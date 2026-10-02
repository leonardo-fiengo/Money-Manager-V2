from calendar import Calendar
from datetime import date, timedelta

from flask import Blueprint, render_template, request

from money_manager.db.connection import get_db
from money_manager.services.forecasting import cash_forecast


bp = Blueprint("calendar", __name__, url_prefix="/calendar")


@bp.get("/")
def index():
    today = date.today()
    try:
        first = date.fromisoformat((request.args.get("month") or today.strftime("%Y-%m")) + "-01")
    except ValueError:
        first = today.replace(day=1)
    if abs((first - today).days) > 370:
        first = today.replace(day=1)
    month = first.strftime("%Y-%m")
    events = {}
    for row in get_db().execute("SELECT t.*, a.name AS account FROM transactions t LEFT JOIN accounts a ON a.id = t.account_id WHERE (t.status = 'posted' OR (t.status = 'pending' AND t.date = ?)) AND substr(t.date,1,7) = ? ORDER BY t.date, t.id", (today.isoformat(), month)):
        amount = row["amount_eur"] if row["type"] == "income" else 0 if row["type"] == "transfer" else -row["amount_eur"]
        events.setdefault(row["date"], []).append(dict(name=row["description"] or row["category"] or row["type"].title(), amount=amount, price=row["amount_eur"], type=row["type"], source=row["status"], account=row["account"], category=row["category"], description=row["description"]))
    for row in cash_forecast(365)["events"]:
        if row["date"].startswith(month):
            events.setdefault(row["date"], []).append(row)
    weeks = [[dict(date=day.isoformat(), in_month=day.month == first.month, events=events.get(day.isoformat(), [])) for day in week]
             for week in Calendar(firstweekday=0).monthdatescalendar(first.year, first.month)]
    previous = (first - timedelta(days=1)).strftime("%Y-%m")
    next_month = (first.replace(day=28) + timedelta(days=4)).strftime("%Y-%m")
    return render_template("calendar.html", weeks=weeks, calendar_events=events, today=today.isoformat(), month=first.strftime("%B %Y"), previous=previous, next_month=next_month)
