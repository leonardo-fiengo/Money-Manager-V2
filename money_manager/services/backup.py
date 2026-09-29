from money_manager.db.connection import get_db


EXPORT_TABLES = [
    "accounts",
    "merchants",
    "categories",
    "transactions",
    "recurring_rules",
    "loans",
    "loan_payments",
    "budgets",
    "payment_preferences",
    "balance_checks",
    "transaction_trash",
    "savings_pots",
]


def export_data():
    db = get_db()
    return {
        table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        for table in EXPORT_TABLES
    }
