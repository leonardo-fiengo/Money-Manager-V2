import base64
import io
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import current_app

from money_manager.db.connection import get_db, dict_factory
from money_manager.db.atomic import atomic
from money_manager.utils.money import storage_row, insert_row, MONEY_COLUMNS, to_minor


EXPORT_TABLES = [
    "accounts",
    "merchants",
    "categories",
    "contacts",
    "transactions",
    "recurring_rules",
    "loans",
    "loan_payments",
    "budgets",
    "payment_preferences",
    "balance_checks",
    "transaction_trash",
    "savings_pots",
    "import_batches",
    "import_rules",
    "transaction_import_hashes",
    "transaction_splits",
    "transaction_links",
    "transaction_tags",
    "pot_movements",
    "budget_templates",
    "import_profiles", "merchant_aliases", "finance_rules", "transaction_relationships",
    "reconciliation_sessions", "forecast_scenarios", "transaction_attachments",
    "net_worth_snapshots", "app_preferences", "inbox_dismissals", "recurring_occurrences", 'reconciliation_transactions',
    "pot_sources", "pot_movement_sources", "pot_spending",
    "local_profile",
    "taxes", "tax_payments", "tax_estimates",
]
LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}


def export_data():
    db = get_db()
    return {
        table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
        for table in EXPORT_TABLES
    }


def export_bundle():
    with atomic(get_db()):
        data = export_data()
    logos = {}
    for path in current_app.config["MERCHANT_LOGO_DIR"].iterdir():
        if path.is_file() and path.suffix.lower() in LOGO_EXTENSIONS:
            logos[path.name] = base64.b64encode(path.read_bytes()).decode("ascii")
    from money_manager.services.attachments import attachment_directory
    attachments={p.name:base64.b64encode(p.read_bytes()).decode('ascii') for p in attachment_directory().iterdir() if p.is_file()}
    return dict(format="money-manager", version=3, schema_version=14, exported_at=datetime.now(timezone.utc).isoformat(),
                data=data, merchant_logos=logos, attachments=attachments)


def create_snapshot(reason="daily"):
    """Consistent SQLite backup plus logos; daily snapshots are made once a day."""
    database = current_app.config["DATABASE"]
    if not database.exists() or not database.stat().st_size:
        return None
    directory = current_app.config["DATA_DIR"] / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    name = f"{reason}-{stamp}" + ("" if reason == "daily" else "-" + uuid4().hex[:8]) + ".zip"
    target = directory / name
    from money_manager.services.backup_encryption import encryption_config,encrypt_snapshot
    encrypted=bool(encryption_config())
    if encrypted: target=target.with_suffix('.mmbackup')
    if target.exists():
        return target
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "money_manager.sqlite3"
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(copy)) as destination:
            source.backup(destination)
        temporary = directory / (name + ".tmp")
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(copy, "money_manager.sqlite3")
                for logo in current_app.config["MERCHANT_LOGO_DIR"].iterdir():
                    if logo.is_file() and logo.suffix.lower() in LOGO_EXTENSIONS:
                        archive.write(logo, "merchants/" + logo.name)
                from money_manager.services.attachments import attachment_directory
                for attachment in attachment_directory().iterdir():
                    if attachment.is_file(): archive.write(attachment, 'attachments/'+attachment.name)
                with closing(sqlite3.connect(copy)) as snapshot_db:
                    schema=0
                    if snapshot_db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone():
                        schema=max((int(r[0].split('_')[0]) for r in snapshot_db.execute('SELECT name FROM schema_migrations')),default=0)
                archive.writestr('manifest.json',json.dumps(dict(format='money-manager',version=3,schema_version=schema)))
            if encrypted:
                temporary.write_bytes(encrypt_snapshot(temporary.read_bytes()))
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


def list_snapshots():
    directory = current_app.config["DATA_DIR"] / "backups"
    return [dict(name=p.name, size=p.stat().st_size) for p in sorted(directory.iterdir(), reverse=True) if p.suffix in {'.zip','.mmbackup'}] if directory.exists() else []


