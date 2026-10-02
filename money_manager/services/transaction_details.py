from money_manager.db.connection import get_db
from money_manager.services.transactions import get_transaction
from money_manager.utils.money import money_value, to_minor, money_sum


def splits_for(transaction_id):
    return get_db().execute("SELECT * FROM transaction_splits WHERE transaction_id = ? ORDER BY id", (transaction_id,)).fetchall()


def save_splits(transaction_id, lines):
    tx = get_transaction(transaction_id)
    if not tx or tx["type"] != "expense":
        raise ValueError("Only expenses can be split.")
    categories = {row["name"] for row in get_db().execute("SELECT name FROM categories")}
    parsed = []
    for category, raw_amount in lines:
        if not category and not raw_amount:
            continue
        amount = money_value(raw_amount)
        if category not in categories or amount <= 0:
            raise ValueError("Each split needs an existing category and a positive amount.")
        parsed.append((category, amount))
    total = tx["amount_eur"] or tx["amount"]
    if parsed and sum(to_minor(amount) for _, amount in parsed) != to_minor(total):
        raise ValueError(f"Split amounts must add up to €{total:.2f}.")
    db = get_db()
    with db:
        db.execute("DELETE FROM transaction_splits WHERE transaction_id = ?", (transaction_id,))
        db.executemany("INSERT INTO transaction_splits (transaction_id, category, amount_eur_minor) VALUES (?, ?, ?)", [(transaction_id, category, to_minor(amount)) for category, amount in parsed])


def tags_for(transaction_id):
    return [row["tag"] for row in get_db().execute("SELECT tag FROM transaction_tags WHERE transaction_id = ? ORDER BY tag", (transaction_id,))]


def save_tags(transaction_id, raw_tags):
    tags = list(dict.fromkeys(tag.strip() for tag in (raw_tags or "").split(",") if tag.strip()))
    if len(tags) > 8 or any(len(tag) > 40 for tag in tags):
        raise ValueError("Use at most eight tags, each under 40 characters.")
    db = get_db()
    with db:
        db.execute("DELETE FROM transaction_tags WHERE transaction_id = ?", (transaction_id,))
        db.executemany("INSERT INTO transaction_tags (transaction_id, tag) VALUES (?, ?)", [(transaction_id, tag) for tag in tags])


def linked_expense(transaction_id):
    return get_db().execute("SELECT * FROM transaction_links WHERE related_transaction_id = ?", (transaction_id,)).fetchone()


def link_refund(income_id, expense_id=None, kind="refund"):
    income = get_transaction(income_id)
    if not income or income["type"] != "income" or income['is_transfer_mirror']:
        raise ValueError("Choose an income transaction to link.")
    db = get_db()
    if expense_id:
        expense = get_transaction(expense_id)
        if not expense or expense["type"] != "expense":
            raise ValueError("Choose an existing expense.")
        if kind not in {"refund", "reimbursement", "chargeback"}:
            raise ValueError("Choose refund, reimbursement, or chargeback.")
        prior = db.execute("SELECT COALESCE(SUM(t.amount_eur_minor),0) / 100.0 AS total FROM transaction_links l JOIN transactions t ON t.id = l.related_transaction_id WHERE l.source_transaction_id = ? AND l.related_transaction_id != ?", (expense_id, income_id)).fetchone()["total"]
        if to_minor(prior) + income["amount_eur_minor"] > expense["amount_eur_minor"]:
            raise ValueError("Linked refunds cannot exceed the original expense.")
    with db:
        db.execute("DELETE FROM transaction_links WHERE related_transaction_id = ?", (income_id,))
        if expense_id:
            db.execute("INSERT INTO transaction_links (source_transaction_id, related_transaction_id, kind) VALUES (?, ?, ?)", (expense_id, income_id, kind))


def expense_allocations(start=None, end=None):
    db = get_db()
    rows = db.execute("SELECT * FROM transactions WHERE status = 'posted' AND type = 'expense' AND (? IS NULL OR date >= ?) AND (? IS NULL OR date <= ?)", (start, start, end, end)).fetchall()
    splits = {}
    for row in db.execute("SELECT * FROM transaction_splits"):
        splits.setdefault(row["transaction_id"], []).append(row)
    refunds = {row["source_transaction_id"]: row["total"] for row in db.execute("""
        SELECT l.source_transaction_id, SUM(t.amount_eur_minor) / 100.0 AS total FROM transaction_links l
        JOIN transactions t ON t.id = l.related_transaction_id
        WHERE t.status = 'posted' GROUP BY l.source_transaction_id
    """)}
    output = []
    for tx in rows:
        gross = tx["amount_eur"] or tx["amount"]
        net = max(0, gross - refunds.get(tx["id"], 0))
        split_lines = splits.get(tx["id"], [])
        allocated = 0
        for split in split_lines[:-1]:
            amount = max(0, min(round(net * split["amount_eur"] / gross, 2), round(net - allocated, 2)))
            output.append(dict(transaction_id=tx["id"], date=tx["date"], category=split["category"], amount=amount))
            allocated += amount
        if split_lines:
            output.append(dict(transaction_id=tx["id"], date=tx["date"], category=split_lines[-1]["category"], amount=round(net - allocated, 2)))
        else:
            output.append(dict(transaction_id=tx["id"], date=tx["date"], category=tx["category"] or "Uncategorized", amount=round(net, 2)))
    return output
