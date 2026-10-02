import gc
import io
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from money_manager import create_app
from money_manager.db.connection import close_db, get_db
from money_manager.services.analytics import dashboard_metrics, expenses_by_category, spending_by_tag
from money_manager.services.budgets import list_budgets, upsert_budget, save_budget_template, list_budget_templates, apply_budget_template
from money_manager.services.categories import create_category
from money_manager.services.forecasting import cash_forecast
from money_manager.services.importing import create_batch, save_mapping, preview_batch, confirm_batch, save_rule
from money_manager.services.planning import move_pot, save_pot, savings_summary
from money_manager.services.recurring import create_rule
from money_manager.services.transaction_details import link_refund, save_splits, save_tags
from money_manager.services.transactions import create_transaction, list_transactions, delete_transaction, restore_transaction, update_transaction


class V3Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        config = type("TestConfig", (), dict(DATA_DIR=root, DATABASE=root / "test.sqlite3", MERCHANT_LOGO_DIR=root / "logos", SECRET_KEY="test", TESTING=True))
        self.app = create_app(config)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()
        self.account = get_db().execute("SELECT id FROM accounts WHERE name = 'Cash'").fetchone()["id"]

    def tearDown(self):
        close_db()
        self.ctx.pop()
        gc.collect()
        self.temp.cleanup()

    def test_csv_mapping_review_rules_and_duplicate_detection(self):
        category = "Travel"
        create_category(dict(name=category, type="expense", color="#147d64"))
        save_rule("EAV", category=category)
        csv_file = io.BytesIO(b"Date,Description,Amount\n2026-09-28,EAV SRL,-3.20\n2026-09-29,Salary,1250.00\n")
        csv_file.filename = "bank.csv"
        batch_id = create_batch(csv_file, self.account)
        self.assertEqual(self.client.get(f"/transactions/import/{batch_id}").status_code, 200)
        save_mapping(batch_id, dict(date="Date", description="Description", amount="Amount", debit="", credit="", currency="", date_format="ymd", default_currency="EUR"))
        self.assertEqual(self.client.get(f"/transactions/import/{batch_id}").status_code, 200)
        rows = preview_batch(batch_id)
        self.assertFalse(any(row["duplicate"] or row["error"] for row in rows))
        self.assertEqual(rows[0]["item"]["category"], category)
        self.assertEqual(confirm_batch(batch_id, ["0", "1"], categories={0: category}), 2)
        with self.assertRaises(ValueError):
            confirm_batch(batch_id, ["0"])
        self.assertEqual(len(list_transactions(include_pending=True)), 2)
        imported_id = list_transactions({"search": "EAV"})[0]["id"]
        restore_transaction(delete_transaction(imported_id))
        csv_again = io.BytesIO(b"Date,Description,Amount\n2026-09-28,EAV SRL,-3.20\n")
        csv_again.filename = "again.csv"
        second = create_batch(csv_again, self.account)
        save_mapping(second, dict(date="Date", description="Description", amount="Amount", debit="", credit="", currency="", date_format="ymd", default_currency="EUR"))
        self.assertTrue(preview_batch(second)[0]["duplicate"])
        with self.assertRaises(ValueError):
            confirm_batch(second, ["0"])

    def test_splits_refunds_tags_budgets_and_pots(self):
        grocery = create_category(dict(name="Split groceries", type="expense", color="#147d64"))
        household = create_category(dict(name="Split household", type="expense", color="#147d64"))
        today = date.today().isoformat()
        expense = create_transaction(dict(date=today, type="expense", amount=80, account_id=self.account))
        income = create_transaction(dict(date=today, type="income", amount=10, account_id=self.account))
        save_splits(expense, [("Split groceries", "55"), ("Split household", "25")])
        save_tags(expense, "Home, October")
        link_refund(income, expense)
        self.assertIn("Home, October", self.client.get("/transactions/").text)
        self.assertEqual(self.client.get(f"/transactions/{expense}/details").status_code, 200)
        self.assertEqual(self.client.get(f"/transactions/{income}/details").status_code, 200)
        allocations = {row["category"]: row["total"] for row in expenses_by_category()}
        self.assertAlmostEqual(allocations["Split groceries"], 48.12, places=2)
        self.assertAlmostEqual(allocations["Split household"], 21.88, places=2)
        self.assertEqual(dashboard_metrics()["income"], 0)
        self.assertEqual(dashboard_metrics()["expenses"], 70)
        self.assertEqual({row["tag"]: row["total"] for row in spending_by_tag()}["Home"], 70)
        self.assertEqual(len(list_transactions({"tag": "Home"})), 1)
        upsert_budget(dict(month=today[:7], category_id=grocery, amount=100, rollover=True))
        self.assertAlmostEqual(list_budgets(today[:7])[0]["spent_amount"], 48.12, places=2)
        create_transaction(dict(date=today, type="income", amount=100, account_id=self.account))
        save_pot("Trip", 200, 20)
        pot_id = savings_summary()["pots"][0]["id"]
        move_pot(pot_id, "10", "add", "Monthly saving")
        self.assertEqual(savings_summary()["pots"][0]["reserved"], 30)
        self.assertEqual(len(savings_summary()["pots"][0]["movements"]), 2)
        original = get_db().execute("SELECT * FROM transactions WHERE id = ?", (expense,)).fetchone()
        update_transaction(expense, dict(original, amount=100))
        self.assertAlmostEqual(sum(row["amount_eur"] for row in get_db().execute("SELECT amount_eur FROM transaction_splits WHERE transaction_id = ?", (expense,))), 100)
        trash = delete_transaction(expense)
        self.assertFalse(get_db().execute("SELECT 1 FROM transaction_tags WHERE transaction_id = ?", (expense,)).fetchone())
        restore_transaction(trash)
        self.assertTrue(get_db().execute("SELECT 1 FROM transaction_tags WHERE transaction_id = ?", (expense,)).fetchone())
        self.assertEqual(len(get_db().execute("SELECT id FROM transaction_splits WHERE transaction_id = ?", (expense,)).fetchall()), 2)
        self.assertTrue(get_db().execute("SELECT 1 FROM transaction_links WHERE source_transaction_id = ?", (expense,)).fetchone())

    def test_forecast_and_new_pages(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        create_transaction(dict(date=tomorrow, type="income", amount=100, account_id=self.account, status="pending"))
        forecast = cash_forecast(30)
        self.assertEqual(forecast["projected"], forecast["opening"] + 100)
        create_rule(dict(name="Gym", type="expense", amount=35, account_id=self.account, frequency="monthly", next_due_date=tomorrow, is_subscription=True))
        forecast = cash_forecast(30)
        self.assertEqual(forecast["projected"], forecast["opening"] + 65)
        self.assertIn("Gym", self.client.get("/recurring/subscriptions").text)
        self.assertIn("Gym", self.client.get("/calendar/?month=" + tomorrow[:7]).text)
        for route in ("/", "/transactions/", "/transactions/import", "/transactions/import/rules", "/calendar/", "/recurring/subscriptions", "/forecast/", "/inbox/"):
            self.assertEqual(self.client.get(route).status_code, 200, route)

    def test_budget_rollover_and_template(self):
        category = create_category(dict(name="Rollover test", type="expense", color="#147d64"))
        upsert_budget(dict(month="2026-01", category_id=category, amount=100, rollover=True))
        upsert_budget(dict(month="2026-02", category_id=category, amount=100, rollover=True))
        upsert_budget(dict(month="2026-03", category_id=category, amount=100, rollover=True))
        self.assertEqual(list_budgets("2026-03")[0]["available_amount"], 300)
        self.assertEqual(self.client.get("/budgets/?month=2026-03").status_code, 200)
        save_budget_template("Travel plan", "2026-03")
        self.assertEqual(self.client.get("/budgets/?month=2026-03").status_code, 200)
        apply_budget_template(list_budget_templates()[0]["id"], "2026-04")
        self.assertEqual(list_budgets("2026-04")[0]["amount"], 100)

    def test_csv_import_http_flow(self):
        response = self.client.post("/transactions/import", data={"account_id": str(self.account), "file": (io.BytesIO(b"Date,Description,Amount\n2026-09-27,Coffee,-4.50\n"), "bank.csv")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        batch_url = response.location
        response = self.client.post(batch_url, data=dict(date="Date", description="Description", amount="Amount", date_format="ymd", default_currency="EUR"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("Coffee", self.client.get(batch_url).text)
        response = self.client.post(batch_url + "/confirm", data={"selected": "0"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(list_transactions(include_pending=True)), 1)
        self.assertIn("needs_category=1", self.client.get("/inbox/").text)
        self.assertIn("Coffee", self.client.get("/transactions/?needs_category=1").text)

    def test_csv_european_amount_and_positive_charges(self):
        file = io.BytesIO('Date;Description;Amount\n28/09/2026;Nexi charge;1.234,56\n'.encode())
        file.filename = "card.csv"
        batch = create_batch(file, self.account)
        save_mapping(batch, dict(date="Date", description="Description", amount="Amount", debit="", credit="", currency="", date_format="dmy", default_currency="EUR", expense_sign="positive"))
        row = preview_batch(batch)[0]
        self.assertIsNone(row["error"])
        self.assertEqual(row["item"]["type"], "expense")
        self.assertEqual(row["item"]["amount"], 1234.56)

    def test_import_remembers_corrected_category(self):
        create_category(dict(name="Learned import category", type="expense", color="#147d64"))
        mapping = dict(date="Date", description="Description", amount="Amount", debit="", credit="", currency="", date_format="ymd", default_currency="EUR")
        first = io.BytesIO(b"Date,Description,Amount\n2026-09-27,LOCAL CAFE,-5.00\n")
        first.filename = "first.csv"
        batch = create_batch(first, self.account)
        save_mapping(batch, mapping)
        confirm_batch(batch, ["0"], categories={0: "Learned import category"}, remember=["0"])
        second = io.BytesIO(b"Date,Description,Amount\n2026-09-28,LOCAL CAFE,-6.00\n")
        second.filename = "second.csv"
        batch = create_batch(second, self.account)
        save_mapping(batch, mapping)
        self.assertEqual(preview_batch(batch)[0]["item"]["category"], "Learned import category")

    def test_invalid_import_selection_does_not_partially_commit(self):
        file = io.BytesIO(b"Date,Description,Amount\n2026-09-27,Valid,-2.00\nnot-a-date,Broken,-3.00\n")
        file.filename = "mixed.csv"
        batch = create_batch(file, self.account)
        save_mapping(batch, dict(date="Date", description="Description", amount="Amount", debit="", credit="", currency="", date_format="ymd", default_currency="EUR"))
        with self.assertRaises(ValueError):
            confirm_batch(batch, ["0", "1"])
        self.assertEqual(list_transactions(include_pending=True), [])


if __name__ == "__main__":
    unittest.main()