def read_backup(file,password=None):
    """Read JSON exports or local snapshots without extracting archive paths."""
    from money_manager.services.backup_encryption import MAGIC,decrypt_snapshot
    file.seek(0)
    if file.read(len(MAGIC))==MAGIC:
        file.seek(0)
        file=io.BytesIO(decrypt_snapshot(file.read(64*1024*1024+1),password))
    file.seek(0)
    if not zipfile.is_zipfile(file):
        file.seek(0)
        return json.load(file)
    file.seek(0)
    try:
        with zipfile.ZipFile(file) as archive:
            if sum(info.file_size for info in archive.infolist()) > 64 * 1024 * 1024:
                raise ValueError("This snapshot is too large.")
            database = archive.read("money_manager.sqlite3")
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "snapshot.sqlite3"
                path.write_bytes(database)
                with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                    db.row_factory = dict_factory
                    if db.execute("PRAGMA integrity_check").fetchone()["integrity_check"] != "ok":
                        raise ValueError("This snapshot database is damaged.")
                    tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    data = {table: db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                            for table in EXPORT_TABLES if table in tables}
            logos = {name.removeprefix("merchants/"): base64.b64encode(archive.read(name)).decode("ascii")
                     for name in archive.namelist() if name.startswith("merchants/") and Path(name).suffix.lower() in LOGO_EXTENSIONS}
            attachments={name.removeprefix('attachments/'):base64.b64encode(archive.read(name)).decode('ascii') for name in archive.namelist() if name.startswith('attachments/') and not name.endswith('/')}
            manifest=json.loads(archive.read('manifest.json')) if 'manifest.json' in archive.namelist() else dict(version=2)
            return dict(format="money-manager", version=manifest['version'],schema_version=manifest.get('schema_version',10), data=data, merchant_logos=logos,attachments=attachments)
    except (zipfile.BadZipFile, KeyError, sqlite3.Error) as error:
        raise ValueError("This file is not a valid Money Manager snapshot.") from error


def _load_rows(db, data):
    db.execute("PRAGMA defer_foreign_keys = ON")
    db.execute("DELETE FROM recurring_occurrences")
    for table in reversed(EXPORT_TABLES):
        db.execute(f"DELETE FROM {table}")
    for table in EXPORT_TABLES:
        allowed = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        rows = data.get(table, [])
        if not isinstance(rows, list):
            raise ValueError(f"Invalid {table} rows.")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"Invalid {table} row.")
            for column in MONEY_COLUMNS.get(table, ()):
                if column in row and column + "_minor" in row and to_minor(row[column]) != row[column + "_minor"]:
                    raise ValueError(f"Conflicting amounts in {table}.")
            stored = storage_row(table, row)
            if set(stored) - allowed:
                raise ValueError(f"Unrecognized columns in {table}.")
            for column in MONEY_COLUMNS.get(table, ()):
                minor = stored.get(column + "_minor")
                if type(minor) is not int or abs(minor) > 99999999900:
                    raise ValueError(f"Invalid amount in {table}.")
            if table == "transactions":
                from datetime import date
                from money_manager.utils.exchange import SUPPORTED_CURRENCIES
                date.fromisoformat(row["date"])
                if row.get("currency", "EUR") not in SUPPORTED_CURRENCIES:
                    raise ValueError("Unsupported currency in backup.")
            if table=='recurring_rules':
                if row.get('currency','EUR') not in {'EUR','USD','GBP','CHF'}:
                    raise ValueError('Unsupported recurring currency in backup.')
                if 'amount_eur_minor' not in stored:
                    if row.get('currency','EUR')!='EUR':
                        raise ValueError('Missing recurring EUR conversion in backup.')
                    stored['amount_eur_minor']=stored['amount_minor']
                if type(stored['amount_eur_minor']) is not int or stored['amount_eur_minor']<=0:
                    raise ValueError('Invalid recurring EUR amount.')
            if table=='local_profile' and row.get('avatar_data'):
                from money_manager.services.profile import profile_photo
                from werkzeug.datastructures import FileStorage
                photo=row['avatar_data']
                if not isinstance(photo,str) or len(photo)>3*1024*1024 or not photo.startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,')):
                    raise ValueError('Invalid profile photo in backup.')
                try:
                    content=base64.b64decode(photo.split(',',1)[1],validate=True)
                    checked=profile_photo(FileStorage(stream=io.BytesIO(content),filename='photo'))
                except (ValueError,TypeError): raise ValueError('Invalid profile photo in backup.') from None
                if checked!=photo: raise ValueError('Invalid profile photo type in backup.')
            if table in {'taxes','tax_payments'}:
                from datetime import date
                date.fromisoformat(row['due_date' if table=='taxes' else 'date'])
            if table=='tax_estimates':
                from money_manager.services.taxes import SOURCE
                try:
                    inputs=json.loads(row['inputs_json']);result=json.loads(row['result_json'])
                    if not isinstance(inputs,dict) or not isinstance(result,dict) or result.get('source')!=SOURCE or result.get('tax_year')!=row['tax_year']:
                        raise ValueError()
                    for key in ('income','deductions','credits','local_tax','withheld'):
                        if to_minor(inputs[key])<0: raise ValueError()
                    for key in ('taxable','gross','net','total','balance'): to_minor(result[key])
                    if not isinstance(result['breakdown'],list): raise ValueError()
                    for bracket in result['breakdown']:
                        for key in ('lower','rate','portion','tax'): to_minor(bracket[key])
                except (ValueError,TypeError,KeyError): raise ValueError('Invalid saved tax estimate in backup.') from None
            insert_row(db, table, stored)
    db.execute("INSERT OR IGNORE INTO recurring_occurrences SELECT recurring_rule_id, date FROM transactions WHERE recurring_rule_id IS NOT NULL")
    if db.execute("PRAGMA foreign_key_check").fetchone():
        raise ValueError("The backup contains missing accounts or other broken references.")
    if db.execute('SELECT 1 FROM transactions WHERE contact_id IS NOT NULL AND merchant_id IS NOT NULL').fetchone():
        raise ValueError('A transaction cannot have both a contact and a merchant.')
    if db.execute("""SELECT 1 FROM savings_pots p JOIN pot_sources s ON s.pot_id=p.id
        GROUP BY p.id HAVING SUM(s.reserved_minor)>p.reserved_minor""").fetchone():
        raise ValueError('Source reservations exceed their savings pot amounts.')
    if db.execute('''SELECT 1 FROM taxes t JOIN tax_payments p ON p.tax_id=t.id
        GROUP BY t.id HAVING SUM(p.amount_minor)>t.amount_minor''').fetchone():
        raise ValueError('Tax payments exceed their tax amount.')


