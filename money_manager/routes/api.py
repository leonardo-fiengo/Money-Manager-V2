from flask import Blueprint, jsonify, request

from money_manager.services.accounts import account_balances
from money_manager.services.analytics import cumulative_balance, dashboard_metrics, expenses_by_category, monthly_summary, weekday_spending, dashboard_period
from money_manager.services.pending import list_pending


bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/dashboard")
def dashboard():
    period = dashboard_period(request.args.get("period", "month"))
    return jsonify(
        metrics=dashboard_metrics(period["start"], period["end"]),
        accounts=account_balances(),
        pending=list_pending(),
        monthly=monthly_summary(period["start"], period["end"]),
        categories=expenses_by_category(period["start"], period["end"]),
    )


@bp.route("/analytics")
def analytics():
    return jsonify(
        monthly=monthly_summary(),
        categories=expenses_by_category(),
        cumulative=cumulative_balance(),
        weekdays=weekday_spending(),
    )
