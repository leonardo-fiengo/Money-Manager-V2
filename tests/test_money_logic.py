import tempfile
import unittest
import gc
from pathlib import Path

from money_manager import create_app
from money_manager.db.connection import close_db
from money_manager.services.accounts import list_accounts
from money_manager.services.backup import export_data
from money_manager.services.budgets import budget_summary, list_budgets, upsert_budget
from money_manager.services.categories import create_category, list_categories
from money_manager.services.loans import add_payment, create_loan, get_loan, loan_summary
from money_manager.services.pending import execute_due_pending
from money_manager.services.recurring import create_rule, generate_due_recurring, list_rules, update_rule
from money_manager.services.transactions import create_transaction, list_transactions


class MoneyLogicTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        config = type(
            "TestConfig",
            (),
            {
                "DATA_DIR": Path(self.temp_dir.name),
                "DATABASE": Path(self.temp_dir.name) / "test.sqlite3",
                "SECRET_KEY": "test",
                "TESTING": True,
            },
        )
        self.app = create_app(config)
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        close_db()
        self.ctx.pop()
        gc.collect()
        self.temp_dir.cleanup()

    def account(self, name):
        return next(account for account in list_accounts(active_only=False) if account["name"] == name)

    def test_credit_card_expense_creates_pending_settlement(self):
        nexi = self.account("Nexi")
        create_transaction(
            {
                "date": "2026-06-10",
                "type": "expense",
                "amount": 42.5,
                "category": "Food",
                "description": "Dinner",
                "account_id": nexi["id"],
            }
        )

        transactions = list_transactions(include_pending=True)
        pending = [tx for tx in transactions if tx["status"] == "pending"]

        self.assertEqual(len(transactions), 2)
        self.assertEqual(pending[0]["type"], "transfer")
        self.assertEqual(pending[0]["date"], "2026-06-15")
        self.assertEqual(pending[0]["is_credit_card_settlement"], 1)

    def test_due_pending_expense_posts_in_place_and_gets_settlement(self):
        nexi = self.account("Nexi")
        create_transaction(
            {
                "date": "2026-06-01",
                "type": "expense",
                "amount": 20,
                "category": "Software",
                "description": "Pending card charge",
                "account_id": nexi["id"],
                "status": "pending",
            },
            create_settlement=False,
        )

        execute_due_pending("2026-06-02")
        transactions = list_transactions(include_pending=True)

        self.assertEqual(len(transactions), 2)
        self.assertEqual(len([tx for tx in transactions if tx["status"] == "posted" and tx["type"] == "expense"]), 1)
        self.assertEqual(len([tx for tx in transactions if tx["status"] == "pending" and tx["type"] == "transfer"]), 1)

    def test_recurring_generation_and_edit(self):
        cash = self.account("Cash")
        rule_id = create_rule(
            {
                "name": "Salary",
                "type": "income",
                "amount": 100,
                "category": "Work",
                "description": "",
                "account_id": cash["id"],
                "merchant_id": None,
                "visual_mode": "standard",
                "frequency": "monthly",
                "next_due_date": "2026-06-01",
            }
        )
        update_rule(
            rule_id,
            {
                "name": "Salary Updated",
                "type": "income",
                "amount": 120,
                "category": "Work",
                "description": "",
                "account_id": cash["id"],
                "merchant_id": None,
                "visual_mode": "standard",
                "frequency": "monthly",
                "next_due_date": "2026-06-01",
                "is_active": True,
            },
        )
        generate_due_recurring("2026-06-30")

        self.assertEqual(list_rules()[0]["name"], "Salary Updated")
        self.assertEqual(len(list_transactions(include_pending=True)), 1)

    def test_recurring_not_advanced_before_due_date(self):
        cash = self.account("Cash")
        create_rule(
            {
                "name": "Future subscription",
                "type": "expense",
                "amount": 12,
                "category": "Software",
                "description": "",
                "account_id": cash["id"],
                "merchant_id": None,
                "visual_mode": "standard",
                "frequency": "monthly",
                "next_due_date": "2026-06-30",
            }
        )

        generate_due_recurring("2026-06-24")

        self.assertEqual(list_rules()[0]["next_due_date"], "2026-06-30")
        self.assertEqual(len(list_transactions(include_pending=True)), 0)

    def test_loan_payment_math(self):
        loan_id = create_loan(
            {
                "direction": "lent_out",
                "counterparty": "Marco",
                "principal_amount": 100,
                "expected_total_amount": 120,
                "start_date": "2026-06-24",
                "due_date": "2026-07-24",
                "notes": "",
            }
        )
        add_payment(loan_id, {"date": "2026-06-25", "amount": 40, "notes": ""})

        loan = get_loan(loan_id)
        self.assertEqual(loan["paid_amount"], 40)
        self.assertEqual(loan["outstanding_amount"], 80)
        self.assertEqual(loan_summary()["to_receive"], 80)

    def test_invalid_transfer_requires_destination(self):
        cash = self.account("Cash")
        with self.assertRaises(ValueError):
            create_transaction(
                {
                    "date": "2026-06-10",
                    "type": "transfer",
                    "amount": 10,
                    "account_id": cash["id"],
                }
            )

    def test_paypal_transfer_page_creates_transfer(self):
        paypal = self.account("PayPal")
        revolut = self.account("Revolut")
        client = self.app.test_client()

        response = client.post(
            "/paypal-transfer/",
            data={
                "destination_account_id": revolut["id"],
                "transfer_amount": "98.25",
            },
            follow_redirects=False,
        )
        transactions = list_transactions(include_pending=True)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0]["type"], "transfer")
        self.assertEqual(transactions[0]["amount"], 98.25)
        self.assertEqual(transactions[0]["account_id"], paypal["id"])
        self.assertEqual(transactions[0]["destination_account_id"], revolut["id"])

    def test_categories_budgets_and_backup_export(self):
        category_id = create_category(
            {
                "name": "Books",
                "type": "expense",
                "color": "#123456",
                "icon": "book",
            }
        )
        cash = self.account("Cash")
        create_transaction(
            {
                "date": "2026-06-10",
                "type": "expense",
                "amount": 15,
                "category": "Books",
                "description": "Novel",
                "account_id": cash["id"],
            }
        )
        upsert_budget({"month": "2026-06", "category_id": category_id, "amount": 50})

        budget = list_budgets("2026-06")[0]
        self.assertEqual(budget["spent_amount"], 15)
        self.assertEqual(budget_summary("2026-06")["remaining"], 35)
        self.assertIn("Books", [category["name"] for category in list_categories()])
        self.assertIn("transactions", export_data())


if __name__ == "__main__":
    unittest.main()
