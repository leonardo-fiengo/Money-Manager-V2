import csv
import hashlib
import io
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from money_manager.db.connection import get_db
from money_manager.services.transactions import create_transaction
from money_manager.utils.exchange import SUPPORTED_CURRENCIES


def list_rules():
    return get_db().execute("SELECT r.*, m.name AS merchant_name FROM import_rules r LEFT JOIN merchants m ON m.id = r.merchant_id ORDER BY r.id DESC").fetchall()


def save_rule(needle, merchant_id=None, category=None):
    needle = (needle or "").strip()
    if not needle or len(needle) > 100 or not (merchant_id or category):
        raise ValueError("Enter matching text and a merchant or category.")
    db = get_db()
    if merchant_id and not db.execute("SELECT 1 FROM merchants WHERE id = ?", (merchant_id,)).fetchone():
        raise ValueError("Choose an existing merchant.")
    if category and not db.execute("SELECT 1 FROM categories WHERE name = ?", (category,)).fetchone():
        raise ValueError("Choose an existing category.")
    db.execute("INSERT INTO import_rules (needle, merchant_id, category) VALUES (?, ?, ?)", (needle, merchant_id or None, category or None))
    db.commit()


def delete_rule(rule_id):
    db = get_db()
    db.execute("DELETE FROM import_rules WHERE id = ?", (rule_id,))
    db.commit()


def create_batch(file, account_id):
    db = get_db()
    if not db.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone():
        raise ValueError("Choose an existing account.")
    raw = file.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError("CSV files must be smaller than 5 MB.")
    try:
        encoding = "utf-16" if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else "utf-8-sig"
        content = raw.decode(encoding)
    except UnicodeDecodeError:
        encoding = "cp1252"
        content = raw.decode("cp1252")
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    headers = [h.strip() for h in (reader.fieldnames or []) if h]
    if len(headers) < 2 or len(set(headers)) != len(headers):
        raise ValueError("The CSV needs distinct column headings.")
    rows = []
    for row in reader:
        if len(rows) >= 5000:
            raise ValueError("Import at most 5,000 rows per file.")
        if None in row:
            raise ValueError("A row has more values than the column headings.")
        if any((value or "").strip() for value in row.values()):
            rows.append({(key or "").strip(): (value or "").strip() for key, value in row.items()})
    if not rows:
        raise ValueError("The CSV has no transaction rows.")
    cursor = db.execute("INSERT INTO import_batches (account_id, filename, headers_json, rows_json) VALUES (?, ?, ?, ?)",
                        (account_id, (file.filename or "transactions.csv")[:150], json.dumps(headers), json.dumps(rows)))
    db.commit()
    db.execute('UPDATE import_batches SET encoding=? WHERE id=?', (encoding,cursor.lastrowid))
    profile=db.execute('SELECT * FROM import_profiles WHERE (account_id=? OR account_id IS NULL) AND headers_json=? ORDER BY account_id IS NOT NULL DESC,id DESC LIMIT 1', (account_id,json.dumps(headers))).fetchone()
    db.commit()
    if profile:
        save_mapping(cursor.lastrowid,json.loads(profile['mapping_json']))
    return cursor.lastrowid


def get_batch(batch_id):
    return get_db().execute("SELECT b.*, a.name AS account_name FROM import_batches b JOIN accounts a ON a.id = b.account_id WHERE b.id = ?", (batch_id,)).fetchone()


def save_mapping(batch_id, mapping):
    batch = get_batch(batch_id)
    if not batch or batch["status"] != "mapping":
        raise ValueError("This import is no longer awaiting column mapping.")
    headers = set(json.loads(batch["headers_json"]))
    if mapping.get("date") not in headers or mapping.get("description") not in headers:
        raise ValueError("Map a date and description column.")
    if mapping.get("amount") not in headers and not (mapping.get("debit") in headers and mapping.get("credit") in headers):
        raise ValueError("Map an amount column or both debit and credit columns.")
    for key in ("currency", "debit", "credit"):
        if mapping.get(key) and mapping[key] not in headers:
            raise ValueError("Choose columns from this file.")
    if mapping.get("date_format") not in {"ymd", "dmy", "mdy", "dmy_dot"}:
        raise ValueError("Choose a date format.")
    if (mapping.get("expense_sign") or "negative") not in {"negative", "positive"}:
        raise ValueError("Choose how expenses appear in the amount column.")
    db = get_db()
    db.execute("UPDATE import_batches SET mapping_json = ?, status = 'review' WHERE id = ?", (json.dumps(mapping), batch_id))
    db.commit()


