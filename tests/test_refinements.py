import gc
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from money_manager import create_app
from money_manager.db.connection import close_db, get_db
from money_manager.services.accounts import account_balances, create_account, list_accounts
from money_manager.services.analytics import cumulative_balance, dashboard_metrics
from money_manager.services.backup import export_data
from money_manager.services.planning import save_pot, savings_summary, upcoming_overview
from money_manager.services.preferences import payment_accounts, save_payment_preference
from money_manager.services.reconciliation import check_payload, money_value, preview_balances, record_checks
from money_manager.services.recurring import create_rule
from money_manager.services.transactions import create_transaction, delete_transaction, get_transaction, restore_transaction
from money_manager.utils.dates import add_frequency


class RefinementTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        config = type("TestConfig", (), dict(DATA_DIR=root, DATABASE=root / "test.sqlite3", MERCHANT_LOGO_DIR=root / "logos", SECRET_KEY="test", TESTING=True))
        self.app = create_app(config)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()
        self.cash = next(a["id"] for a in list_accounts() if a["name"] == "Cash")
        self.card = next(a["id"] for a in list_accounts() if a["name"] == "Nexi")

    def tearDown(self):
        close_db()
        self.ctx.pop()
        gc.collect()
        self.temp.cleanup()

    def tx(self, account=None, **extra):
        values = dict(date=date.today().isoformat(), type="expense", amount=10, account_id=account or self.cash)
        values.update(extra)
        return create_transaction(values)

    def balance(self, account):
        return next(a["balance"] for a in account_balances() if a["id"] == account)

    def test_automatic_uses_recency_and_only_completed_purchases(self):
        old = (date.today() - timedelta(days=180)).isoformat()
        for _ in range(4):
            self.tx(date=old)
        self.tx(self.card)
        self.tx(type="income", amount=1000)
        self.tx(status="pending")
        self.assertEqual(payment_accounts()[0]["id"], self.card)
        save_payment_preference("manual", str(self.cash))
        self.assertEqual(payment_accounts()[0]["id"], self.cash)
        get_db().execute("UPDATE accounts SET is_active = 0 WHERE id = ?", (self.cash,))
        get_db().commit()
        self.assertEqual(payment_accounts()[0]["id"], self.card)
        with self.assertRaises(ValueError):
            save_payment_preference("manual", str(self.cash))

    def test_adjustment_changes_balance_but_not_income_or_expenses(self):
        self.tx(type="income", amount=100)
        before = dashboard_metrics()
        rows = preview_balances({str(self.cash): "85", str(self.card): "0"})
        record_checks(check_payload(rows), [str(self.cash)], "Counted cash")
        self.assertEqual(self.balance(self.cash), 85)
        self.assertEqual(dashboard_metrics()["income"], before["income"])
        self.assertEqual(dashboard_metrics()["expenses"], before["expenses"])
        self.assertEqual(dashboard_metrics()["net_balance"], before["net_balance"] - 15)
        self.assertEqual(cumulative_balance()[-1]["balance"], dashboard_metrics()["net_balance"])
        self.assertEqual(len(export_data()["balance_checks"]), 2)

    def test_check_without_adjustment_and_duplicate_submission(self):
        payload = check_payload(preview_balances({str(self.cash): "20"}))
        record_checks(payload, [], "Still investigating")
        self.assertEqual(self.balance(self.cash), 0)
        with self.assertRaisesRegex(ValueError, "already been saved"):
            record_checks(payload, [str(self.cash)], "")
        self.assertEqual(self.balance(self.cash), 0)

    def test_stale_preview_is_rejected_atomically(self):
        payload = check_payload(preview_balances({str(self.cash): "20", str(self.card): "30"}))
        self.tx(self.card)
        with self.assertRaisesRegex(ValueError, "changed"):
            record_checks(payload, [str(self.cash), str(self.card)], "")
        self.assertEqual(self.balance(self.cash), 0)
        self.assertEqual(export_data()["balance_checks"], [])

    def test_mismatch_hints_and_invalid_balances(self):
        rows = preview_balances({str(self.cash): "-10", str(self.card): "10"})
        self.assertIn("opposite difference", rows[0]["hints"][0])
        for invalid in ("NaN", "inf", "1.001", "", "10000000000"):
            with self.assertRaises(ValueError):
                money_value(invalid)
        with self.assertRaises(ValueError):
            preview_balances({})

    def test_undo_restores_expense_and_its_settlement_exactly_once(self):
        credit = create_account("Credit", "credit_card", settlement_account_id=self.cash, settlement_day=15)
        txid = self.tx(credit)
        before = [dict(r) for r in get_db().execute("SELECT * FROM transactions ORDER BY id")]
        trash_id = delete_transaction(txid)
        self.assertIsNone(get_transaction(txid))
        self.assertEqual(list(get_db().execute("SELECT * FROM transactions")), [])
        restore_transaction(trash_id)
        self.assertEqual(list(get_db().execute("SELECT * FROM transactions ORDER BY id")), before)
        with self.assertRaises(ValueError):
            restore_transaction(trash_id)

    def test_savings_pots_do_not_move_money_or_allow_double_reservation(self):
        self.tx(type="income", amount=100)
        save_pot("Trip", "200", "70")
        self.assertEqual(savings_summary()["unassigned"], 30)
        self.assertEqual(self.balance(self.cash), 100)
        with self.assertRaises(ValueError):
            save_pot("Laptop", 500, 40)
        self.tx(amount=80)
        pot = savings_summary()["pots"][0]
        save_pot("Trip", 200, 10, pot["id"])
        self.assertEqual(savings_summary()["unassigned"], 10)

    def test_upcoming_includes_recurring_without_double_counting(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        rule_id = create_rule(dict(name="Bill", type="expense", amount=12, account_id=self.cash, frequency="monthly", next_due_date=tomorrow))
        overview = upcoming_overview()
        self.assertTrue(any(r["source"] == "recurring" for r in overview["rows"]))
        expected = overview["outgoing"]
        self.tx(date=tomorrow, amount=12, status="pending", recurring_rule_id=rule_id)
        self.assertEqual(upcoming_overview()["outgoing"], expected)
        self.assertEqual(add_frequency("2024-02-29", "yearly").isoformat(), "2025-02-28")

    def test_routes_and_inline_creation(self):
        pages = ("/", "/?period=all", "/accounts/", "/accounts/new", "/accounts/check", "/accounts/pots",
                 "/transactions/", "/transactions/new", "/analytics/", "/budgets/", "/recurring/", "/recurring/new",
                 "/pending/", "/loans/", "/loans/new", "/forecast/", "/merchants/", "/merchants/new",
                 "/categories/", "/categories/new", "/backup/", "/paypal-transfer/")
        for route in pages:
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200, route)
            self.assertIn('css/refinements.css?v=', response.text, route)
        response = self.client.post("/transactions/options/category", data=dict(name="Coffee test", type="expense"))
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.post("/transactions/options/category", data=dict(name="Coffee test", type="expense")).status_code, 400)
        response = self.client.post("/transactions/options/merchant", data=dict(name="Cafe test", default_category="Coffee test"))
        self.assertEqual(response.json["default_category"], "Coffee test")
        page = self.client.get("/transactions/").text
        self.assertEqual(page.count('href="/transactions/new"'), 1)
        response = self.client.post("/transactions/new", data=dict(account_id=self.cash, type="expense", amount="4.5", date=date.today().isoformat(), after_save="another"))
        self.assertTrue(response.location.endswith("/transactions/new"))

    def test_balance_check_preview_and_signed_confirmation(self):
        response = self.client.post("/accounts/check", data={f"actual_{self.cash}": "25"})
        self.assertEqual(response.status_code, 200)
        token = re.search(r'name="token" value="([^"]+)"', response.text).group(1)
        self.assertEqual(self.balance(self.cash), 0)
        response = self.client.post("/accounts/check", data=dict(action="save", token=token, adjust=str(self.cash)), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.balance(self.cash), 25)
        response = self.client.post("/accounts/check", data=dict(action="save", token=token + "invalid"))
        self.assertEqual(response.status_code, 400)

    def test_dashboard_period_filters_html_api_and_drilldowns(self):
        self.tx(type="income", amount=100)
        self.tx(date="2020-01-01", amount=40)
        response = self.client.get("/api/dashboard?period=month")
        self.assertEqual(response.json["metrics"]["expenses"], 0)
        response = self.client.get("/api/dashboard?period=all")
        self.assertEqual(response.json["metrics"]["expenses"], 40)
        self.assertIn("start=", self.client.get("/").text)
        self.assertNotIn("2020-01-01", self.client.get("/transactions/?start=" + date.today().isoformat()).text)


if __name__ == "__main__":
    unittest.main()
