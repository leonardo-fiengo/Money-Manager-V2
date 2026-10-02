from money_manager.db.connection import get_db
from money_manager.services.categories import seed_default_categories


DEFAULT_ACCOUNTS = [
    ("Revolut", "bank", "/static/uploads/accounts/revolut.svg", 0, None, None),
    ("Cash", "cash", "/static/uploads/accounts/cash.svg", 0, None, None),
    ("PayPal", "wallet", "/static/uploads/accounts/paypal.svg", 0, None, None),
    ("Nexi", "prepaid_card", "/static/uploads/accounts/nexi.svg", 0, None, None),
]


def seed_defaults():
    db = get_db()
    for name, account_type, logo, opening_balance, _, settlement_day in DEFAULT_ACCOUNTS:
        db.execute(
            """
            INSERT OR IGNORE INTO accounts (name, type, logo, opening_balance_minor, settlement_day)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, account_type, logo, opening_balance, settlement_day),
        )
        db.execute(
            "UPDATE accounts SET logo = ? WHERE name = ? AND (logo IS NULL OR logo = '')",
            (logo, name),
        )

    for name, _, _, _, settlement_account, _ in DEFAULT_ACCOUNTS:
        if settlement_account:
            db.execute(
                """
                UPDATE accounts
                SET settlement_account_id = (SELECT id FROM accounts WHERE name = ?)
                WHERE name = ? AND settlement_account_id IS NULL
                """,
                (settlement_account, name),
            )

    db.commit()
    seed_default_categories()