def _date(value, date_format):
    value = (value or "").strip()
    try:
        if date_format == "ymd":
            return datetime.strptime(value[:10], "%Y-%m-%d").date().isoformat()
        pattern = {"dmy": "%d/%m/%Y", "mdy": "%m/%d/%Y", "dmy_dot": "%d.%m.%Y"}[date_format]
        return datetime.strptime(value, pattern).date().isoformat()
    except ValueError:
        raise ValueError(f"Invalid date: {value}") from None


def _number(value):
    value = (value or "").strip().replace("€", "").replace("£", "").replace("$", "").replace(" ", "")
    if not value:
        return Decimal("0")
    if "," in value and "." in value:
        value = value.replace(".", "").replace(",", ".") if value.rfind(",") > value.rfind(".") else value.replace(",", "")
    elif "," in value:
        value = value.replace(",", "") if len(value.rsplit(",", 1)[-1]) == 3 else value.replace(",", ".")
    elif "." in value and len(value.rsplit(".", 1)[-1]) == 3:
        value = value.replace(".", "")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"Invalid amount: {value}") from None
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError("Amounts need at most two decimal places.")
    return amount


def _fingerprint(account_id, item):
    description = re.sub(r"\s+", " ", item["description"].casefold()).strip()
    value = f'{account_id}|{item["date"]}|{item["type"]}|{item["amount"]:.2f}|{item["currency"]}|{description}'
    return hashlib.sha256(value.encode()).hexdigest()


def _suggest(description):
    db = get_db()
    folded = description.casefold()
    for rule in list_rules():
        if rule["needle"].casefold() in folded:
            merchant = db.execute("SELECT default_category FROM merchants WHERE id = ?", (rule["merchant_id"],)).fetchone() if rule["merchant_id"] else None
            return rule["merchant_id"], rule["category"] or (merchant["default_category"] if merchant else None)
    from money_manager.services.rules import merchant_match
    merchant=merchant_match(description)
    if merchant:
        return merchant['id'],merchant['default_category']
    return None, None


def preview_batch(batch_id):
    batch = get_batch(batch_id)
    if not batch or not batch["mapping_json"]:
        raise ValueError("Map columns before reviewing this import.")
    mapping = json.loads(batch["mapping_json"])
    db = get_db()
    results = []
    seen = set()
    for index, row in enumerate(json.loads(batch["rows_json"])):
        try:
            date = _date(row[mapping["date"]], mapping["date_format"])
            description = (row[mapping["description"]] or "").strip()
            if not description:
                raise ValueError("Description is empty.")
            currency = (row.get(mapping.get("currency"), "") or mapping.get("default_currency") or "EUR").upper()
            if currency not in SUPPORTED_CURRENCIES:
                raise ValueError(f"Unsupported currency: {currency}")
            separate_columns = not mapping.get("amount")
            if not separate_columns:
                signed = _number(row[mapping["amount"]])
            else:
                signed = _number(row[mapping["credit"]]) - _number(row[mapping["debit"]])
            if not signed:
                raise ValueError("Amount is zero.")
            income = signed > 0 if separate_columns or (mapping.get("expense_sign") or "negative") == "negative" else signed < 0
            item = dict(date=date, description=description, type="income" if income else "expense", amount=float(abs(signed)), currency=currency, account_id=batch["account_id"])
            item["merchant_id"], item["category"] = _suggest(description)
            from money_manager.services.rules import apply_rules
            original_item=dict(item)
            item=apply_rules(item)
            fingerprint = _fingerprint(batch["account_id"], original_item)
            candidate = db.execute("SELECT description FROM transactions WHERE account_id = ? AND date = ? AND type = ? AND amount = ? AND currency = ?", (batch["account_id"], date, item["type"], item["amount"], currency)).fetchall()
            prior = db.execute("SELECT 1 FROM transaction_import_hashes WHERE fingerprint = ? LIMIT 1", (fingerprint,)).fetchone()
            duplicate = bool(prior or fingerprint in seen or any(re.sub(r"\s+", " ", (c["description"] or "").casefold()).strip() == re.sub(r"\s+", " ", description.casefold()).strip() for c in candidate))
            seen.add(fingerprint)
            results.append(dict(index=index, item=item, fingerprint=fingerprint, duplicate=duplicate, error=None))
        except ValueError as error:
            results.append(dict(index=index, item=None, fingerprint=None, duplicate=False, error=str(error)))
    return results


