from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from sqlite3 import IntegrityError
from datetime import date, timedelta

from money_manager.services.accounts import list_accounts
from money_manager.services.categories import list_categories
from money_manager.services.merchants import list_merchants
from money_manager.services.categories import create_category, get_category
from money_manager.services.merchants import create_merchant, get_merchant
from money_manager.services.preferences import payment_accounts, payment_preference
from money_manager.services.transactions import create_transaction, delete_transaction, get_transaction, list_transactions, update_transaction, restore_transaction
from money_manager.services.importing import create_batch, get_batch, save_mapping, preview_batch, confirm_batch, list_rules, save_rule, delete_rule
from money_manager.services.transaction_details import splits_for, save_splits, tags_for, save_tags, linked_expense, link_refund
from money_manager.services.attachments import attachments_for, save_attachment
from money_manager.services.relationships import relationships_for
from money_manager.services.importing import suggested_mapping, save_profile
from money_manager.db.connection import get_db
import json
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
        "status": "pending" if (request.form.get("date") or "") > today_iso() else "posted",
    }


@bp.route("/")
def index():
    filters = {
        "type": request.args.get("type"),
        "account_id": request.args.get("account_id"),
        "account_activity": request.args.get("account_activity") == '1',
        "category": request.args.get("category"),
        "needs_category": request.args.get("needs_category"),
        "tag": request.args.get("tag"),
        "search": request.args.get("search"),
        "start": request.args.get("start"),
        "end": request.args.get("end"),
    }
    page_size = 50
    total = list_transactions(filters, include_pending=True, count=True)
    pages = max(1, (total + page_size - 1) // page_size)
    try:
        page = min(pages, max(1, int(request.args.get("page", 1))))
    except ValueError:
        page = 1
    transactions = list_transactions(filters, include_pending=True, limit=page_size, offset=(page - 1) * page_size)
    month_labels = {tx["date"][:7]: date.fromisoformat(tx["date"]).strftime("%B %Y") for tx in transactions}
    return render_template(
        "transactions/index.html",
        transactions=transactions,
        month_labels=month_labels,
        accounts=list_accounts(),
        merchants=list_merchants(),
        categories=list_categories(),
        filters=filters,
        pagination=dict(page=page, pages=pages, total=total, first=(page - 1) * page_size + 1 if total else 0, last=min(page * page_size, total)),
        today=today_iso(),
        yesterday=(date.today() - timedelta(days=1)).isoformat(),
    )


@bp.route("/import", methods=("GET", "POST"))
def import_csv():
    if request.method == "POST":
        try:
            file = request.files.get("file")
            if not file or not (file.filename or "").lower().endswith(".csv"):
                raise ValueError("Choose a CSV file.")
            batch_id = create_batch(file, int(request.form.get("account_id") or 0))
            return redirect(url_for("transactions.import_batch", batch_id=batch_id))
        except ValueError as error:
            return render_template("transactions/import.html", accounts=list_accounts(), error=str(error)), 400
    return render_template("transactions/import.html", accounts=list_accounts(), categories=list_categories(), merchants=list_merchants())


@bp.route("/import/<int:batch_id>", methods=("GET", "POST"))
def import_batch(batch_id):
    batch = get_batch(batch_id)
    if not batch:
        abort(404)
    if request.method == "POST":
        try:
            save_mapping(batch_id, {key: request.form.get(key) for key in ("date", "description", "amount", "debit", "credit", "currency", "date_format", "default_currency", "expense_sign")})
            if request.form.get('profile_name', '').strip():
                save_profile(batch_id, request.form['profile_name'])
            return redirect(url_for("transactions.import_batch", batch_id=batch_id))
        except ValueError as error:
            return render_template("transactions/import_batch.html", batch=batch, headers=json.loads(batch["headers_json"]), sample=json.loads(batch["rows_json"])[:3], rows=None, categories=list_categories(), mapping=request.form, error=str(error)), 400
    rows = preview_batch(batch_id) if batch["status"] == "review" else None
    return render_template("transactions/import_batch.html", batch=batch, headers=json.loads(batch["headers_json"]), sample=json.loads(batch["rows_json"])[:3], rows=rows, categories=list_categories(), mapping=suggested_mapping(batch))


@bp.post("/import/<int:batch_id>/confirm")
def import_confirm(batch_id):
    try:
        category_choices = {int(key[9:]): value for key, value in request.form.items() if key.startswith("category_") and key[9:].isdigit()}
        count = confirm_batch(batch_id, request.form.getlist("selected"), request.form.getlist("override"), category_choices, request.form.getlist("remember"))
        flash(f"Imported {count} transactions.", "success")
        return redirect(url_for("transactions.index"))
    except ValueError as error:
        batch = get_batch(batch_id)
        if not batch:
            abort(404)
        return render_template("transactions/import_batch.html", batch=batch, headers=json.loads(batch["headers_json"]), sample=[], rows=preview_batch(batch_id), categories=list_categories(), error=str(error)), 400


@bp.route("/import/rules", methods=("GET", "POST"))
def import_rules():
    error = None
    if request.method == "POST":
        try:
            save_rule(request.form.get("needle"), request.form.get("merchant_id") or None, request.form.get("category") or None)
            return redirect(url_for("transactions.import_rules"))
        except ValueError as exc:
            error = str(exc)
    return render_template("transactions/import_rules.html", rules=list_rules(), merchants=list_merchants(), categories=list_categories(), error=error), (400 if error else 200)


@bp.post("/import/rules/<int:rule_id>/delete")
def import_rule_delete(rule_id):
    delete_rule(rule_id)
    return redirect(url_for("transactions.import_rules"))


@bp.route("/new", methods=("GET", "POST"))
def new():
    if request.method == "POST":
        try:
            transaction_id = create_transaction(_form_data())
            if get_transaction(transaction_id)["exchange_rate_source"] == "estimated":
                flash("Saved with an estimated exchange rate because live rates are unavailable. Review the rate in transaction details.", "warning")
            flash("Transaction saved.", "success")
            if request.form.get("after_save") == "another":
                return redirect(url_for("transactions.new"))
            return redirect(url_for("transactions.index"))
        except ValueError as error:
            return render_template("transactions/form.html", **_context(request.form, str(error))), 400
    account_id = request.args.get('account_id',type=int)
    preset = dict(type='expense',date=today_iso(),currency='EUR',amount='',account_id=account_id) if account_id in {a['id'] for a in list_accounts()} else None
    return render_template("transactions/form.html", **_context(preset))


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


@bp.route("/<int:transaction_id>/details", methods=("GET", "POST"))
def details(transaction_id):
    tx = get_transaction(transaction_id)
    if not tx:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            action = request.form.get("action")
            if action == "splits":
                save_splits(transaction_id, zip(request.form.getlist("split_category"), request.form.getlist("split_amount")))
            elif action == "tags":
                save_tags(transaction_id, request.form.get("tags"))
            elif action == "link":
                link_refund(transaction_id, int(request.form["expense_id"]) if request.form.get("expense_id") else None, request.form.get("kind", "refund"))
            elif action == 'notes':
                notes = request.form.get('notes', '').strip()
                if len(notes)>2000:
                    raise ValueError('Keep notes under 2,000 characters.')
                db=get_db()
                db.execute('UPDATE transactions SET notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(notes,transaction_id))
                db.commit()
            elif action == 'attachment':
                file=request.files.get('file')
                if not file:
                    raise ValueError('Choose a receipt to attach.')
                save_attachment(transaction_id,file)
            else:
                raise ValueError("Choose a detail to save.")
            flash("Transaction details saved.", "success")
            return redirect(url_for("transactions.details", transaction_id=transaction_id))
        except ValueError as exc:
            error = str(exc)
    expenses = list_transactions({"type": "expense"}, limit=100) if tx["type"] == "income" else []
    return render_template("transactions/details.html", tx=tx, splits=splits_for(transaction_id), tags=tags_for(transaction_id), link=linked_expense(transaction_id), expenses=expenses, categories=list_categories(), attachments=attachments_for(transaction_id), relationships=relationships_for(transaction_id), error=error), (400 if error else 200)


@bp.route("/<int:transaction_id>/delete", methods=("POST",))
def delete(transaction_id):
    try:
        trash_id = delete_transaction(transaction_id)
        if trash_id:
            flash(str(trash_id), "undo_transaction")
    except ValueError as exc:
        flash(str(exc), 'error')
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
