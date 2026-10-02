from flask import Blueprint, flash, redirect, render_template, request, url_for

from money_manager.services.preferences import payment_accounts, payment_preference, save_payment_preference
from money_manager.services.history import dashboard_widgets, save_widgets


bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=("GET", "POST"))
def index():
    error = None
    if request.method == "POST":
        try:
            if request.form.get('action')=='widgets':
                save_widgets(request.form.getlist('widgets'))
                flash('Dashboard preferences saved.', 'success')
                return redirect(url_for('settings.index',_anchor='dashboard'))
            save_payment_preference(request.form.get("mode"), request.form.get("account_id"))
            flash("Default payment account saved.", "success")
            return redirect(url_for("settings.index", _anchor="payments"))
        except ValueError as exc:
            error = str(exc)
    preference = payment_preference() if not error else {
        "mode": request.form.get("mode"), "account_id": request.form.get("account_id", type=int)
    }
    return render_template("settings.html", preference=preference, payment_accounts=payment_accounts(), widgets=dashboard_widgets(), error=error), (400 if error else 200)
