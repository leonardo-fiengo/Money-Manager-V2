import json
from datetime import date
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from money_manager.db.connection import get_db
from money_manager.db.atomic import atomic
from money_manager.services.taxes import RULES, calculate_irpef, get_tax, list_taxes, list_estimates, record_payment, save_estimate, save_tax, tax_years

bp=Blueprint('taxes',__name__,url_prefix='/taxes')


@bp.get('/')
def index():
    year=request.args.get('year',date.today().year,type=int)
    if not 1900<=year<=2200: abort(400)
    return render_template('taxes/index.html',taxes=list_taxes(year),estimates=list_estimates(year),year=year,years=sorted(set(tax_years()+[year]),reverse=True),current_year=date.today().year,today=date.today().isoformat())


@bp.route('/new',methods=['GET','POST'])
@bp.route('/<int:tax_id>/edit',methods=['GET','POST'])
def edit(tax_id=None):
    tax=get_tax(tax_id) if tax_id else None
    if tax_id and not tax: abort(404)
    error=None
    if request.method=='POST':
        try:
            tax_id=save_tax(request.form,tax_id)
            return redirect(url_for('taxes.detail',tax_id=tax_id))
        except ValueError as exc: error=str(exc)
    return render_template('taxes/form.html',tax=request.form if error else tax,error=error,editing=bool(tax),year=request.args.get('year',date.today().year,type=int),amount=request.args.get('amount','')), (400 if error else 200)


@bp.get('/<int:tax_id>')
def detail(tax_id):
    tax=get_tax(tax_id)
    if not tax: abort(404)
    payments=get_db().execute('SELECT *,amount_minor/100.0 AS amount FROM tax_payments WHERE tax_id=? ORDER BY date DESC,id DESC',(tax_id,)).fetchall()
    return render_template('taxes/detail.html',tax=tax,payments=payments,today=date.today().isoformat())


@bp.post('/<int:tax_id>/payments')
def payment(tax_id):
    if not get_tax(tax_id): abort(404)
    try:
        record_payment(tax_id,request.form)
        flash('Payment recorded. One less thing for future you.', 'success')
    except ValueError as exc: flash(str(exc),'error')
    return redirect(url_for('taxes.detail',tax_id=tax_id))


@bp.post('/payments/<int:payment_id>/delete')
def payment_delete(payment_id):
    row=get_db().execute('SELECT * FROM tax_payments WHERE id=?',(payment_id,)).fetchone()
    if not row: abort(404)
    with atomic(get_db()): get_db().execute('DELETE FROM tax_payments WHERE id=?',(payment_id,))
    return redirect(url_for('taxes.detail',tax_id=row['tax_id']))


@bp.post('/<int:tax_id>/delete')
def delete(tax_id):
    tax=get_tax(tax_id)
    if not tax: abort(404)
    with atomic(get_db()):
        if get_db().execute('SELECT 1 FROM tax_payments WHERE tax_id=?',(tax_id,)).fetchone():
            flash('This tax has payment history. Keep it in its yearly archive, or remove mistaken payments first.','error')
            return redirect(url_for('taxes.detail',tax_id=tax_id))
        get_db().execute('DELETE FROM taxes WHERE id=?',(tax_id,))
    return redirect(url_for('taxes.index',year=tax['tax_year']))


@bp.route('/calculator',methods=['GET','POST'])
def calculator():
    values=dict(tax_year=request.args.get('year',date.today().year,type=int)); result=None; error=None
    if request.method=='POST':
        values=request.form
        try:
            values,result=calculate_irpef(request.form)
            if request.form.get('action')=='save':
                estimate_id=save_estimate(request.form)
                flash('Estimate saved in your tax-year archive.','success')
                return redirect(url_for('taxes.estimate',estimate_id=estimate_id))
        except ValueError as exc: error=str(exc)
    return render_template('taxes/calculator.html',values=values,result=result,error=error,verified_years=sorted(RULES,reverse=True)), (400 if error else 200)


@bp.get('/estimates/<int:estimate_id>')
def estimate(estimate_id):
    row=get_db().execute('SELECT * FROM tax_estimates WHERE id=?',(estimate_id,)).fetchone()
    if not row: abort(404)
    return render_template('taxes/estimate.html',estimate=row,values=json.loads(row['inputs_json']),result=json.loads(row['result_json']))
