from flask import current_app

from money_manager.db.connection import get_db
from money_manager.db.schema import SCHEMA
from money_manager.db.seed import seed_defaults
from money_manager.utils.exchange import to_eur


def ensure_database(app):
    with app.app_context():
        current_app.config["DATA_DIR"].mkdir(exist_ok=True)
        db = get_db()
        if db.execute('PRAGMA quick_check').fetchone()['quick_check']!='ok':
            raise ValueError('Database integrity check failed. Restore a checked backup before continuing.')
        tables={r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'transactions' in tables and ('schema_migrations' not in tables or not db.execute("SELECT 1 FROM schema_migrations WHERE name='014_people_and_obligations'").fetchone()):
            from money_manager.services.backup import create_snapshot
            create_snapshot('before-migration')
        db.executescript(SCHEMA)
        db.commit()
        run_migrations(db)
        if db.execute('PRAGMA integrity_check').fetchone()['integrity_check']!='ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Database integrity check failed after migration.')
        seed_defaults()


def run_migrations(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.commit()
    _run_once(db, "001_recurring_visual_mode", _add_recurring_visual_mode)
    _run_once(db, "002_account_logos", _add_account_logos)
    _run_once(db, "003_transaction_currency", _add_transaction_currency)
    _run_once(db, "004_transaction_amount_eur", _add_transaction_amount_eur)
    _run_once(db, "005_nexi_prepaid_account", _fix_nexi_prepaid_account)
    _run_once(db, "006_prepaid_card_account_type", _add_prepaid_card_account_type)
    _run_once(db, "007_budget_rollover", _add_budget_rollover)
    _run_once(db, "008_subscription_flag", _add_subscription_flag)
    _backfill_transaction_amount_eur(db)
    from money_manager.db.money_migration import migrate_money
    _run_once(db, "009_integer_money", migrate_money)
    _run_once(db, "010_scheduling_and_rates", _add_scheduling_and_rates)
    from money_manager.db.roadmap_migration import migrate_roadmap
    _run_once(db, "011_finance_workflows", migrate_roadmap)
    _run_once(db, "012_pot_sources", _add_pot_sources)
    _run_once(db, "013_cockpit_profile", _add_cockpit_profile)
    from money_manager.db.people_migration import migrate_people
    _run_once(db, "014_people_and_obligations", migrate_people)


def _add_cockpit_profile(db):
    from money_manager.db.atomic import atomic
    with atomic(db):
        db.execute("ALTER TABLE accounts ADD COLUMN role TEXT NOT NULL DEFAULT 'auto' CHECK(role IN ('auto','everyday','savings'))")
        db.execute("CREATE TABLE local_profile (id INTEGER PRIMARY KEY CHECK(id=1), display_name TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        db.execute("INSERT INTO local_profile(id) VALUES(1)")


def _add_pot_sources(db):
    from money_manager.db.atomic import atomic
    with atomic(db):
        db.execute("ALTER TABLE savings_pots ADD COLUMN spent_at TEXT")
        db.execute("ALTER TABLE savings_pots ADD COLUMN deleted_at TEXT")
        db.execute("""CREATE TABLE pot_sources (
            pot_id INTEGER NOT NULL REFERENCES savings_pots(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            reserved_minor INTEGER NOT NULL CHECK(typeof(reserved_minor)='integer' AND reserved_minor>=0),
            PRIMARY KEY(pot_id,account_id))""")
        db.execute("""CREATE TABLE pot_movement_sources (
            movement_id INTEGER NOT NULL REFERENCES pot_movements(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            delta_minor INTEGER NOT NULL CHECK(typeof(delta_minor)='integer'),
            PRIMARY KEY(movement_id,account_id))""")
        db.execute("""CREATE TABLE pot_spending (
            pot_id INTEGER NOT NULL REFERENCES savings_pots(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
            amount_minor INTEGER NOT NULL CHECK(typeof(amount_minor)='integer' AND amount_minor>0),
            PRIMARY KEY(pot_id,account_id))""")


def _run_once(db, name, migration):
    exists = db.execute("SELECT name FROM schema_migrations WHERE name = ?", (name,)).fetchone()
    if exists:
        return
    migration(db)
    db.execute("INSERT OR IGNORE INTO schema_migrations (name) VALUES (?)", (name,))
    db.commit()


def _add_budget_rollover(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(budgets)")}
    if "rollover" not in columns:
        db.execute("ALTER TABLE budgets ADD COLUMN rollover INTEGER NOT NULL DEFAULT 0")


def _add_subscription_flag(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(recurring_rules)")}
    if "is_subscription" not in columns:
        db.execute("ALTER TABLE recurring_rules ADD COLUMN is_subscription INTEGER NOT NULL DEFAULT 0")


def _add_recurring_visual_mode(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(recurring_rules)").fetchall()}
    if "visual_mode" not in columns:
        db.execute(
            """
            ALTER TABLE recurring_rules
            ADD COLUMN visual_mode TEXT NOT NULL DEFAULT 'auto'
            CHECK (visual_mode IN ('auto', 'merchant_logo', 'standard'))
            """
        )


def _add_account_logos(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(accounts)").fetchall()}
    if "logo" not in columns:
        db.execute("ALTER TABLE accounts ADD COLUMN logo TEXT")


def _add_transaction_currency(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(transactions)").fetchall()}
    if "currency" not in columns:
        db.execute("ALTER TABLE transactions ADD COLUMN currency TEXT NOT NULL DEFAULT 'EUR'")


def _add_transaction_amount_eur(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(transactions)").fetchall()}
    if "amount_eur" not in columns:
        db.execute("ALTER TABLE transactions ADD COLUMN amount_eur REAL NOT NULL DEFAULT 0")
    _backfill_transaction_amount_eur(db)


def _backfill_transaction_amount_eur(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(transactions)").fetchall()}
    if "amount_eur_minor" in columns or "amount_eur" not in columns:
        return

    rows = db.execute(
        """
        SELECT id, amount, currency, amount_eur
        FROM transactions
        WHERE amount_eur IS NULL OR amount_eur = 0
        """
    ).fetchall()
    for row in rows:
        db.execute(
            "UPDATE transactions SET amount_eur = ? WHERE id = ?",
            (to_eur(row["amount"], row["currency"] or "EUR"), row["id"]),
        )
    db.commit()


def _add_scheduling_and_rates(db):
    for column in ("exchange_rate TEXT", "exchange_rate_date TEXT", "exchange_rate_source TEXT"):
        db.execute(f"ALTER TABLE transactions ADD COLUMN {column}")
    db.execute("""CREATE TABLE recurring_occurrences (
        recurring_rule_id INTEGER NOT NULL REFERENCES recurring_rules(id) ON DELETE CASCADE,
        due_date TEXT NOT NULL,
        PRIMARY KEY(recurring_rule_id, due_date)
    )""")
    db.execute("INSERT OR IGNORE INTO recurring_occurrences SELECT recurring_rule_id, date FROM transactions WHERE recurring_rule_id IS NOT NULL")
    db.execute("CREATE INDEX IF NOT EXISTS idx_transactions_recurring_date ON transactions(recurring_rule_id, date)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_transactions_status_date ON transactions(status, date)")


def _fix_nexi_prepaid_account(db):
    nexi = db.execute(
        "SELECT id FROM accounts WHERE lower(name) = 'nexi' AND type = 'credit_card'"
    ).fetchone()
    if not nexi:
        return

    # Remove only unposted transfers that were generated automatically for
    # Nexi while it was incorrectly classified as a credit card.
    db.execute(
        """
        DELETE FROM transactions
        WHERE destination_account_id = ?
          AND status = 'pending'
          AND is_credit_card_settlement = 1
        """,
        (nexi["id"],),
    )
    db.execute(
        """
        UPDATE accounts
        SET type = 'wallet', settlement_account_id = NULL, settlement_day = NULL
        WHERE id = ?
        """,
        (nexi["id"],),
    )


def _add_prepaid_card_account_type(db):
    table = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'accounts'"
    ).fetchone()
    supports_prepaid = table and "'prepaid_card'" in table["sql"]

    if not supports_prepaid:
        db.commit()
        db.execute("PRAGMA foreign_keys = OFF")
        try:
            db.executescript(
                """
                BEGIN;

                CREATE TABLE accounts_with_prepaid (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL CHECK (
                        type IN ('bank', 'cash', 'wallet', 'prepaid_card', 'credit_card', 'investment')
                    ),
                    logo TEXT,
                    opening_balance REAL NOT NULL DEFAULT 0,
                    settlement_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
                    settlement_day INTEGER CHECK (settlement_day BETWEEN 1 AND 28),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                INSERT INTO accounts_with_prepaid (
                    id, name, type, logo, opening_balance, settlement_account_id,
                    settlement_day, is_active, created_at
                )
                SELECT
                    id, name, type, logo, opening_balance, settlement_account_id,
                    settlement_day, is_active, created_at
                FROM accounts;

                DROP TABLE accounts;
                ALTER TABLE accounts_with_prepaid RENAME TO accounts;

                COMMIT;
                """
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute("PRAGMA foreign_keys = ON")

    db.execute(
        """
        UPDATE accounts
        SET type = 'prepaid_card', settlement_account_id = NULL, settlement_day = NULL
        WHERE lower(name) = 'nexi'
          AND type IN ('wallet', 'credit_card')
        """
    )
