from flask import Blueprint, redirect, render_template, request, url_for

from money_manager.services.accounts import list_accounts
from money_manager.services.categories import list_categories
from money_manager.services.merchants import list_merchants
from money_manager.services.transactions import create_transaction, delete_transaction, get_transaction, list_transactions, update_transaction
from money_manager.utils.filters import clean_amount, empty_to_none


bp = Blueprint("transactions", __name__, url_prefix="/transactions")


def _form_data():
    return {
        "date": request.form.get("date"),
        "type": request.form.get("type"),
        "amount": clean_amount(request.form.get("amount")),
        "currency": (request.form.get("currency") or "EUR").upper(),
        "category": empty_to_none(request.form.get("category")),
        "description": empty_to_none(request.form.get("description")),
        "account_id": int(request.form.get("account_id")),
        "destination_account_id": int(request.form["destination_account_id"]) if request.form.get("destination_account_id") else None,
        "merchant_id": int(request.form["merchant_id"]) if request.form.get("merchant_id") else None,
        "status": request.form.get("status", "posted"),
    }


@bp.route("/")
def index():
    filters = {
        "type": request.args.get("type"),
        "account_id": request.args.get("account_id"),
        "category": request.args.get("category"),
        "search": request.args.get("search"),
    }
    return render_template(
        "transactions/index.html",
        transactions=list_transactions(filters, include_pending=True),
        accounts=list_accounts(),
        merchants=list_merchants(),
        categories=list_categories(),
        filters=filters,
    )


@bp.route("/new", methods=("GET", "POST"))
def new():
    if request.method == "POST":
        try:
            create_transaction(_form_data())
            return redirect(url_for("transactions.index"))
        except ValueError as error:
            return render_template("transactions/form.html", tx=request.form, accounts=list_accounts(), merchants=list_merchants(), categories=list_categories(), error=str(error)), 400
    return render_template("transactions/form.html", tx=None, accounts=list_accounts(), merchants=list_merchants(), categories=list_categories())


@bp.route("/<int:transaction_id>/edit", methods=("GET", "POST"))
def edit(transaction_id):
    tx = get_transaction(transaction_id)
    if request.method == "POST":
        try:
            update_transaction(transaction_id, _form_data())
            return redirect(url_for("transactions.index"))
        except ValueError as error:
            return render_template("transactions/form.html", tx=request.form, accounts=list_accounts(), merchants=list_merchants(), categories=list_categories(), error=str(error)), 400
    return render_template("transactions/form.html", tx=tx, accounts=list_accounts(), merchants=list_merchants(), categories=list_categories())


@bp.route("/<int:transaction_id>/delete", methods=("POST",))
def delete(transaction_id):
    delete_transaction(transaction_id)
    return redirect(url_for("transactions.index"))
