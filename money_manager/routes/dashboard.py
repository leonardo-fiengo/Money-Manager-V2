from flask import Blueprint, render_template, request

from money_manager.services.accounts import account_balances
from money_manager.services.analytics import cumulative_balance, dashboard_metrics, dashboard_period, six_month_flow
from money_manager.services.planning import upcoming_overview
from money_manager.services.budgets import list_budgets
from money_manager.services.inbox import money_inbox
from money_manager.services.history import dashboard_widgets


bp = Blueprint("dashboard", __name__)


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

    upcoming = upcoming_overview()
    budget_preview = list_budgets()

    return render_template(
        "dashboard.html",
        metrics=dashboard_metrics(period["start"], period["end"]),
        period=period,
        flow_trend=six_month_flow(),
        upcoming=upcoming,
        accounts=accounts,
        account_sort=account_sort,
        budget_preview=budget_preview,
        inbox_items=money_inbox(budget_preview, upcoming),
        balance_trend=[row["balance"] for row in cumulative_balance()[-30:]],
        widgets=dashboard_widgets(),
    )
