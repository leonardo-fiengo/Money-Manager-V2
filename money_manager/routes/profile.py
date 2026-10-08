from flask import Blueprint, render_template, request, flash, redirect, url_for
from money_manager.services.profile import local_profile, save_profile, profile_photo
from money_manager.services.contacts import list_contacts
from money_manager.services.preferences import payment_accounts

bp = Blueprint('profile',__name__,url_prefix='/profile')


@bp.route('/',methods=['GET','POST'])
def index():
    error = None
    if request.method=='POST':
        try:
            save_profile(request.form.get('display_name'),request.form.get('email',''),request.form.get('phone',''),profile_photo(request.files.get('photo')),request.form.get('remove_photo')=='1')
            flash('Profile saved. Your money now knows who to blame.', 'success')
            return redirect(url_for('profile.index'))
        except ValueError as exc:
            error = str(exc)
    return render_template('profile.html',profile=local_profile(),payment_accounts=payment_accounts(),contacts=list_contacts(),error=error), (400 if error else 200)
