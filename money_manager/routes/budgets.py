from flask import Blueprint, redirect, render_template, request, url_for

from money_manager.services.budgets import budget_summary, delete_budget, list_budgets, upsert_budget, current_month
from money_manager.services.categories import list_categories
from money_manager.utils.filters import clean_amount


bp = Blueprint("budgets", __name__, url_prefix="/budgets")


@bp.route("/", methods=("GET", "POST"))
def index():
    month = request.values.get("month") or current_month()
    if request.method == "POST":
        try:
            upsert_budget(
                {
                    "month": month,
                    "category_id": request.form["category_id"],
                    "amount": clean_amount(request.form.get("amount")),
                }
            )
            return redirect(url_for("budgets.index", month=month))
        except ValueError as error:
            return render_template(
                "budgets/index.html",
                budgets=list_budgets(month),
                categories=list_categories(),
                summary=budget_summary(month),
                month=month,
                error=str(error),
            ), 400
    return render_template(
        "budgets/index.html",
        budgets=list_budgets(month),
        categories=list_categories(),
        summary=budget_summary(month),
        month=month,
    )


@bp.route("/<int:budget_id>/delete", methods=("POST",))
def delete(budget_id):
    month = request.form.get("month") or current_month()
    delete_budget(budget_id)
    return redirect(url_for("budgets.index", month=month))
