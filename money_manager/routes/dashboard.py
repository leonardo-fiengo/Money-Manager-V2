from flask import Blueprint, jsonify, render_template, request

from money_manager.services.analytics import dashboard_metrics, dashboard_period, six_month_flow
from money_manager.services.cockpit import cockpit_summary
from money_manager.services.history import dashboard_layout
from money_manager.services.dashboard_overview import overview_summary, balance_series, flow_summary

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    if request.args.get('view') != 'workspace':
        return render_template('dashboard.html', overview=overview_summary())
    period = dashboard_period(request.args.get("period", "month"))
    return render_template(
        "dashboard_workspace.html", metrics=dashboard_metrics(period["start"], period["end"]),
        period=period, flow_trend=six_month_flow(), layout=dashboard_layout(),
        cockpit=cockpit_summary(request.args.get('days', 30)),
    )


@bp.get('/overview/balance')
def balance():
    return jsonify(balance_series(request.args.get('range', '3m')))


@bp.get('/overview/cash-flow')
def cash_flow():
    return jsonify(flow_summary(request.args.get('months', 6, type=int)))
