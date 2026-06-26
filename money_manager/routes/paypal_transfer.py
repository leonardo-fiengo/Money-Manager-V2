from flask import Blueprint, render_template


bp = Blueprint("paypal_transfer", __name__, url_prefix="/paypal-transfer")


@bp.route("/")
def index():
    return render_template("paypal_transfer.html")
