import json
from urllib.request import urlopen


BASE_CURRENCY = "EUR"
SUPPORTED_CURRENCIES = ["EUR", "USD", "GBP", "CHF"]
_CACHE = {}

# Used only when the live API is unavailable. These are conservative fallbacks,
# not a replacement for the live rate saved at transaction time.
FALLBACK_TO_EUR = {
    "USD": 0.93,
    "GBP": 1.18,
    "CHF": 1.05,
}


def to_eur(amount, currency):
    currency = (currency or BASE_CURRENCY).upper()
    amount = float(amount or 0)
    if currency == BASE_CURRENCY:
        return amount
    return round(amount * eur_rate(currency), 2)


def eur_rate(currency):
    currency = currency.upper()
    if currency in _CACHE:
        return _CACHE[currency]
    try:
        with urlopen(f"https://api.frankfurter.app/latest?from={currency}&to=EUR", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
            rate = float(payload["rates"]["EUR"])
    except Exception:
        rate = FALLBACK_TO_EUR.get(currency, 1.0)
    _CACHE[currency] = rate
    return rate