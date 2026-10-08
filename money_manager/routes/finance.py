import json
from flask import Blueprint, abort, flash, redirect, render_template, request, send_from_directory, url_for
from money_manager.db.connection import get_db
from money_manager.services.accounts import list_accounts
from money_manager.services.categories import list_categories
from money_manager.services.merchants import list_merchants
from money_manager.services.rules import list_finance_rules, parse_rule, preview_rule, save_finance_rule, save_alias
from money_manager.services.relationships import transfer_candidates, match_transfer, unmatch_transfer
from money_manager.services.importing import rollback_batch, save_profile
from money_manager.services.reconciliation import reconciliation_history, reopen_session
from money_manager.services.history import net_worth_history
from money_manager.services.subscriptions import track_subscription
from money_manager.services.attachments import attachment_directory

bp = Blueprint('finance', __name__, url_prefix='/tools')


@bp.get('/')
def index():
    return redirect(url_for('settings.index'))


@bp.route('/rules', methods=['GET', 'POST'])
def rules():
    error, preview = None, None
    if request.method == 'POST':
        try:
            if request.form.get('action') == 'preview':
                preview = preview_rule(request.form)
            else:
                save_finance_rule(request.form)
                flash('Rule saved. Future imports will use it.', 'success')
                return redirect(url_for('finance.rules'))
        except ValueError as exc:
            error = str(exc)
    return render_template('finance/rules.html', rules=list_finance_rules(), preview=preview, values=request.form if request.method == 'POST' else request.args,
                           accounts=list_accounts(False), merchants=list_merchants(), categories=list_categories(), error=error), (400 if error else 200)


@bp.post('/rules/<int:rule_id>/toggle')
def toggle_rule(rule_id):
    db = get_db()
    db.execute('UPDATE finance_rules SET is_active=1-is_active WHERE id=?', (rule_id,))
    db.commit()
    return redirect(url_for('finance.rules'))


@bp.get('/imports')
def imports():
    rows = get_db().execute('SELECT b.*,a.name AS account_name,(SELECT COUNT(*) FROM transaction_import_hashes h WHERE h.batch_id=b.id) AS count FROM import_batches b JOIN accounts a ON a.id=b.account_id ORDER BY b.id DESC').fetchall()
    return render_template('finance/imports.html', batches=rows, profiles=get_db().execute('SELECT p.*,a.name AS account_name FROM import_profiles p LEFT JOIN accounts a ON a.id=p.account_id ORDER BY p.name').fetchall())


@bp.get('/recovery')
def recovery():
    rows=[]
    for row in get_db().execute('SELECT * FROM transaction_trash WHERE restored_at IS NULL ORDER BY id DESC LIMIT 100'):
        payload=json.loads(row['payload'])
        transactions=payload if isinstance(payload,list) else payload['transactions']
        rows.append(dict(row,transactions=transactions))
    return render_template('finance/recovery.html',deleted=rows)


@bp.post('/imports/<int:batch_id>/<action>')
def import_action(batch_id, action):
    try:
        if action == 'rollback':
            count = rollback_batch(batch_id)
            flash(f'Rolled back {count} imported records. They are retained in transaction recovery.', 'success')
        elif action == 'profile':
            save_profile(batch_id, request.form.get('name'))
            flash('Bank profile saved. Matching files for this account will reuse it.', 'success')
        else:
            abort(404)
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('finance.imports'))


@bp.route('/transfers', methods=['GET', 'POST'])
def transfers():
    error = None
    if request.method == 'POST':
        try:
            match_transfer(request.form.get('outgoing_id', type=int), request.form.get('incoming_id', type=int))
            flash('Transfer matched. Account balances are unchanged; reports now treat it as a transfer.', 'success')
            return redirect(url_for('finance.transfers'))
        except ValueError as exc:
            error = str(exc)
    matches = get_db().execute("SELECT r.*,t.date,t.amount_eur,a.name AS from_account,b.name AS to_account FROM transaction_relationships r JOIN transactions t ON t.id=r.source_transaction_id JOIN accounts a ON a.id=t.account_id JOIN accounts b ON b.id=t.destination_account_id WHERE r.kind='transfer_pair' ORDER BY t.date DESC").fetchall()
    return render_template('finance/transfers.html', candidates=transfer_candidates(), matches=matches, error=error), (400 if error else 200)


@bp.post('/transfers/<int:relationship_id>/unmatch')
def unmatch(relationship_id):
    try:
        unmatch_transfer(relationship_id)
        flash('Original expense and income restored.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('finance.transfers'))


@bp.route('/aliases', methods=['GET', 'POST'])
def aliases():
    error = None
    if request.method == 'POST':
        try:
            save_alias(request.form.get('merchant_id'), request.form.get('alias'))
            return redirect(url_for('finance.aliases'))
        except ValueError as exc:
            error = str(exc)
    rows = get_db().execute('SELECT a.*,m.name AS merchant_name FROM merchant_aliases a JOIN merchants m ON m.id=a.merchant_id ORDER BY m.name,a.alias').fetchall()
    return render_template('finance/aliases.html', aliases=rows, merchants=list_merchants(), error=error), (400 if error else 200)


@bp.post('/aliases/<int:alias_id>/delete')
def delete_alias(alias_id):
    db = get_db()
    db.execute('DELETE FROM merchant_aliases WHERE id=?', (alias_id,))
    db.commit()
    return redirect(url_for('finance.aliases'))


@bp.get('/reconciliation')
def reconciliation():
    return render_template('finance/reconciliation.html', sessions=reconciliation_history())


@bp.post('/reconciliation/<int:session_id>/reopen')
def reopen(session_id):
    try:
        reopen_session(session_id)
        flash('Session reopened. Its transactions can be corrected and checked again.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('finance.reconciliation'))


@bp.get('/net-worth')
def net_worth():
    return render_template('finance/net_worth.html', history=net_worth_history())


@bp.get('/recurring/<int:rule_id>/history')
def occurrences(rule_id):
    rule = get_db().execute('SELECT * FROM recurring_rules WHERE id=?', (rule_id,)).fetchone()
    if not rule:
        abort(404)
    rows = get_db().execute('SELECT o.due_date,t.id,t.status,t.amount FROM recurring_occurrences o LEFT JOIN transactions t ON t.recurring_rule_id=o.recurring_rule_id AND t.date=o.due_date WHERE o.recurring_rule_id=? ORDER BY o.due_date DESC', (rule_id,)).fetchall()
    return render_template('finance/occurrences.html', rule=rule, occurrences=rows)


@bp.post('/subscriptions/<int:transaction_id>/track')
def track(transaction_id):
    try:
        track_subscription(transaction_id)
        flash('Subscription added to recurring payments. Review its next due date.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('recurring.subscriptions'))


@bp.get('/attachments/<int:attachment_id>')
def attachment(attachment_id):
    row = get_db().execute('SELECT * FROM transaction_attachments WHERE id=?', (attachment_id,)).fetchone()
    if not row:
        abort(404)
    return send_from_directory(attachment_directory(), row['storage_name'], as_attachment=True, download_name=row['filename'])
