from money_manager.db.atomic import atomic


def migrate_people(db):
    with atomic(db):
        db.execute("CREATE TABLE contacts (id INTEGER PRIMARY KEY, name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 100), email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        for column in ("email TEXT NOT NULL DEFAULT ''", "phone TEXT NOT NULL DEFAULT ''", "avatar_data TEXT"):
            db.execute(f'ALTER TABLE local_profile ADD COLUMN {column}')
        db.execute('ALTER TABLE transactions ADD COLUMN contact_id INTEGER REFERENCES contacts(id)')
        db.execute('CREATE INDEX transaction_contact ON transactions(contact_id)')
        db.execute('ALTER TABLE loans ADD COLUMN contact_id INTEGER REFERENCES contacts(id)')
        db.execute("ALTER TABLE loans ADD COLUMN kind TEXT NOT NULL DEFAULT 'loan' CHECK(kind IN ('loan','debt'))")
        db.execute("""CREATE TABLE taxes (id INTEGER PRIMARY KEY, name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 100),
            amount_minor INTEGER NOT NULL CHECK(typeof(amount_minor)='integer' AND amount_minor>0 AND amount_minor<=99999999900),
            due_date TEXT NOT NULL, tax_year INTEGER NOT NULL CHECK(tax_year BETWEEN 1900 AND 2200),
            authority TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE tax_payments (id INTEGER PRIMARY KEY, tax_id INTEGER NOT NULL REFERENCES taxes(id) ON DELETE CASCADE,
            date TEXT NOT NULL, amount_minor INTEGER NOT NULL CHECK(typeof(amount_minor)='integer' AND amount_minor>0 AND amount_minor<=99999999900),
            notes TEXT NOT NULL DEFAULT '')""")
        db.execute("""CREATE TABLE tax_estimates (id INTEGER PRIMARY KEY, tax_year INTEGER NOT NULL CHECK(tax_year BETWEEN 1900 AND 2200),
            inputs_json TEXT NOT NULL, result_json TEXT NOT NULL, rules_version TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
