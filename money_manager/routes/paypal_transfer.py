from flask import Blueprint, render_template, request


bp = Blueprint("paypal_transfer", __name__, url_prefix="/paypal-transfer")


@bp.route("/", methods=("GET", "POST"))
def index():
    amount = float(request.form.get("amount") or 0)
    mode = request.form.get("mode", "instant")
    fee_rate = 0.0175 if mode == "instant" else 0
    fee = round(amount * fee_rate, 2)
    net = round(amount - fee, 2)
    return render_template(
        "paypal_transfer.html",
        amount=amount,
        mode=mode,
        fee=fee,
        net=net,
        fee_rate=fee_rate * 100,
    )
