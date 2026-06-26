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
