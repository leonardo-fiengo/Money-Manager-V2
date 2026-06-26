from flask import Blueprint, redirect, render_template, request, url_for

from money_manager.services.accounts import list_accounts
from money_manager.services.transactions import create_transaction
from money_manager.utils.dates import today_iso
from money_manager.utils.filters import clean_amount

bp = Blueprint("paypal_transfer", __name__, url_prefix="/paypal-transfer")


def _paypal_context(error=None):
    accounts = list_accounts()
    source_account = next((account for account in accounts if account["name"].lower() == "paypal"), None)
    destination_accounts = [
        account
        for account in accounts
        if account["name"].lower() in {"nexi", "revolut"}
        and (not source_account or account["id"] != source_account["id"])
    ]
    if not destination_accounts:
        destination_accounts = [
            account for account in accounts if not source_account or account["id"] != source_account["id"]
        ]
    return {
        "source_account": source_account,
        "destination_accounts": destination_accounts,
        "error": error,
    }


@bp.route("/", methods=("GET", "POST"))
def index():
    if request.method == "POST":
        context = _paypal_context()
        source_account = context["source_account"]
        destination_account_id = request.form.get("destination_account_id")
        try:
            amount = clean_amount(request.form.get("transfer_amount"))
            if not source_account:
                raise ValueError("PayPal account is required.")
            create_transaction(
                {
                    "date": today_iso(),
                    "type": "transfer",
                    "amount": amount,
                    "currency": "EUR",
                    "category": "PayPal transfer",
                    "description": "PayPal transfer",
                    "account_id": source_account["id"],
                    "destination_account_id": int(destination_account_id) if destination_account_id else None,
                    "merchant_id": None,
                    "status": "posted",
                }
            )
            return redirect(url_for("transactions.index", type="transfer"))
        except ValueError as error:
            return render_template("paypal_transfer.html", **_paypal_context(str(error))), 400

    return render_template("paypal_transfer.html", **_paypal_context())
