from flask import Blueprint, redirect, render_template, request, url_for

from money_manager.services.categories import create_category, get_category, list_categories, update_category


bp = Blueprint("categories", __name__, url_prefix="/categories")


def _form_data():
    return {
        "name": request.form["name"],
        "type": request.form["type"],
        "color": request.form.get("color"),
        "icon": request.form.get("icon"),
        "is_active": bool(request.form.get("is_active", True)),
    }


@bp.route("/")
def index():
    return render_template("categories/index.html", categories=list_categories(active_only=False))


@bp.route("/new", methods=("GET", "POST"))
def new():
    if request.method == "POST":
        try:
            create_category(_form_data())
            return redirect(url_for("categories.index"))
        except ValueError as error:
            return render_template("categories/form.html", category=request.form, error=str(error)), 400
    return render_template("categories/form.html", category=None)


@bp.route("/<int:category_id>/edit", methods=("GET", "POST"))
def edit(category_id):
    category = get_category(category_id)
    if request.method == "POST":
        try:
            update_category(category_id, _form_data())
            return redirect(url_for("categories.index"))
        except ValueError as error:
            return render_template("categories/form.html", category=request.form, error=str(error)), 400
    return render_template("categories/form.html", category=category)
