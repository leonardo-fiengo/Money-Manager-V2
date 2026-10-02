"""Additive migrations for import, review and planning workflows."""


def migrate_roadmap(db):
    tables = [
        "CREATE TABLE import_profiles (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL, headers_json TEXT NOT NULL, mapping_json TEXT NOT NULL)",
        "CREATE TABLE merchant_aliases (id INTEGER PRIMARY KEY, merchant_id INTEGER NOT NULL REFERENCES merchants(id) ON DELETE CASCADE, alias TEXT NOT NULL, normalized TEXT NOT NULL UNIQUE)",
        "CREATE TABLE finance_rules (id INTEGER PRIMARY KEY, name TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0, conditions_json TEXT NOT NULL, actions_json TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1)",
        "CREATE TABLE transaction_relationships (id INTEGER PRIMARY KEY, source_transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE, related_transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE, originals_json TEXT, kind TEXT NOT NULL CHECK(kind IN ('transfer_pair','credit_card_settlement','chargeback')), UNIQUE(source_transaction_id,related_transaction_id,kind), CHECK(source_transaction_id != related_transaction_id))",
        "CREATE TABLE reconciliation_sessions (id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id), through_date TEXT NOT NULL, expected_minor INTEGER NOT NULL, actual_minor INTEGER NOT NULL, adjustment_minor INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'closed', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE reconciliation_transactions (session_id INTEGER NOT NULL REFERENCES reconciliation_sessions(id) ON DELETE CASCADE, transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE, PRIMARY KEY(session_id,transaction_id))",
        "CREATE TABLE forecast_scenarios (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, income_delta_minor INTEGER NOT NULL DEFAULT 0, spending_delta_minor INTEGER NOT NULL DEFAULT 0, investment_delta_minor INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE transaction_attachments (id INTEGER PRIMARY KEY, transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE, filename TEXT NOT NULL, storage_name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
        "CREATE TABLE net_worth_snapshots (id INTEGER PRIMARY KEY, date TEXT NOT NULL UNIQUE, balance_minor INTEGER NOT NULL, accounts_json TEXT NOT NULL)",
        "CREATE TABLE app_preferences (id INTEGER PRIMARY KEY CHECK(id=1), widgets_json TEXT NOT NULL DEFAULT '[\"accounts\",\"cashflow\",\"upcoming\",\"budgets\"]')",
        "CREATE TABLE inbox_dismissals (id INTEGER PRIMARY KEY, item_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
    ]
    db.commit()
    try:
        db.execute('BEGIN IMMEDIATE')
        for sql in tables:
            db.execute(sql)
        for sql in [
            "ALTER TABLE transactions ADD COLUMN is_transfer_mirror INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE transactions ADD COLUMN notes TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE transactions ADD COLUMN is_subscription INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE transactions ADD COLUMN reconciled_session_id INTEGER REFERENCES reconciliation_sessions(id) ON DELETE SET NULL",
            "ALTER TABLE balance_checks ADD COLUMN session_id INTEGER REFERENCES reconciliation_sessions(id) ON DELETE SET NULL",
            "ALTER TABLE savings_pots ADD COLUMN target_date TEXT",
            "ALTER TABLE recurring_rules ADD COLUMN currency TEXT NOT NULL DEFAULT 'EUR'",
            "ALTER TABLE recurring_rules ADD COLUMN amount_eur_minor INTEGER NOT NULL DEFAULT 0 CHECK(typeof(amount_eur_minor)='integer')",
            "ALTER TABLE import_batches ADD COLUMN original_json TEXT",
            "ALTER TABLE import_batches ADD COLUMN encoding TEXT",
            "CREATE INDEX idx_aliases_merchant ON merchant_aliases(merchant_id)",
            "CREATE INDEX idx_relationships_related ON transaction_relationships(related_transaction_id)",
            "CREATE INDEX idx_reconciled_transactions ON transactions(reconciled_session_id)",
        ]:
            db.execute(sql)
        db.execute("CREATE VIEW ledger_transactions AS SELECT * FROM transactions WHERE is_transfer_mirror=0")
        db.execute('UPDATE recurring_rules SET amount_eur_minor=amount_minor')
        db.execute("INSERT INTO transaction_relationships(source_transaction_id,related_transaction_id,kind) SELECT settlement_for_transaction_id,id,'credit_card_settlement' FROM transactions WHERE settlement_for_transaction_id IS NOT NULL")
        db.execute("ALTER TABLE transaction_links RENAME TO transaction_links_legacy")
        db.execute("CREATE TABLE transaction_links (id INTEGER PRIMARY KEY AUTOINCREMENT, source_transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE, related_transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE, kind TEXT NOT NULL CHECK(kind IN ('refund','reimbursement','chargeback')), UNIQUE(source_transaction_id,related_transaction_id))")
        db.execute("INSERT INTO transaction_links SELECT * FROM transaction_links_legacy")
        db.execute("DROP TABLE transaction_links_legacy")
        db.execute("CREATE VIRTUAL TABLE transaction_search USING fts5(description, merchant, category, notes, tokenize='unicode61 remove_diacritics 2')")
        db.execute("INSERT INTO transaction_search(rowid,description,merchant,category,notes) SELECT t.id,t.description,m.name,t.category,t.notes FROM transactions t LEFT JOIN merchants m ON m.id=t.merchant_id")
        for name, event, body in [
            ('insert','AFTER INSERT', "INSERT INTO transaction_search(rowid,description,merchant,category,notes) VALUES (new.id,new.description,(SELECT name FROM merchants WHERE id=new.merchant_id),new.category,new.notes);"),
            ('delete','AFTER DELETE', "DELETE FROM transaction_search WHERE rowid=old.id;"),
            ('update','AFTER UPDATE', "DELETE FROM transaction_search WHERE rowid=old.id; INSERT INTO transaction_search(rowid,description,merchant,category,notes) VALUES (new.id,new.description,(SELECT name FROM merchants WHERE id=new.merchant_id),new.category,new.notes);"),
        ]:
            db.execute(f'CREATE TRIGGER transaction_search_{name} {event} ON transactions BEGIN {body} END')
        db.execute("CREATE TRIGGER merchant_search_update AFTER UPDATE OF name ON merchants BEGIN UPDATE transaction_search SET merchant=new.name WHERE rowid IN (SELECT id FROM transactions WHERE merchant_id=new.id); END")
        db.execute("INSERT OR IGNORE INTO schema_migrations(name) VALUES('011_finance_workflows')")
        db.commit()
    except Exception:
        db.rollback()
        raise
