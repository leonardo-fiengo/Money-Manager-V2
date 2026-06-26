from flask import Blueprint, redirect, render_template, request, url_for

from money_manager.services.accounts import account_balances, create_account, list_accounts, update_account, get_account


bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.route("/")
def index():
    return render_template("accounts/index.html", accounts=account_balances())


@bp.route("/new", methods=("GET", "POST"))
def new():
    if request.method == "POST":
        create_account(
            request.form["name"],
            request.form["type"],
            float(request.form.get("opening_balance") or 0),
            int(request.form["settlement_account_id"]) if request.form.get("settlement_account_id") else None,
            int(request.form["settlement_day"]) if request.form.get("settlement_day") else None,
            request.form.get("logo") or None,
        )
        return redirect(url_for("accounts.index"))
    return render_template("accounts/form.html", account=None, accounts=list_accounts())


@bp.route("/<int:account_id>/edit", methods=("GET", "POST"))
def edit(account_id):
    account = get_account(account_id)
    if request.method == "POST":
        update_account(
            account_id,
            request.form["name"],
            request.form["type"],
            float(request.form.get("opening_balance") or 0),
            int(request.form["settlement_account_id"]) if request.form.get("settlement_account_id") else None,
            int(request.form["settlement_day"]) if request.form.get("settlement_day") else None,
            bool(request.form.get("is_active")),
            request.form.get("logo") or None,
        )
        return redirect(url_for("accounts.index"))
    return render_template("accounts/form.html", account=account, accounts=list_accounts(active_only=False))
