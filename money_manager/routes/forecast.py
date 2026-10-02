from flask import Blueprint, flash, redirect, render_template, request, url_for

from money_manager.services.forecasting import cash_forecast, list_scenarios, save_scenario


bp = Blueprint("forecast", __name__, url_prefix="/forecast")


@bp.route("/", methods=['GET','POST'])
def index():
    error=None
    if request.method=='POST':
        try:
            save_scenario(request.form.get('name'),request.form.get('income'),request.form.get('spending'),request.form.get('investment'))
            flash('Forecast scenario saved.', 'success')
            return redirect(url_for('forecast.index',days=request.args.get('days') or 30))
        except ValueError as exc:
            error=str(exc)
    return render_template("forecast.html", forecast=cash_forecast(request.args.get("days") or 30,request.args.get('scenario',type=int)), scenarios=list_scenarios(),error=error), (400 if error else 200)
