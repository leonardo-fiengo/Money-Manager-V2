from money_manager.db.connection import get_db
from money_manager.utils.dates import today_iso


def list_loans(status=None):
    params = []
    where = ""
    if status:
        where = "WHERE l.status = ?"
        params.append(status)
    return get_db().execute(
        f"""
        SELECT l.*,
               COALESCE(SUM(p.amount), 0) AS paid_amount,
               MAX(l.expected_total_amount - COALESCE((SELECT SUM(amount) FROM loan_payments WHERE loan_id = l.id), 0), 0) AS outstanding_amount
        FROM loans l
        LEFT JOIN loan_payments p ON p.loan_id = l.id
        {where}
        GROUP BY l.id
        ORDER BY l.status ASC, COALESCE(l.due_date, '9999-12-31') ASC, l.start_date DESC
        """,
        params,
    ).fetchall()


def get_loan(loan_id):
    return get_db().execute(
        """
        SELECT l.*,
               COALESCE((SELECT SUM(amount) FROM loan_payments WHERE loan_id = l.id), 0) AS paid_amount,
               MAX(l.expected_total_amount - COALESCE((SELECT SUM(amount) FROM loan_payments WHERE loan_id = l.id), 0), 0) AS outstanding_amount
        FROM loans l
        WHERE l.id = ?
        """,
        (loan_id,),
    ).fetchone()


def list_payments(loan_id):
    return get_db().execute(
        "SELECT * FROM loan_payments WHERE loan_id = ? ORDER BY date DESC, id DESC",
        (loan_id,),
    ).fetchall()


def create_loan(data):
    _validate_loan_data(data)
    db = get_db()
    expected_total = float(data.get("expected_total_amount") or data["principal_amount"])
    cursor = db.execute(
        """
        INSERT INTO loans (
            direction, counterparty, principal_amount, expected_total_amount,
            start_date, due_date, notes, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open')
        """,
        (
            data["direction"],
            data["counterparty"],
            float(data["principal_amount"]),
            expected_total,
            data.get("start_date") or today_iso(),
            data.get("due_date") or None,
            data.get("notes") or None,
        ),
    )
    db.commit()
    return cursor.lastrowid


def update_loan(loan_id, data):
    _validate_loan_data(data, loan_id)
    db = get_db()
    expected_total = float(data.get("expected_total_amount") or data["principal_amount"])
    db.execute(
        """
        UPDATE loans
        SET direction = ?, counterparty = ?, principal_amount = ?, expected_total_amount = ?,
            start_date = ?, due_date = ?, notes = ?, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            data["direction"],
            data["counterparty"],
            float(data["principal_amount"]),
            expected_total,
            data.get("start_date") or today_iso(),
            data.get("due_date") or None,
            data.get("notes") or None,
            data.get("status", "open"),
            loan_id,
        ),
    )
    db.commit()
    _refresh_status(loan_id)


def delete_loan(loan_id):
    db = get_db()
    db.execute("DELETE FROM loans WHERE id = ?", (loan_id,))
    db.commit()


def add_payment(loan_id, data):
    _validate_payment_data(loan_id, data)
    db = get_db()
    db.execute(
        """
        INSERT INTO loan_payments (loan_id, date, amount, notes)
        VALUES (?, ?, ?, ?)
        """,
        (
            loan_id,
            data.get("date") or today_iso(),
            float(data["amount"]),
            data.get("notes") or None,
        ),
    )
    db.commit()
    _refresh_status(loan_id)


def delete_payment(payment_id):
    db = get_db()
    row = db.execute("SELECT loan_id FROM loan_payments WHERE id = ?", (payment_id,)).fetchone()
    if not row:
        return
    db.execute("DELETE FROM loan_payments WHERE id = ?", (payment_id,))
    db.commit()
    _refresh_status(row["loan_id"])


def loan_summary():
    row = get_db().execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN direction = 'lent_out' AND status = 'open' THEN expected_total_amount - paid_amount END), 0) AS to_receive,
            COALESCE(SUM(CASE WHEN direction = 'borrowed' AND status = 'open' THEN expected_total_amount - paid_amount END), 0) AS to_pay
        FROM (
            SELECT l.*, COALESCE((SELECT SUM(amount) FROM loan_payments WHERE loan_id = l.id), 0) AS paid_amount
            FROM loans l
        )
        """
    ).fetchone()
    return {
        "to_receive": round(row["to_receive"], 2),
        "to_pay": round(row["to_pay"], 2),
    }


def _refresh_status(loan_id):
    loan = get_loan(loan_id)
    if not loan:
        return
    status = "closed" if loan["outstanding_amount"] <= 0 else "open"
    db = get_db()
    db.execute(
        "UPDATE loans SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, loan_id),
    )
    db.commit()


def _validate_loan_data(data, loan_id=None):
    direction = data.get("direction")
    principal = float(data.get("principal_amount") or 0)
    expected_total = float(data.get("expected_total_amount") or principal)
    paid = 0
    if loan_id:
        row = get_loan(loan_id)
        paid = row["paid_amount"] if row else 0

    if direction not in {"lent_out", "borrowed"}:
        raise ValueError("Loan direction is required.")
    if not (data.get("counterparty") or "").strip():
        raise ValueError("Counterparty is required.")
    if principal <= 0:
        raise ValueError("Principal amount must be greater than zero.")
    if expected_total < principal:
        raise ValueError("Expected total cannot be less than principal.")
    if expected_total < paid:
        raise ValueError("Expected total cannot be less than already paid.")


def _validate_payment_data(loan_id, data):
    amount = float(data.get("amount") or 0)
    loan = get_loan(loan_id)
    if not loan:
        raise ValueError("Loan does not exist.")
    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")
