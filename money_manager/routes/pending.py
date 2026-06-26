from flask import Blueprint, redirect, render_template, url_for

from money_manager.services.pending import execute_due_pending, list_pending, mark_posted


bp = Blueprint("pending", __name__, url_prefix="/pending")


@bp.route("/")
def index():
    return render_template("pending/index.html", pending=list_pending())


@bp.route("/execute-due", methods=("POST",))
def execute_due():
    execute_due_pending()
    return redirect(url_for("pending.index"))


@bp.route("/<int:transaction_id>/post", methods=("POST",))
def post(transaction_id):
    mark_posted(transaction_id)
    return redirect(url_for("pending.index"))
