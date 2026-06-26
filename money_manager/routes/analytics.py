from flask import Blueprint, render_template

from money_manager.services.analytics import cumulative_balance, expenses_by_category, largest_expenses, monthly_summary, weekday_spending


bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@bp.route("/")
def index():
    return render_template(
        "analytics.html",
        monthly=monthly_summary(),
        categories=expenses_by_category(),
        cumulative=cumulative_balance(),
        weekdays=weekday_spending(),
        largest=largest_expenses(),
    )