def validate_backup(payload):
    if not isinstance(payload, dict) or type(payload.get('version',1)) is not int or payload.get("version", 1) not in {1, 2, 3} or type(payload.get('schema_version',11)) is not int or not 0<=payload.get('schema_version',11)<=14:
        raise ValueError("Choose a supported Money Manager JSON backup.")
    data = payload.get("data")
    required = {"accounts", "transactions", "categories", "merchants", "recurring_rules", "loans", "loan_payments"}
    if not isinstance(data, dict) or not required.issubset(data) or set(data) - set(EXPORT_TABLES):
        raise ValueError("The backup is incomplete or contains unknown tables.")
    logos = payload.get("merchant_logos", {})
    if not isinstance(logos, dict):
        raise ValueError("Invalid merchant logos.")
    parsed_logos = {}
    for name, encoded in logos.items():
        if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name or Path(name).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
            raise ValueError("Invalid logo filename.")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            raise ValueError("Invalid logo data.") from None
        if len(content) > 5 * 1024 * 1024:
            raise ValueError("A logo is too large.")
        parsed_logos[name] = content
    from money_manager.services.attachments import ALLOWED
    parsed_attachments={}
    if not isinstance(payload.get('attachments',{}),dict): raise ValueError('Invalid attachments.')
    for name,encoded in payload.get('attachments',{}).items():
        if not isinstance(name,str) or Path(name).name!=name or '/' in name or '\\' in name or Path(name).suffix.lower() not in ALLOWED: raise ValueError('Invalid attachment filename.')
        try: content=base64.b64decode(encoded,validate=True)
        except (ValueError,TypeError): raise ValueError('Invalid attachment data.') from None
        if len(content)>5*1024*1024: raise ValueError('An attachment is too large.')
        parsed_attachments[name]=content
    attachment_rows=data.get('transaction_attachments',[])
    if not isinstance(attachment_rows,list) or any(not isinstance(r,dict) for r in attachment_rows): raise ValueError('Invalid attachment records.')
    if any(r.get('storage_name') not in parsed_attachments for r in attachment_rows): raise ValueError('The backup is missing attachment files.')
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "validation.sqlite3"
        with closing(sqlite3.connect(current_app.config["DATABASE"])) as source, closing(sqlite3.connect(path)) as copy:
            source.backup(copy)
            copy.row_factory = dict_factory
            copy.execute("PRAGMA foreign_keys = ON")
            try:
                with atomic(copy):
                    _load_rows(copy, data)
            except (sqlite3.Error, KeyError, TypeError) as error:
                raise ValueError("The backup contains invalid or incomplete records.") from error
    return dict(payload=payload, logos=parsed_logos, attachments=parsed_attachments, accounts=len(data["accounts"]), transactions=len(data["transactions"]))


def restore_backup(payload):
    validated = validate_backup(payload)
    snapshot = create_snapshot("before-restore")
    db = get_db()
    directory = current_app.config["MERCHANT_LOGO_DIR"]
    previous = {name: (directory / name).read_bytes() if (directory / name).exists() else None for name in validated["logos"]}
    from money_manager.services.attachments import attachment_directory
    attachment_dir=attachment_directory()
    previous_files={name:(attachment_dir/name).read_bytes() if (attachment_dir/name).exists() else None for name in validated['attachments']}
    try:
        with atomic(db):
            _load_rows(db, payload["data"])
            for name, content in validated["logos"].items():
                (directory / name).write_bytes(content)
            for name,content in validated['attachments'].items(): (attachment_dir/name).write_bytes(content)
    except Exception:
        for name, content in previous.items():
            if content is None:
                (directory / name).unlink(missing_ok=True)
            else:
                (directory / name).write_bytes(content)
        for name,content in previous_files.items():
            if content is None: (attachment_dir/name).unlink(missing_ok=True)
            else: (attachment_dir/name).write_bytes(content)
        raise
    return snapshot
