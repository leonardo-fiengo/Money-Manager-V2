from flask import Blueprint, render_template, request
from money_manager.services.loans import list_loans
from money_manager.utils.dates import today_iso

bp = Blueprint('debts',__name__,url_prefix='/debts')


@bp.get('/')
def index():
    direction = request.args.get('direction')
    status = request.args.get('status')
    if direction not in {'lent_out','borrowed'}: direction=None
    if status not in {'open','closed'}: status=None
    return render_template('loans/index.html',loans=list_loans(status,direction=direction),all_loans=list_loans(),status=status,direction=direction,debt_view=True,today=today_iso())
