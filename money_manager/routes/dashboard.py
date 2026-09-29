from flask import Blueprint, render_template, request

from money_manager.services.accounts import account_balances
from money_manager.services.analytics import dashboard_metrics, expenses_by_category, monthly_summary, dashboard_period
from money_manager.services.planning import upcoming_overview
from money_manager.services.loans import loan_summary
from money_manager.services.pending import execute_due_pending, list_pending
from money_manager.services.recurring import generate_due_recurring


bp = Blueprint("dashboard", __name__)


@bp.before_app_request
def run_scheduled_tasks():
    generate_due_recurring()
    execute_due_pending()


@bp.route("/")
def index():
    period = dashboard_period(request.args.get("period", "month"))
    account_sort = request.args.get("account_sort", "name")
    if account_sort not in {"name", "amount"}:
        account_sort = "name"

    accounts = account_balances()
    if account_sort == "amount":
        accounts = sorted(accounts, key=lambda account: account["balance"], reverse=True)
    else:
        accounts = sorted(accounts, key=lambda account: account["name"].lower())

    return render_template(
        "dashboard.html",
        metrics=dashboard_metrics(period["start"], period["end"]),
        period=period,
        upcoming=upcoming_overview(),
        accounts=accounts,
        account_sort=account_sort,
        loan_summary=loan_summary(),
        pending=list_pending()[:5],
        monthly=monthly_summary(period["start"], period["end"]),
        categories=expenses_by_category(period["start"], period["end"]),
    )
