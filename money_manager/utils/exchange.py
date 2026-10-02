import json
import threading
import time
from datetime import date
from decimal import Decimal
from urllib.request import urlopen

from money_manager.utils.money import decimal_money

BASE_CURRENCY = "EUR"
SUPPORTED_CURRENCIES = ["EUR", "USD", "GBP", "CHF"]
FALLBACK_TO_EUR = {"USD": "0.93", "GBP": "1.18", "CHF": "1.05"}
_CACHE = {}
_LOCK = threading.Lock()


def exchange_quote(currency):
    currency = (currency or BASE_CURRENCY).upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError("Choose EUR, USD, GBP, or CHF.")
    if currency == BASE_CURRENCY:
        return dict(rate="1", date=date.today().isoformat(), source="EUR")
    with _LOCK:
        cached = _CACHE.get(currency)
        now = time.monotonic()
        if cached and cached["expires"] > now and cached["day"] == date.today().isoformat():
            return dict(cached["quote"])
        try:
            with urlopen(f"https://api.frankfurter.app/latest?from={currency}&to=EUR", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            rate = Decimal(str(payload["rates"]["EUR"]))
            if not rate.is_finite() or rate <= 0:
                raise ValueError("Invalid exchange rate.")
            quote = dict(rate=str(rate), date=date.fromisoformat(payload["date"]).isoformat(), source="Frankfurter")
            ttl = 21600
        except (OSError, ValueError, KeyError, TypeError):
            quote = dict(rate=FALLBACK_TO_EUR[currency], date=None, source="estimated")
            ttl = 60
        _CACHE[currency] = dict(quote=quote, expires=now + ttl, day=date.today().isoformat())
        return dict(quote)


def to_eur(amount, currency, quote=None):
    quote = quote or exchange_quote(currency)
    return float(decimal_money(decimal_money(amount) * Decimal(quote["rate"]), rounding=True))


def eur_rate(currency):
    return float(exchange_quote(currency)["rate"])
