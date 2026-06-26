from flask import Blueprint, render_template

from money_manager.services.accounts import account_balances
from money_manager.services.analytics import dashboard_metrics, expenses_by_category, monthly_summary
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
    return render_template(
        "dashboard.html",
        metrics=dashboard_metrics(),
        accounts=account_balances(),
        loan_summary=loan_summary(),
        pending=list_pending()[:5],
        monthly=monthly_summary(),
        categories=expenses_by_category(),
    )
