from flask import Blueprint, redirect, render_template, request, url_for

from money_manager.services.loans import (
    add_payment,
    create_loan,
    delete_loan,
    delete_payment,
    get_loan,
    list_loans,
    list_payments,
    update_loan,
)
from money_manager.utils.filters import clean_amount


bp = Blueprint("loans", __name__, url_prefix="/loans")


def _loan_form_data():
    return {
        "direction": request.form["direction"],
        "counterparty": request.form["counterparty"],
        "principal_amount": clean_amount(request.form.get("principal_amount")),
        "expected_total_amount": clean_amount(request.form.get("expected_total_amount")),
        "start_date": request.form.get("start_date"),
        "due_date": request.form.get("due_date"),
        "notes": request.form.get("notes"),
        "status": request.form.get("status", "open"),
    }


@bp.route("/")
def index():
    status = request.args.get("status")
    return render_template("loans/index.html", loans=list_loans(status), status=status)


@bp.route("/new", methods=("GET", "POST"))
def new():
    if request.method == "POST":
        try:
            loan_id = create_loan(_loan_form_data())
            return redirect(url_for("loans.detail", loan_id=loan_id))
        except ValueError as error:
            return render_template("loans/form.html", loan=request.form, error=str(error)), 400
    return render_template("loans/form.html", loan=None)


@bp.route("/<int:loan_id>")
def detail(loan_id):
    return render_template("loans/detail.html", loan=get_loan(loan_id), payments=list_payments(loan_id))


@bp.route("/<int:loan_id>/edit", methods=("GET", "POST"))
def edit(loan_id):
    loan = get_loan(loan_id)
    if request.method == "POST":
        try:
            update_loan(loan_id, _loan_form_data())
            return redirect(url_for("loans.detail", loan_id=loan_id))
        except ValueError as error:
            return render_template("loans/form.html", loan=request.form, error=str(error)), 400
    return render_template("loans/form.html", loan=loan)


@bp.route("/<int:loan_id>/delete", methods=("POST",))
def delete(loan_id):
    delete_loan(loan_id)
    return redirect(url_for("loans.index"))


@bp.route("/<int:loan_id>/payments", methods=("POST",))
def payment(loan_id):
    try:
        add_payment(
            loan_id,
            {
                "date": request.form.get("date"),
                "amount": clean_amount(request.form.get("amount")),
                "notes": request.form.get("notes"),
            },
        )
    except ValueError:
        pass
    return redirect(url_for("loans.detail", loan_id=loan_id))


@bp.route("/payments/<int:payment_id>/delete", methods=("POST",))
def payment_delete(payment_id):
    loan_id = int(request.form["loan_id"])
    delete_payment(payment_id)
    return redirect(url_for("loans.detail", loan_id=loan_id))
