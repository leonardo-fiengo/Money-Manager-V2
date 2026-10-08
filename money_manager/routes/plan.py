from flask import Blueprint, render_template, request
from money_manager.services.cockpit import plan_summary

bp=Blueprint('plan',__name__,url_prefix='/plan')


@bp.get('/')
def index():
    return render_template('plan.html',**plan_summary(request.args.get('month'),request.args.get('days',30)))
