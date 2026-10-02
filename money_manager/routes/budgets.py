from flask import Blueprint, redirect, render_template, request, url_for
from datetime import date

from money_manager.services.budgets import budget_summary, delete_budget, list_budgets, upsert_budget, current_month, copy_previous_budgets, list_budget_templates, save_budget_template, apply_budget_template
from money_manager.services.categories import list_categories
from money_manager.services.budgets import budget_suggestions
from money_manager.utils.filters import clean_amount


bp = Blueprint("budgets", __name__, url_prefix="/budgets")


def _safe_month(value):
    try:
        date.fromisoformat((value or "") + "-01")
        return value
    except ValueError:
        return current_month()


@bp.route("/", methods=("GET", "POST"))
def index():
    month = _safe_month(request.values.get("month"))
    if request.method == "POST":
        try:
            upsert_budget(
                {
                    "month": month,
                    "category_id": request.form["category_id"],
                    "amount": clean_amount(request.form.get("amount")),
                    "rollover": bool(request.form.get("rollover")),
                }
            )
            return redirect(url_for("budgets.index", month=month))
        except ValueError as error:
            return render_template(
                "budgets/index.html",
                budgets=list_budgets(month),
                categories=[c for c in list_categories() if c["type"] in {"expense", "any"}], suggestions=budget_suggestions(),
                summary=budget_summary(month),
                month=month,
                error=str(error),
                templates=list_budget_templates(),
            ), 400
    return render_template(
        "budgets/index.html",
        budgets=list_budgets(month),
        categories=[c for c in list_categories() if c["type"] in {"expense", "any"}], suggestions=budget_suggestions(),
        summary=budget_summary(month),
        month=month,
        templates=list_budget_templates(),
    )


@bp.post("/copy-previous")
def copy_previous():
    month = _safe_month(request.form.get("month"))
    try:
        copy_previous_budgets(month)
    except ValueError:
        month = current_month()
    return redirect(url_for("budgets.index", month=month))


@bp.post("/templates/save")
def template_save():
    month = _safe_month(request.form.get("month"))
    try:
        save_budget_template(request.form.get("name"), month)
    except ValueError as error:
        return render_template("budgets/index.html", budgets=list_budgets(month), categories=[c for c in list_categories() if c["type"] in {"expense", "any"}], suggestions=budget_suggestions(), summary=budget_summary(month), month=month, templates=list_budget_templates(), error=str(error)), 400
    return redirect(url_for("budgets.index", month=month))


@bp.post("/templates/apply")
def template_apply():
    month = _safe_month(request.form.get("month"))
    try:
        apply_budget_template(int(request.form.get("template_id") or 0), month)
    except ValueError as error:
        return render_template("budgets/index.html", budgets=list_budgets(month), categories=[c for c in list_categories() if c["type"] in {"expense", "any"}], suggestions=budget_suggestions(), summary=budget_summary(month), month=month, templates=list_budget_templates(), error=str(error)), 400
    return redirect(url_for("budgets.index", month=month))


@bp.route("/<int:budget_id>/delete", methods=("POST",))
def delete(budget_id):
    month = _safe_month(request.form.get("month"))
    delete_budget(budget_id)
    return redirect(url_for("budgets.index", month=month))
