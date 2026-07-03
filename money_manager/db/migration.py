from flask import current_app

from money_manager.db.connection import get_db
from money_manager.db.schema import SCHEMA
from money_manager.db.seed import seed_defaults
from money_manager.utils.exchange import to_eur


def ensure_database(app):
    with app.app_context():
        current_app.config["DATA_DIR"].mkdir(exist_ok=True)
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()
        run_migrations(db)
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
    _backfill_transaction_amount_eur(db)


def _run_once(db, name, migration):
    exists = db.execute("SELECT name FROM schema_migrations WHERE name = ?", (name,)).fetchone()
    if exists:
        return
    migration(db)
    db.execute("INSERT INTO schema_migrations (name) VALUES (?)", (name,))
    db.commit()


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
    if "amount_eur" not in columns:
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
