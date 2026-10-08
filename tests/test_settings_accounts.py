import tempfile
import unittest
from pathlib import Path

from money_manager import create_app
from money_manager.db.connection import get_db
from money_manager.services.accounts import create_account, get_account
from money_manager.services.preferences import payment_preference


class SettingsAccountsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        config = type("TestConfig", (), dict(DATA_DIR=root, DATABASE=root / "test.sqlite3",
                      MERCHANT_LOGO_DIR=root / "logos", SECRET_KEY="test", TESTING=True))
        self.app = create_app(config)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.temp.cleanup()

    def test_settings_saves_default_and_rejects_inactive_account_without_changing_it(self):
        active = create_account("Everyday", "bank")
        inactive = create_account("Old bank", "bank")
        get_db().execute("UPDATE accounts SET is_active = 0 WHERE id = ?", (inactive,))
        get_db().commit()
        response = self.client.post("/settings/", data=dict(mode="manual", account_id=active), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payment_preference(), dict(id=1, mode="manual", account_id=active))
        response = self.client.post("/settings/", data=dict(mode="manual", account_id=inactive))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Choose an active account", response.text)
        self.assertEqual(payment_preference()["account_id"], active)

    def test_overview_excludes_inactive_balance_but_keeps_account_history_accessible(self):
        get_db().execute("UPDATE accounts SET is_active = 0")
        create_account("Active bank", "bank", "12.34")
        old = create_account("Archived bank", "bank", "900")
        get_db().execute("UPDATE accounts SET is_active = 0 WHERE id = ?", (old,))
        get_db().commit()
        page = self.client.get("/accounts/").text
        self.assertIn("€12.34", page)
        self.assertIn("Across 1 active account", page)
        self.assertIn("Archived accounts", page)
        self.assertIn(f"/accounts/{old}/edit", page)
        self.assertIn(f"account_id={old}", page)

    def test_switching_card_type_clears_settlement_and_invalid_edit_preserves_fields(self):
        bank = create_account("Settlement bank", "bank")
        card = create_account("Credit", "credit_card", "-10", bank, 12)
        response = self.client.post(f"/accounts/{card}/edit", data=dict(name="Credit", type="prepaid_card",
                                   opening_balance="-10", settlement_account_id=bank, settlement_day="12", is_active="on"))
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(get_account(card)["settlement_account_id"])
        self.assertIsNone(get_account(card)["settlement_day"])
        response = self.client.post(f"/accounts/{card}/edit", data=dict(name="New name", type="credit_card",
                                   opening_balance="-10", settlement_account_id=bank, settlement_day="29", is_active="on"))
        self.assertEqual(response.status_code, 400)
        self.assertIn('value="29"', response.text)
        self.assertIn('value="New name"', response.text)
        self.assertEqual(get_account(card)["name"], "Credit")

    def test_settings_write_requires_csrf_and_no_active_accounts_render_cleanly(self):
        self.app.config["CSRF_ENABLED"] = True
        self.assertEqual(self.client.post("/settings/", data=dict(mode="auto")).status_code, 400)
        get_db().execute("UPDATE accounts SET is_active = 0")
        get_db().commit()
        page = self.client.get("/settings/payments")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Add an active account", page.text)
        self.assertIn("No active accounts yet", self.client.get("/accounts/").text)


if __name__ == "__main__":
    unittest.main()
