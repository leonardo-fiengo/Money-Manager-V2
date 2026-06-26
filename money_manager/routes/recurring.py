from flask import Blueprint, redirect, render_template, request, url_for

from money_manager.services.accounts import list_accounts
from money_manager.services.categories import list_categories
from money_manager.services.merchants import list_merchants
from money_manager.services.recurring import create_rule, delete_rule, generate_due_recurring, get_rule, list_rules, update_rule
from money_manager.utils.filters import clean_amount


bp = Blueprint("recurring", __name__, url_prefix="/recurring")


def _form_data():
    return {
        "name": request.form["name"],
        "type": request.form["type"],
        "amount": clean_amount(request.form.get("amount")),
        "category": request.form.get("category"),
        "description": request.form.get("description"),
        "account_id": int(request.form["account_id"]),
        "merchant_id": int(request.form["merchant_id"]) if request.form.get("merchant_id") else None,
        "visual_mode": request.form.get("visual_mode", "auto"),
        "frequency": request.form["frequency"],
        "next_due_date": request.form["next_due_date"],
        "is_active": bool(request.form.get("is_active", True)),
    }


def _form_context(rule=None, error=None):
    return {
        "rule": rule,
        "accounts": list_accounts(),
        "merchants": list_merchants(),
        "categories": list_categories(),
        "error": error,
    }


@bp.route("/")
def index():
    return render_template("recurring/index.html", rules=list_rules())


@bp.route("/new", methods=("GET", "POST"))
def new():
    if request.method == "POST":
        try:
            create_rule(_form_data())
            return redirect(url_for("recurring.index"))
        except ValueError as error:
            return render_template("recurring/form.html", **_form_context(request.form, str(error))), 400
    return render_template("recurring/form.html", **_form_context())


@bp.route("/<int:rule_id>/edit", methods=("GET", "POST"))
def edit(rule_id):
    rule = get_rule(rule_id)
    if request.method == "POST":
        try:
            update_rule(rule_id, _form_data())
            return redirect(url_for("recurring.index"))
        except ValueError as error:
            return render_template("recurring/form.html", **_form_context(request.form, str(error))), 400
    return render_template("recurring/form.html", **_form_context(rule))


@bp.route("/generate", methods=("POST",))
def generate():
    generate_due_recurring()
    return redirect(url_for("pending.index"))


@bp.route("/<int:rule_id>/delete", methods=("POST",))
def delete(rule_id):
    delete_rule(rule_id)
    return redirect(url_for("recurring.index"))
