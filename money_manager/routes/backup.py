from datetime import datetime

from flask import Blueprint, jsonify, render_template

from money_manager.services.backup import export_data


bp = Blueprint("backup", __name__, url_prefix="/backup")


@bp.route("/")
def index():
    return render_template("backup.html")


@bp.route("/export.json")
def export_json():
    response = jsonify(exported_at=datetime.utcnow().isoformat(timespec="seconds") + "Z", data=export_data())
    response.headers["Content-Disposition"] = "attachment; filename=money-manager-backup.json"
    return response
