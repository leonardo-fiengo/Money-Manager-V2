from flask import Blueprint, render_template

from money_manager.services.cockpit import cockpit_summary


bp = Blueprint("inbox", __name__, url_prefix="/inbox")


@bp.get("/")
def index():
    return render_template("inbox.html", items=cockpit_summary()['actions'])
