from flask import Blueprint, flash, redirect, render_template, request, url_for

from money_manager.services.preferences import payment_accounts, payment_preference, save_payment_preference
from money_manager.services.history import WIDGET_CATALOG, dashboard_layout, dashboard_widgets, save_widgets


bp = Blueprint("settings", __name__, url_prefix="/settings")
SECTIONS = [('appearance','overview','Appearance & privacy','A comfortable view, day or night.'),('workspace','overview','Today workspace','Add widgets and arrange your dashboard.'),('payments','accounts','Payments','Choose your default payment account.'),('organization','filter','Organization','Categories, merchants, contacts, and rules.'),('review','check','Review','Balance checks and transfer matching.'),('data','backup','Data & tools','Imports, recovery, and backups.')]


@bp.route("/", methods=("GET", "POST"))
def index():
    error = None
    if request.method == "POST":
        try:
            if request.form.get('action')=='widgets':
                save_widgets(['position', 'actions', 'pulse', *request.form.getlist('widgets')])
                flash('Dashboard preferences saved.', 'success')
                return redirect(url_for('settings.workspace'))
            save_payment_preference(request.form.get("mode"), request.form.get("account_id"))
            flash("Default payment account saved.", "success")
            return redirect(url_for("settings.section", section="payments"))
        except ValueError as exc:
            error = str(exc)
    preference = payment_preference() if not error else {
        "mode": request.form.get("mode"), "account_id": request.form.get("account_id", type=int)
    }
    if error:
        return render_template('settings_section.html',section='payments',title='Payments',sections=SECTIONS,preference=preference,payment_accounts=payment_accounts(),error=error),400
    return render_template("settings.html",sections=SECTIONS)


@bp.route('/<section>',methods=['GET','POST'])
def section(section):
    from flask import abort
    item=next((s for s in SECTIONS if s[0]==section and section!='workspace'),None)
    if not item: abort(404)
    error=None
    if request.method=='POST':
        if section!='payments': abort(405)
        try:
            save_payment_preference(request.form.get('mode'),request.form.get('account_id'))
            flash('Default payment account saved.','success')
            return redirect(url_for('settings.section',section=section))
        except ValueError as exc: error=str(exc)
    preference=payment_preference() if not error else dict(mode=request.form.get('mode'),account_id=request.form.get('account_id',type=int))
    return render_template('settings_section.html',section=section,title=item[2],sections=SECTIONS,preference=preference,payment_accounts=payment_accounts(),error=error),(400 if error else 200)


@bp.route('/workspace', methods=('GET', 'POST'))
def workspace():
    from money_manager.services.analytics import dashboard_metrics, dashboard_period, six_month_flow
    from money_manager.services.cockpit import cockpit_summary

    error = None
    layout = dashboard_layout()
    if request.method == 'POST':
        widgets = request.form.getlist('widgets')
        widths = request.form.getlist('widths')
        try:
            if len(widgets) != len(widths) or len(widgets) != len(set(widgets)):
                raise ValueError('Each widget needs one size and may only appear once.')
            save_widgets(widgets, dict(zip(widgets, widths)))
            flash('Your Today workspace is saved. Make yourself at home.', 'success')
            return redirect(url_for('dashboard.index',view='workspace'))
        except ValueError as exc:
            error = str(exc)
    period = dashboard_period('month')
    return render_template('workspace_editor.html', layout=layout, catalog=WIDGET_CATALOG,
                           metrics=dashboard_metrics(period['start'], period['end']), period=period,
                           cockpit=cockpit_summary(), flow_trend=six_month_flow(), error=error), (400 if error else 200)
