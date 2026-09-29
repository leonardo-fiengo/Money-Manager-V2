from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from sqlite3 import IntegrityError

from money_manager.services.accounts import list_accounts
from money_manager.services.categories import list_categories
from money_manager.services.merchants import list_merchants
from money_manager.services.categories import create_category, get_category
from money_manager.services.merchants import create_merchant, get_merchant
from money_manager.services.preferences import payment_accounts, payment_preference
from money_manager.services.transactions import create_transaction, delete_transaction, get_transaction, list_transactions, update_transaction, restore_transaction
from money_manager.utils.dates import today_iso
from money_manager.utils.filters import clean_amount, empty_to_none


bp = Blueprint("transactions", __name__, url_prefix="/transactions")


def _context(tx=None, error=None, editing=False):
    return dict(tx=tx, error=error, editing=editing, today=today_iso(),
                accounts=list_accounts(active_only=False) if editing else payment_accounts(),
                merchants=list_merchants(), categories=list_categories(), preference=payment_preference())


def _form_data():
    return {
        "date": request.form.get("date"),
        "type": request.form.get("type"),
        "amount": clean_amount(request.form.get("amount")),
        "currency": (request.form.get("currency") or "EUR").upper(),
        "category": empty_to_none(request.form.get("category")),
        "description": empty_to_none(request.form.get("description")),
        "account_id": int(request.form.get("account_id") or 0),
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
        "start": request.args.get("start"),
        "end": request.args.get("end"),
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
            flash("Transaction saved.", "success")
            if request.form.get("after_save") == "another":
                return redirect(url_for("transactions.new"))
            return redirect(url_for("transactions.index"))
        except ValueError as error:
            return render_template("transactions/form.html", **_context(request.form, str(error))), 400
    return render_template("transactions/form.html", **_context())


@bp.route("/<int:transaction_id>/edit", methods=("GET", "POST"))
def edit(transaction_id):
    tx = get_transaction(transaction_id)
    if tx is None:
        abort(404)
    if request.method == "POST":
        try:
            update_transaction(transaction_id, _form_data())
            return redirect(url_for("transactions.index"))
        except ValueError as error:
            return render_template("transactions/form.html", **_context(request.form, str(error), editing=True)), 400
    return render_template("transactions/form.html", **_context(tx, editing=True))


@bp.route("/<int:transaction_id>/delete", methods=("POST",))
def delete(transaction_id):
    trash_id = delete_transaction(transaction_id)
    if trash_id:
        flash(str(trash_id), "undo_transaction")
    return redirect(url_for("transactions.index"))


@bp.post("/restore/<int:trash_id>")
def restore(trash_id):
    try:
        restore_transaction(trash_id)
        flash("Transaction restored.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("transactions.index"))


@bp.post("/options/<kind>")
def quick_option(kind):
    if kind not in {"category", "merchant"}:
        abort(404)
    data = request.form
    name = data.get("name", "").strip()
    if not name or len(name) > 100:
        return jsonify(error="Enter a name between 1 and 100 characters."), 400
    try:
        if kind == "category":
            category_id = create_category(dict(name=name, type=data.get("type", "expense"), color="#147d64", icon=None))
            row = dict(get_category(category_id))
        else:
            default = data.get("default_category") or None
            if default and default not in {r["name"] for r in list_categories()}:
                raise ValueError("Choose an existing category.")
            merchant_id = create_merchant(name, default_category=default)
            row = dict(get_merchant(merchant_id))
        return jsonify(row), 201
    except IntegrityError:
        return jsonify(error="That name already exists. Choose it from the dropdown or use a different name."), 400
    except ValueError as error:
        return jsonify(error=str(error)), 400
