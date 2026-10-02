from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for, abort
from sqlite3 import IntegrityError
from itsdangerous import BadSignature, URLSafeTimedSerializer

from money_manager.services.accounts import account_balances, create_account, list_accounts, update_account, get_account
from money_manager.services.preferences import payment_accounts, payment_preference, save_payment_preference
from money_manager.services.reconciliation import check_history, check_payload, preview_balances, record_checks
from money_manager.services.planning import savings_summary, save_pot, move_pot
from money_manager.services.pots import assign_sources, spend_pot, delete_pot, restore_pot


bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.get('/<int:account_id>')
def detail(account_id):
    from money_manager.services.account_detail import account_detail
    try:
        months = int(request.args.get('history', 6))
    except ValueError:
        months = 6
    detail = account_detail(account_id,request.args.get('period','month'),months)
    if not detail:
        abort(404)
    return render_template('accounts/detail.html', **detail)


def _pot_sources():
    return {key.removeprefix('source_'):value for key,value in request.form.items() if key.startswith('source_')}


@bp.route("/")
def index():
    from money_manager.utils.money import to_minor
    accounts = account_balances()
    active = [a for a in accounts if a["is_active"]]
    return render_template("accounts/index.html", accounts=active,
                           inactive_accounts=[a for a in accounts if not a["is_active"]],
                           total_balance=sum(to_minor(a["balance"]) for a in active) / 100,
                           review_count=sum(bool(a.get("last_check")) and not a.get("last_check_matched") for a in active),
                           unchecked_count=sum(not a.get("last_check") for a in active),
                           preference=payment_preference(), payment_accounts=payment_accounts())


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
            pot_id = request.form.get('pot_id') or None
            if pot_id:
                from money_manager.db.connection import get_db
                old = get_db().execute('SELECT reserved FROM savings_pots WHERE id=?',(pot_id,)).fetchone()
                if not old:
                    raise ValueError('Savings pot not found.')
                reserved, sources = old['reserved'], None
            else:
                reserved, sources = request.form.get('reserved') or 0, _pot_sources()
            save_pot(request.form.get("name"), request.form.get("target"), reserved, pot_id,
                     target_date=request.form.get('target_date') or '', sources=sources)
            flash("Savings pot saved. Your account balances haven't changed.", "success")
            return redirect(url_for("accounts.pots"))
        except ValueError as exc:
            error = str(exc)
    return render_template("accounts/pots.html", summary=savings_summary(), error=error), (400 if error else 200)


@bp.post("/pots/<int:pot_id>/move")
def pot_move(pot_id):
    try:
        move_pot(pot_id, request.form.get("amount"), request.form.get("direction"), request.form.get("note") or "", sources=_pot_sources())
        flash("Pot updated. Your account balances haven't changed.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("accounts.pots"))


@bp.post('/pots/<int:pot_id>/<action>')
def pot_action(pot_id, action):
    try:
        if action == 'sources':
            assign_sources(pot_id,_pot_sources())
            flash('Sources saved. Every euro has an alibi.', 'success')
        elif action == 'spend':
            spend_pot(pot_id,request.form.get('confirm') == 'yes')
            flash('Goal spent. Your source accounts and transaction history are updated. Enjoy it.', 'success')
        elif action == 'delete':
            delete_pot(pot_id)
            flash('Pot deleted. Reserved money is free again; recorded spending stays in your history. Restore it below if you change your mind.', 'success')
        elif action == 'restore':
            restore_pot(pot_id)
            flash('Pot restored. The dream lives on.', 'success')
        else:
            abort(404)
    except ValueError as error:
        flash(str(error),'error')
    return redirect(url_for('accounts.pots'))


@bp.route("/check", methods=("GET", "POST"))
def check():
    rows, token, error = [], None, None
    values = request.form if request.method == "POST" else {}
    serializer = URLSafeTimedSerializer(current_app.secret_key, salt="balance-check")
    if request.method == "POST":
        try:
            if request.form.get("action") == "save":
                payload = serializer.loads(request.form.get("token", ""), max_age=1800)
                matched = bool(payload["rows"]) and all(abs(row["actual"] - row["expected"]) < 0.005 for row in payload["rows"])
                record_checks(payload, request.form.getlist("adjust"), request.form.get("note", ""))
                flash("Balance check saved. Only the adjustments you selected were applied.", "success")
                return redirect(url_for("accounts.check", matched=1 if matched else 0))
            rows = preview_balances({str(a["id"]): request.form.get(f"actual_{a['id']}", "") for a in list_accounts(active_only=False)},request.form.get('through_date') or None)
            token = serializer.dumps(check_payload(rows))
        except BadSignature:
            error = "This preview expired. Enter balances again to create a new check."
        except ValueError as exc:
            error = str(exc)
    accounts = account_balances()
    if request.method == 'GET' and request.args.get('account_id',type=int):
        accounts = [a for a in accounts if a['id']==request.args.get('account_id',type=int)]
    return render_template("accounts/check.html", accounts=accounts, rows=rows, token=token, error=error, values=values, history=check_history()), (400 if error else 200)


def _account_form():
    from money_manager.utils.money import money_value
    kind = request.form.get("type", "")
    try:
        target = int(request.form["settlement_account_id"]) if kind == "credit_card" and request.form.get("settlement_account_id") else None
        day = int(request.form["settlement_day"]) if kind == "credit_card" and request.form.get("settlement_day") else None
    except ValueError:
        raise ValueError("Choose a settlement account and a day from 1 to 28.") from None
    return (request.form.get("name", ""), kind,
            money_value(request.form.get("opening_balance") or 0), target, day, request.form.get("logo") or None)


@bp.route("/new", methods=("GET", "POST"))
def new():
    if request.method == "POST":
        try:
            create_account(*_account_form())
        except (ValueError, IntegrityError) as error:
            message = "An account with that name already exists." if isinstance(error, IntegrityError) else str(error)
            return render_template("accounts/form.html", account=request.form, editing=False, accounts=list_accounts(), error=message), 400
        return redirect(url_for("accounts.index"))
    return render_template("accounts/form.html", account=None, editing=False, accounts=list_accounts())


@bp.route("/<int:account_id>/edit", methods=("GET", "POST"))
def edit(account_id):
    account = get_account(account_id)
    if not account:
        abort(404)
    if request.method == "POST":
        try:
            name, kind, balance, target, day, logo = _account_form()
            update_account(account_id, name, kind, balance, target, day, bool(request.form.get("is_active")), logo)
        except (ValueError, IntegrityError) as error:
            message = "An account with that name already exists." if isinstance(error, IntegrityError) else str(error)
            return render_template("accounts/form.html", account=request.form, editing=True, editing_account_id=account_id, accounts=list_accounts(active_only=False), error=message), 400
        return redirect(url_for("accounts.detail",account_id=account_id))
    return render_template("accounts/form.html", account=account, editing=True, editing_account_id=account_id, accounts=list_accounts(active_only=False))


@bp.post('/<int:account_id>/archive')
def archive(account_id):
    from money_manager.db.connection import get_db
    account=get_account(account_id)
    if not account:
        abort(404)
    db=get_db()
    with db:
        db.execute('UPDATE accounts SET is_active=0 WHERE id=?',(account_id,))
    flash('Account archived. Its history and balance are retained. You can reactivate it from Accounts.', 'success')
    return redirect(url_for('accounts.index'))