def confirm_batch(batch_id, selected, overrides=None, categories=None, remember=None):
    batch = get_batch(batch_id)
    if not batch or batch["status"] != "review":
        raise ValueError("This import has already been completed.")
    preview = preview_batch(batch_id)
    chosen = {int(i) for i in selected}
    overrides = {int(i) for i in (overrides or [])}
    categories = categories or {}
    remember = {int(i) for i in (remember or [])}
    valid_categories = {row["name"] for row in get_db().execute("SELECT name FROM categories")}
    unknown = chosen - {row["index"] for row in preview}
    if unknown:
        raise ValueError("Choose rows from this import.")
    for row in preview:
        if row["index"] in chosen and (row["error"] or (row["duplicate"] and row["index"] not in overrides)):
            raise ValueError("Review invalid and duplicate rows before confirming.")
        if row["index"] in chosen and categories.get(row["index"], "") not in valid_categories | {""}:
            raise ValueError("Choose existing categories for imported rows.")
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT status FROM import_batches WHERE id = ?", (batch_id,)).fetchone()["status"] != "review":
            raise ValueError("This import has already been completed.")
        count = 0
        for row in preview:
            if row["index"] not in chosen:
                continue
            if row["index"] not in overrides and db.execute("SELECT 1 FROM transaction_import_hashes WHERE fingerprint = ? LIMIT 1", (row["fingerprint"],)).fetchone():
                raise ValueError("A selected transaction was imported by another batch. Review duplicates again.")
            item = dict(row["item"])
            choice = categories.get(row["index"], item["category"])
            item["category"] = choice or None
            if item.get('ignored'):
                continue
            tx_id = create_transaction(item, commit=False)
            from money_manager.services.transaction_details import save_tags
            if item.get('tags'):
                for tag in dict.fromkeys(t.strip() for t in item['tags'].split(',') if t.strip()):
                    db.execute('INSERT OR IGNORE INTO transaction_tags(transaction_id,tag) VALUES(?,?)',(tx_id,tag))
            db.execute('UPDATE transactions SET is_subscription=? WHERE id=?',(int(item.get('is_subscription',False)),tx_id))
            db.execute("INSERT INTO transaction_import_hashes (fingerprint, transaction_id, batch_id) VALUES (?, ?, ?)", (row["fingerprint"], tx_id, batch_id))
            if row["index"] in remember and item["category"] and item["category"] != row["item"]["category"]:
                db.execute("INSERT INTO import_rules (needle, category) VALUES (?, ?)", (item["description"][:100], item["category"]))
            count += 1
        ids=[r['transaction_id'] for r in db.execute('SELECT transaction_id FROM transaction_import_hashes WHERE batch_id=?',(batch_id,))]
        originals={str(tx_id):dict(db.execute('SELECT * FROM transactions WHERE id=?',(tx_id,)).fetchone()) for tx_id in ids}
        details={str(tx_id):_batch_details(db,tx_id) for tx_id in ids}
        db.execute("UPDATE import_batches SET status = 'done',original_json=? WHERE id = ?", (json.dumps(dict(transactions=originals,details=details)),batch_id))
        db.commit()
        return count
    except Exception:
        db.rollback()
        raise


