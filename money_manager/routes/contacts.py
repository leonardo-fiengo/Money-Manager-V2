from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from money_manager.services.contacts import get_contact, list_contacts, save_contact, set_contact_active

bp = Blueprint('contacts',__name__,url_prefix='/profile/contacts')


@bp.get('/')
def index():
    return render_template('contacts/index.html',contacts=list_contacts(active_only=False))


@bp.route('/new',methods=['GET','POST'])
@bp.route('/<int:contact_id>/edit',methods=['GET','POST'])
def edit(contact_id=None):
    contact = get_contact(contact_id) if contact_id else None
    if contact_id and not contact: abort(404)
    error = None
    if request.method=='POST':
        try:
            save_contact(request.form,contact_id)
            flash('Contact saved. People: now slightly easier to keep track of.', 'success')
            return redirect(url_for('contacts.index'))
        except ValueError as exc: error = str(exc)
    return render_template('contacts/form.html',contact=request.form if error else contact,error=error,editing=bool(contact_id)), (400 if error else 200)


@bp.post('/<int:contact_id>/archive')
def archive(contact_id):
    if not get_contact(contact_id): abort(404)
    set_contact_active(contact_id,request.form.get('restore')=='1')
    flash('Contact restored.' if request.form.get('restore')=='1' else 'Contact archived. Their past transactions stay put.', 'success')
    return redirect(url_for('contacts.index'))
