from money_manager.db.connection import get_db
from money_manager.services.transactions import create_settlement_for_transaction, get_transaction
from money_manager.utils.dates import today_iso


def list_pending():
    return get_db().execute(
        """
        SELECT t.*, a.name AS account_name, a.logo AS account_logo,
               d.name AS destination_account_name, d.logo AS destination_account_logo,
               m.name AS merchant_name, m.logo AS merchant_logo,
               c.icon AS category_icon, c.color AS category_color
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        LEFT JOIN accounts d ON d.id = t.destination_account_id
        LEFT JOIN merchants m ON m.id = t.merchant_id
        LEFT JOIN categories c ON c.name = t.category
        WHERE t.status = 'pending'
        ORDER BY t.date ASC, t.id ASC
        """
    ).fetchall()


def execute_due_pending(current_date=None):
    db = get_db()
    due = db.execute(
        "SELECT id FROM transactions WHERE status = 'pending' AND date <= ?",
        (current_date or today_iso(),),
    ).fetchall()
    db.execute(
        """
        UPDATE transactions
        SET status = 'posted', updated_at = CURRENT_TIMESTAMP
        WHERE status = 'pending' AND date <= ?
        """,
        (current_date or today_iso(),),
    )
    db.commit()
    for row in due:
        tx = get_transaction(row["id"])
        if tx and tx["type"] == "expense":
            create_settlement_for_transaction(tx["id"])


def mark_posted(transaction_id):
    db = get_db()
    tx = get_transaction(transaction_id)
    db.execute(
        "UPDATE transactions SET status = 'posted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (transaction_id,),
    )
    db.commit()
    if tx and tx["type"] == "expense":
        create_settlement_for_transaction(transaction_id)
