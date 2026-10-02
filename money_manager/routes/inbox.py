from flask import Blueprint, render_template

from money_manager.services.inbox import money_inbox


bp = Blueprint("inbox", __name__, url_prefix="/inbox")


@bp.get("/")
def index():
    return render_template("inbox.html", items=money_inbox())
