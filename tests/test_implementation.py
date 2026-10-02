import copy
import io
import json
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from money_manager import create_app
from money_manager.db.connection import get_db, dict_factory
from money_manager.db.schema import SCHEMA
from money_manager.db.money_migration import migrate_money
from money_manager.services.accounts import list_accounts, create_account, account_balances
from money_manager.services.backup import export_bundle, validate_backup, restore_backup, read_backup, create_snapshot
from money_manager.services.recurring import create_rule
from money_manager.services.scheduling import process_scheduled
from money_manager.services.pending import mark_posted
from money_manager.services.transactions import create_transaction, update_transaction, get_transaction, list_transactions
from money_manager.services.transaction_details import save_splits, link_refund
from money_manager.utils.exchange import exchange_quote, to_eur, _CACHE


class ImplementationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        config = type("Config", (), dict(DATA_DIR=root, DATABASE=root / "test.sqlite3", MERCHANT_LOGO_DIR=root / "logos", SECRET_KEY="test", TESTING=True))
        self.app = create_app(config)
        with self.app.app_context():
            self.cash = next(a["id"] for a in list_accounts() if a["name"] == "Cash")
            self.card = create_account("Test credit card", "credit_card", settlement_account_id=self.cash, settlement_day=15)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()
        _CACHE.clear()

    def values(self, **changes):
        values = dict(date=date.today().isoformat(), type="expense", amount="42.50", currency="EUR", account_id=self.card, status="posted")
        values.update(changes)
        return values

    def test_edit_updates_pending_settlement_and_account_change_removes_it(self):
        with self.app.app_context():
            tx = create_transaction(self.values())
            original_settlement = get_db().execute("SELECT id FROM transactions WHERE settlement_for_transaction_id = ?", (tx,)).fetchone()["id"]
            update_transaction(tx, self.values(amount="100", description="Updated purchase"))
            settlement = get_db().execute("SELECT * FROM transactions WHERE settlement_for_transaction_id = ?", (tx,)).fetchone()
            self.assertEqual(settlement["id"], original_settlement)
            self.assertEqual(settlement["amount_minor"], 10000)
            self.assertIn("Updated purchase", settlement["description"])
            update_transaction(tx, self.values(account_id=self.cash, amount="100"))
            self.assertFalse(get_db().execute("SELECT 1 FROM transactions WHERE settlement_for_transaction_id = ?", (tx,)).fetchone())

    def test_posted_settlement_cannot_be_silently_changed(self):
        with self.app.app_context():
            tx = create_transaction(self.values())
            settlement = get_db().execute("SELECT id FROM transactions WHERE settlement_for_transaction_id = ?", (tx,)).fetchone()["id"]
            mark_posted(settlement)
            with self.assertRaisesRegex(ValueError, "already been settled"):
                update_transaction(tx, self.values(amount="100"))
            self.assertEqual(get_transaction(tx)["amount_minor"], 4250)
            update_transaction(tx, self.values(description="New note"))
            self.assertEqual(get_transaction(settlement)["amount_minor"], 4250)

    def test_money_is_stored_as_integers_and_balances_add_exactly(self):
        with self.app.app_context():
            for _ in range(100):
                create_transaction(self.values(account_id=self.cash, type="income", amount="0.01"))
            account = next(a for a in account_balances() if a["id"] == self.cash)
            self.assertEqual(account["balance"], 1)
            row = get_db().execute("SELECT SUM(amount_minor) AS cents, typeof(amount_minor) AS storage FROM transactions").fetchone()
            self.assertEqual((row["cents"], row["storage"]), (100, "integer"))
            with self.assertRaises(ValueError):
                create_transaction(self.values(amount="0.001"))

    def test_split_tracks_a_one_cent_edit_and_refund_limit_is_exact(self):
        with self.app.app_context():
            tx = create_transaction(self.values(account_id=self.cash, amount="10"))
            save_splits(tx, [("Groceries", "5"), ("Transport", "5")])
            update_transaction(tx, self.values(account_id=self.cash, amount="10.01"))
            self.assertEqual(get_db().execute("SELECT SUM(amount_eur_minor) AS total FROM transaction_splits").fetchone()["total"], 1001)
            refund = create_transaction(self.values(account_id=self.cash, type="income", amount="10.02"))
            with self.assertRaises(ValueError):
                link_refund(refund, tx)

    def test_health_assets_and_pages_do_not_process_schedules(self):
        with self.app.app_context():
            rule = create_rule(dict(name="Due today", type="expense", amount="10", account_id=self.cash, frequency="monthly", next_due_date=date.today().isoformat()))
        for url in ("/health", "/static/js/app.js", "/", "/api/dashboard"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            response.close()
        with self.app.app_context():
            self.assertEqual(len(list_transactions(include_pending=True)), 0)
            process_scheduled()
            self.assertEqual(get_db().execute("SELECT COUNT(*) AS n FROM transactions WHERE recurring_rule_id = ?", (rule,)).fetchone()["n"], 1)

    def test_concurrent_schedule_runs_create_one_occurrence(self):
        with self.app.app_context():
            rule = create_rule(dict(name="Concurrent", type="expense", amount="10", account_id=self.card, frequency="monthly", next_due_date=date.today().isoformat()))
        def run():
            with self.app.app_context():
                process_scheduled()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: run(), range(4)))
        with self.app.app_context():
            expenses = get_db().execute("SELECT * FROM transactions WHERE recurring_rule_id = ?", (rule,)).fetchall()
            self.assertEqual(len(expenses), 1)
            self.assertEqual(expenses[0]["status"], "posted")
            self.assertEqual(get_db().execute("SELECT COUNT(*) AS n FROM transactions WHERE settlement_for_transaction_id = ?", (expenses[0]["id"],)).fetchone()["n"], 1)

    def test_schedule_failure_rolls_back_occurrence_and_due_date(self):
        with self.app.app_context():
            rule = create_rule(dict(name="Retry", type="expense", amount="10", account_id=self.cash, frequency="monthly", next_due_date=date.today().isoformat()))
            with patch("money_manager.services.recurring.create_transaction", side_effect=ValueError("failure")):
                with self.assertRaises(ValueError):
                    process_scheduled()
            self.assertFalse(get_db().execute("SELECT 1 FROM recurring_occurrences WHERE recurring_rule_id = ?", (rule,)).fetchone())
            process_scheduled()
            self.assertEqual(len(list_transactions()), 1)

    def test_invalid_account_input_keeps_values_and_does_not_create_record(self):
        for amount in ("abc", "NaN", "Infinity", "0.001"):
            response = self.client.post("/accounts/new", data=dict(name="Preserved name", type="bank", opening_balance=amount))
            self.assertEqual(response.status_code, 400)
            self.assertIn("Preserved name", response.text)
        with self.app.app_context():
            self.assertFalse(get_db().execute("SELECT 1 FROM accounts WHERE name = 'Preserved name'").fetchone())

    def test_csrf_rejects_missing_and_accepts_valid_token(self):
        self.app.config["CSRF_ENABLED"] = True
        values = self.values(account_id=self.cash)
        self.assertEqual(self.client.post("/transactions/new", data=values).status_code, 400)
        page = self.client.get("/transactions/new").text
        values["csrf_token"] = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        self.assertEqual(self.client.post("/transactions/new", data=values).status_code, 302)
        values["csrf_token"] = "invalid"
        self.assertEqual(self.client.post("/transactions/new", data=values).status_code, 400)

    def test_paginated_transactions_preserve_filters(self):
        with self.app.app_context():
            for index in range(55):
                create_transaction(self.values(account_id=self.cash, description=f"Purchase {index}"))
        page = self.client.get(f"/transactions/?account_id={self.cash}").text
        self.assertEqual(page.count('data-transaction-detail '), 50)
        self.assertIn("1–50 of 55 transactions", page)
        second = self.client.get(f"/transactions/?account_id={self.cash}&page=2&mode=table").text
        self.assertIn("51–55 of 55 transactions", second)
        self.assertEqual(self.client.get("/transactions/?page=abc").status_code, 200)

    def test_backup_roundtrip_restores_records_and_logos(self):
        with self.app.app_context():
            create_transaction(self.values(account_id=self.cash))
            logo = self.app.config["MERCHANT_LOGO_DIR"] / "saved.png"
            logo.write_bytes(b"saved-logo")
            original = export_bundle()
            create_transaction(self.values(account_id=self.cash, amount="15"))
            logo.write_bytes(b"changed-logo")
            snapshot = restore_backup(original)
            self.assertTrue(snapshot.exists())
            self.assertEqual(export_bundle()["data"], original["data"])
            self.assertEqual(logo.read_bytes(), b"saved-logo")

    def test_invalid_backup_does_not_change_existing_data(self):
        with self.app.app_context():
            create_transaction(self.values(account_id=self.cash))
            original = export_bundle()
            invalid = copy.deepcopy(original)
            invalid["data"]["transactions"][0]["account_id"] = 9999
            with self.assertRaises(ValueError):
                restore_backup(invalid)
            self.assertEqual(export_bundle()["data"], original["data"])
            invalid = copy.deepcopy(original)
            invalid["merchant_logos"] = {"../secret.png": "YQ=="}
            with self.assertRaises(ValueError):
                validate_backup(invalid)

    def test_snapshot_can_be_previewed_and_restored(self):
        with self.app.app_context():
            create_transaction(self.values(account_id=self.cash))
            original = export_bundle()
            snapshot = create_snapshot("test")
            with snapshot.open("rb") as file:
                payload = read_backup(file)
            create_transaction(self.values(account_id=self.cash, amount="15"))
            restore_backup(payload)
            self.assertEqual(export_bundle()["data"], original["data"])
            with snapshot.open("rb") as file:
                response = self.client.post("/backup/", data={"file": (io.BytesIO(file.read()), "snapshot.zip")})
            self.assertEqual(response.status_code, 200)
            self.assertIn("Backup checked", response.text)

    def test_conflicting_backup_amounts_are_rejected(self):
        with self.app.app_context():
            create_transaction(self.values(account_id=self.cash))
            payload = export_bundle()
            payload["data"]["transactions"][0]["amount_minor"] += 1
            with self.assertRaisesRegex(ValueError, "Conflicting amounts"):
                validate_backup(payload)

    def test_legacy_backup_and_http_preview_restore(self):
        with self.app.app_context():
            create_transaction(self.values(account_id=self.cash))
            backup = export_bundle()
            # Legacy JSON exports used major-unit amounts and lacked metadata.
            from money_manager.utils.money import MONEY_COLUMNS
            legacy_tables=set(MONEY_COLUMNS)|{'merchants','categories','payment_preferences','transaction_trash','import_batches','import_rules','transaction_import_hashes','transaction_links','transaction_tags','budget_templates'}
            backup['data']={table:rows for table,rows in backup['data'].items() if table in legacy_tables}
            backup.update(version=1)
            backup.pop('schema_version',None)
            for rows in backup["data"].values():
                for row in rows:
                    for key in list(row):
                        if key.endswith("_minor") or key.startswith("exchange_rate"):
                            row.pop(key)
            validate_backup(backup)
        response = self.client.post("/backup/", data={"file": (io.BytesIO(json.dumps(backup).encode()), "backup.json")})
        self.assertEqual(response.status_code, 200)
        preview = re.search(r'name="preview_id" value="([^"]+)"', response.text).group(1)
        self.assertEqual(self.client.post("/backup/", data=dict(action="restore", preview_id=preview)).status_code, 302)

    def test_fx_fallback_is_flagged_and_expires(self):
        _CACHE.clear()
        with patch("money_manager.utils.exchange.urlopen", side_effect=OSError("offline")):
            quote = exchange_quote("USD")
            self.assertEqual(quote["source"], "estimated")
            self.assertEqual(to_eur("0.50", "USD", quote), 0.47)
            with self.app.app_context():
                tx = create_transaction(self.values(account_id=self.cash, currency="USD", amount="10"))
                self.assertEqual(get_transaction(tx)["exchange_rate_source"], "estimated")
            _CACHE["USD"]["expires"] = -1
            exchange_quote("USD")
        with self.assertRaises(ValueError):
            exchange_quote("XYZ")

    def test_integer_migration_preserves_ids_links_and_amounts(self):
        path = Path(self.temp.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            db.row_factory = dict_factory
            # Old releases added EUR amounts with ALTER TABLE, leaving the
            # final column and the table's closing parenthesis on one line.
            db.executescript(SCHEMA.replace("    amount_eur REAL NOT NULL DEFAULT 0,\n", ""))
            db.execute("ALTER TABLE transactions ADD COLUMN amount_eur REAL NOT NULL DEFAULT 0")
            db.execute("INSERT INTO accounts (id, name, type, opening_balance) VALUES (20, 'Legacy', 'bank', 12.34)")
            db.execute("INSERT INTO transactions (id,date,type,amount,amount_eur,account_id) VALUES (30,'2026-01-01','expense',0.29,0.29,20)")
            db.execute("INSERT INTO transaction_tags (transaction_id, tag) VALUES (30, 'Keep me')")
            db.commit()
            migrate_money(db)
            self.assertEqual(db.execute("SELECT amount_minor FROM transactions WHERE id=30").fetchone()["amount_minor"], 29)
            self.assertEqual(db.execute("SELECT opening_balance_minor FROM accounts WHERE id=20").fetchone()["opening_balance_minor"], 1234)
            self.assertEqual(db.execute("SELECT transaction_id FROM transaction_tags").fetchone()["transaction_id"], 30)
            self.assertFalse(db.execute("PRAGMA foreign_key_check").fetchall())
            migrate_money(db)  # Idempotent after an interrupted version marker.


if __name__ == "__main__":
    unittest.main()
