from flask import Blueprint, current_app, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

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

    logo = (request.form.get("logo") or "").strip()
    if not logo:
        return existing_logo
    logo = logo.strip('"').strip("'")
    if logo.startswith(("http://", "https://", "/")):
        return logo
    if "\\" in logo or "/" in logo:
        logo = logo.replace("\\", "/").split("/")[-1]
    return url_for("static", filename=f"uploads/merchants/{logo}")


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
            return render_template("merchants/form.html", merchant=request.form, error=str(error)), 400
    return render_template("merchants/form.html", merchant=None)


@bp.route("/<int:merchant_id>/edit", methods=("GET", "POST"))
def edit(merchant_id):
    merchant = get_merchant(merchant_id)
    if request.method == "POST":
        try:
            update_merchant(merchant_id, request.form["name"], _logo_value(merchant["logo"]), request.form.get("website"), request.form.get("default_category"))
            return redirect(url_for("merchants.index"))
        except ValueError as error:
            return render_template("merchants/form.html", merchant=request.form, error=str(error)), 400
    return render_template("merchants/form.html", merchant=merchant)