def save_profile(batch_id,name):
    batch=get_batch(batch_id)
    name=(name or '').strip()
    if not batch or not batch['mapping_json'] or not name or len(name)>100:
        raise ValueError('Map the columns first and choose a profile name under 100 characters.')
    db=get_db()
    db.execute('INSERT INTO import_profiles(name,account_id,headers_json,mapping_json) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET account_id=excluded.account_id,headers_json=excluded.headers_json,mapping_json=excluded.mapping_json',(name,batch['account_id'],batch['headers_json'],batch['mapping_json']))
    db.commit()


def suggested_mapping(batch):
    headers=json.loads(batch['headers_json'])
    aliases={'date':['date','completed date','started date','booking date','data','data operazione','data contabile'], 'description':['description','merchant','details','payee','descrizione','esercente','causale'], 'amount':['amount','total','importo'], 'debit':['debit','paid out','addebito','uscite'], 'credit':['credit','paid in','accredito','entrate'], 'currency':['currency','valuta']}
    mapping={key:next((h for h in headers if h.casefold() in candidates),'') for key,candidates in aliases.items()}
    samples=[r.get(mapping['date'],'') for r in json.loads(batch['rows_json'])[:30]]
    mapping['date_format']='ymd'
    for value in samples:
        if len(value)>=10 and value[2:3] in {'/','.'}:
            mapping['date_format']='dmy_dot' if value[2]=='.' else ('mdy' if value[:2].isdigit() and int(value[:2])<=12 and value[3:5].isdigit() and int(value[3:5])>12 else 'dmy')
            break
    return mapping


def rollback_batch(batch_id):
    from money_manager.db.atomic import atomic
    from money_manager.services.transactions import delete_transaction
    db=get_db()
    with atomic(db):
        batch=get_batch(batch_id)
        if not batch or batch['status']!='done' or not batch['original_json']:
            raise ValueError('Only a completed import with an unchanged history can be rolled back.')
        saved=json.loads(batch['original_json'])
        originals=saved.get('transactions',saved)
        for tx_id,original in originals.items():
            current=db.execute('SELECT * FROM transactions WHERE id=?',(tx_id,)).fetchone()
            if current and current!=original:
                raise ValueError('An imported transaction was edited or reconciled. Review those changes before rollback.')
            if current and saved.get('details',{}).get(tx_id)!=_batch_details(db,int(tx_id)):
                raise ValueError('Imported tags, splits, receipts, or settlements changed. Review those changes before rollback.')
            if db.execute('SELECT 1 FROM transaction_links WHERE source_transaction_id=? OR related_transaction_id=?',(tx_id,tx_id)).fetchone() or db.execute("SELECT 1 FROM transaction_relationships WHERE kind!='credit_card_settlement' AND (source_transaction_id=? OR related_transaction_id=?)",(tx_id,tx_id)).fetchone():
                raise ValueError('An imported transaction has a linked payment. Unlink it before rollback.')
            if db.execute("SELECT 1 FROM transactions WHERE settlement_for_transaction_id=? AND status='posted'",(tx_id,)).fetchone():
                raise ValueError('An imported card payment has settled. It cannot be rolled back.')
        for tx_id in originals:
            delete_transaction(int(tx_id),commit=False)
        db.execute("UPDATE import_batches SET status='rolled_back' WHERE id=?",(batch_id,))
    return len(originals)


def _batch_details(db,tx_id):
    details={table:db.execute(f'SELECT * FROM {table} WHERE transaction_id=? ORDER BY id',(tx_id,)).fetchall() for table in ('transaction_tags','transaction_splits','transaction_attachments')}
    details['settlements']=db.execute('SELECT * FROM transactions WHERE settlement_for_transaction_id=? ORDER BY id',(tx_id,)).fetchall()
    return details
