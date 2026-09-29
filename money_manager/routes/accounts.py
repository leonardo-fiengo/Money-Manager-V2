from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from money_manager.services.accounts import account_balances, create_account, list_accounts, update_account, get_account
from money_manager.services.preferences import payment_accounts, payment_preference, save_payment_preference
from money_manager.services.reconciliation import check_history, check_payload, preview_balances, record_checks
from money_manager.services.planning import savings_summary, save_pot


bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.route("/")
def index():
    return render_template("accounts/index.html", accounts=account_balances(), preference=payment_preference(), payment_accounts=payment_accounts())


@bp.post("/payment-preference")
def preference():
    try:
        save_payment_preference(request.form.get("mode"), request.form.get("account_id"))
        flash("Payment preference saved.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("accounts.index"))


@bp.route("/pots", methods=("GET", "POST"))
def pots():
    error = None
    if request.method == "POST":
        try:
            save_pot(request.form.get("name"), request.form.get("target"), request.form.get("reserved") or 0, request.form.get("pot_id") or None)
            flash("Savings pot saved. Your account balances haven't changed.", "success")
            return redirect(url_for("accounts.pots"))
        except ValueError as exc:
            error = str(exc)
    return render_template("accounts/pots.html", summary=savings_summary(), error=error), (400 if error else 200)


@bp.route("/check", methods=("GET", "POST"))
def check():
    rows, token, error = [], None, None
    values = request.form if request.method == "POST" else {}
    serializer = URLSafeTimedSerializer(current_app.secret_key, salt="balance-check")
    if request.method == "POST":
        try:
            if request.form.get("action") == "save":
                payload = serializer.loads(request.form.get("token", ""), max_age=1800)
                record_checks(payload, request.form.getlist("adjust"), request.form.get("note", ""))
                flash("Balance check saved. Only the adjustments you selected were applied.", "success")
                return redirect(url_for("accounts.check"))
            rows = preview_balances({str(a["id"]): request.form.get(f"actual_{a['id']}", "") for a in list_accounts(active_only=False)})
            token = serializer.dumps(check_payload(rows))
        except BadSignature:
            error = "This preview expired. Enter balances again to create a new check."
        except ValueError as exc:
            error = str(exc)
    return render_template("accounts/check.html", accounts=account_balances(), rows=rows, token=token, error=error, values=values, history=check_history()), (400 if error else 200)


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
