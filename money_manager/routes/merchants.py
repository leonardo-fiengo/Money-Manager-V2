from flask import Blueprint, current_app, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from money_manager.services.categories import list_categories
from money_manager.services.merchants import create_merchant, get_merchant, list_merchants, update_merchant


bp = Blueprint("merchants", __name__, url_prefix="/merchants")
ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}


def _logo_value(existing_logo=None):
    uploaded = request.files.get("logo_file")
    if uploaded and uploaded.filename:
        filename = secure_filename(uploaded.filename)
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in ALLOWED_LOGO_EXTENSIONS:
            raise ValueError("Logo must be png, jpg, jpeg, gif, webp, or svg.")
        target = current_app.config["MERCHANT_LOGO_DIR"] / filename
        uploaded.save(target)
        return url_for("static", filename=f"uploads/merchants/{filename}")

    return existing_logo


def _form_context(merchant=None, error=None):
    return {
        "merchant": merchant,
        "categories": list_categories(),
        "error": error,
    }


@bp.route("/")
def index():
    return render_template("merchants/index.html", merchants=list_merchants())


@bp.route("/new", methods=("GET", "POST"))
def new():
    if request.method == "POST":
        try:
            create_merchant(request.form["name"], _logo_value(), request.form.get("website"), request.form.get("default_category"))
            return redirect(url_for("merchants.index"))
        except ValueError as error:
            return render_template("merchants/form.html", **_form_context(request.form, str(error))), 400
    return render_template("merchants/form.html", **_form_context())


@bp.route("/<int:merchant_id>/edit", methods=("GET", "POST"))
def edit(merchant_id):
    merchant = get_merchant(merchant_id)
    if request.method == "POST":
        try:
            update_merchant(merchant_id, request.form["name"], _logo_value(merchant["logo"]), request.form.get("website"), request.form.get("default_category"))
            return redirect(url_for("merchants.index"))
        except ValueError as error:
            form_merchant = dict(request.form, logo=merchant["logo"])
            return render_template("merchants/form.html", **_form_context(form_merchant, str(error))), 400
    return render_template("merchants/form.html", **_form_context(merchant))
