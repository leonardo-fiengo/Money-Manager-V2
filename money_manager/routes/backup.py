import json
from uuid import uuid4

from flask import Blueprint, jsonify, render_template, request, session, current_app, redirect, url_for, flash, send_from_directory, abort
from money_manager.services.backup import export_bundle, validate_backup, restore_backup, list_snapshots, read_backup
from money_manager.services.backup_encryption import configure_encryption, encryption_config

bp = Blueprint("backup", __name__, url_prefix="/backup")


@bp.route("/", methods=("GET", "POST"))
def index():
    error, preview = None, None
    if request.method == "POST":
        try:
            if request.form.get('action')=='encrypt':
                configure_encryption(request.form.get('password') or '')
                from money_manager.services.backup import create_snapshot
                create_snapshot(reason='encrypted')
                flash('Encrypted snapshots enabled. Keep your passphrase to restore on another installation.', 'success')
                return redirect(url_for('backup.index'))
            directory = current_app.config["DATA_DIR"] / "restore-previews"
            directory.mkdir(exist_ok=True)
            if request.form.get("action") == "restore":
                name = session.get("restore_preview")
                if not name or request.form.get("preview_id") != name:
                    raise ValueError("Upload and review a backup before restoring.")
                path = directory / (name + ".json")
                if not path.exists():
                    raise ValueError("This preview is no longer available. Upload your backup again.")
                snapshot = restore_backup(json.loads(path.read_text(encoding="utf-8")))
                path.unlink()
                session.pop("restore_preview", None)
                flash(f"Backup restored. Your previous data is saved in {snapshot.name}.", "success")
                return redirect(url_for("backup.index"))
            file = request.files.get("file")
            if not file or not (file.filename or "").lower().endswith((".json", ".zip", '.mmbackup')):
                raise ValueError("Choose a Money Manager JSON backup, ZIP snapshot, or encrypted .mmbackup file.")
            payload = read_backup(file,request.form.get('password') or None)
            validated = validate_backup(payload)
            name = uuid4().hex
            (directory / (name + ".json")).write_text(json.dumps(payload), encoding="utf-8")
            session["restore_preview"] = name
            preview = dict(accounts=validated["accounts"], transactions=validated["transactions"], logos=len(validated["logos"]), id=name)
        except (ValueError, UnicodeError, OSError) as exc:
            error = str(exc) if not isinstance(exc, json.JSONDecodeError) else "This file is not a valid JSON backup."
    return render_template("backup.html", snapshots=list_snapshots(), error=error, preview=preview, encrypted=bool(encryption_config())), (400 if error else 200)


@bp.get("/export.json")
def export_json():
    response = jsonify(export_bundle())
    response.headers["Content-Disposition"] = "attachment; filename=money-manager-backup.json"
    return response


@bp.get("/snapshots/<name>")
def snapshot_download(name):
    if name not in {row["name"] for row in list_snapshots()}:
        abort(404)
    return send_from_directory(current_app.config["DATA_DIR"] / "backups", name, as_attachment=True)
