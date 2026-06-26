from flask import Blueprint, render_template, request


bp = Blueprint("forecast", __name__, url_prefix="/forecast")


@bp.route("/", methods=("GET", "POST"))
def index():
    result = None
    form = {
        "monthly_income": float(request.form.get("monthly_income") or 3000),
        "monthly_expenses": float(request.form.get("monthly_expenses") or 1800),
        "monthly_investments": float(request.form.get("monthly_investments") or 500),
        "years": int(request.form.get("years") or 10),
        "annual_return": float(request.form.get("annual_return") or 5),
    }
    if request.method == "POST":
        monthly_return = (form["annual_return"] / 100) / 12
        balance = 0
        invested = 0
        rows = []
        for month in range(1, form["years"] * 12 + 1):
            surplus = form["monthly_income"] - form["monthly_expenses"] - form["monthly_investments"]
            invested = (invested + form["monthly_investments"]) * (1 + monthly_return)
            balance += surplus
            if month % 12 == 0:
                rows.append({"year": month // 12, "cash": round(balance, 2), "investments": round(invested, 2), "total": round(balance + invested, 2)})
        result = rows
    return render_template("forecast.html", form=form, result=result)
