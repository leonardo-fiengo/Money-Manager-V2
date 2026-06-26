from flask import Blueprint, jsonify

from money_manager.services.accounts import account_balances
from money_manager.services.analytics import cumulative_balance, dashboard_metrics, expenses_by_category, monthly_summary, weekday_spending
from money_manager.services.pending import list_pending


bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/dashboard")
def dashboard():
    return jsonify(
        metrics=dashboard_metrics(),
        accounts=account_balances(),
        pending=list_pending(),
        monthly=monthly_summary(),
        categories=expenses_by_category(),
    )


@bp.route("/analytics")
def analytics():
    return jsonify(
        monthly=monthly_summary(),
        categories=expenses_by_category(),
        cumulative=cumulative_balance(),
        weekdays=weekday_spending(),
    )
