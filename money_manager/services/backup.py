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
]


def export_data():
    db = get_db()
    return {
        table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        for table in EXPORT_TABLES
    }
