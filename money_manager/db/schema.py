SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK (type IN ('bank', 'cash', 'wallet', 'prepaid_card', 'credit_card', 'investment')),
    logo TEXT,
    opening_balance REAL NOT NULL DEFAULT 0,
    settlement_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    settlement_day INTEGER CHECK (settlement_day BETWEEN 1 AND 28),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS merchants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    logo TEXT,
    website TEXT,
    default_category TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL DEFAULT 'expense' CHECK (type IN ('expense', 'income', 'investment', 'transfer', 'any')),
    color TEXT NOT NULL DEFAULT '#64748b',
    icon TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('expense', 'income', 'investment', 'transfer')),
    amount REAL NOT NULL CHECK (amount >= 0),
    currency TEXT NOT NULL DEFAULT 'EUR',
    amount_eur REAL NOT NULL DEFAULT 0,
    category TEXT,
    description TEXT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    destination_account_id INTEGER REFERENCES accounts(id) ON DELETE RESTRICT,
    merchant_id INTEGER REFERENCES merchants(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted', 'pending')),
    is_credit_card_settlement INTEGER NOT NULL DEFAULT 0,
    settlement_for_transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    recurring_rule_id INTEGER REFERENCES recurring_rules(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recurring_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('expense', 'income', 'investment')),
    amount REAL NOT NULL CHECK (amount >= 0),
    category TEXT,
    description TEXT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    merchant_id INTEGER REFERENCES merchants(id) ON DELETE SET NULL,
    visual_mode TEXT NOT NULL DEFAULT 'auto' CHECK (visual_mode IN ('auto', 'merchant_logo', 'standard')),
    is_subscription INTEGER NOT NULL DEFAULT 0,
    frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly', 'monthly', 'yearly')),
    next_due_date TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL CHECK (direction IN ('lent_out', 'borrowed')),
    counterparty TEXT NOT NULL,
    principal_amount REAL NOT NULL CHECK (principal_amount >= 0),
    expected_total_amount REAL NOT NULL CHECK (expected_total_amount >= 0),
    start_date TEXT NOT NULL,
    due_date TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS loan_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    amount REAL NOT NULL CHECK (amount >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (month, category_id)
);

CREATE TABLE IF NOT EXISTS payment_preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    mode TEXT NOT NULL DEFAULT 'auto' CHECK (mode IN ('auto', 'manual')),
    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS balance_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    expected REAL NOT NULL,
    actual REAL NOT NULL,
    adjustment REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    batch_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (batch_id, account_id)
);

CREATE TABLE IF NOT EXISTS transaction_trash (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    restored_at TEXT
);

CREATE TABLE IF NOT EXISTS savings_pots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target REAL NOT NULL CHECK (target > 0),
    reserved REAL NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    filename TEXT NOT NULL,
    headers_json TEXT NOT NULL,
    rows_json TEXT NOT NULL,
    mapping_json TEXT,
    status TEXT NOT NULL DEFAULT 'mapping',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS import_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    needle TEXT NOT NULL,
    merchant_id INTEGER REFERENCES merchants(id) ON DELETE SET NULL,
    category TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS transaction_import_hashes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS transaction_splits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    amount_eur REAL NOT NULL CHECK (amount_eur > 0)
);
CREATE TABLE IF NOT EXISTS transaction_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    related_transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('refund', 'reimbursement')),
    UNIQUE(source_transaction_id, related_transaction_id)
);
CREATE TABLE IF NOT EXISTS transaction_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    UNIQUE(transaction_id, tag)
);
CREATE TABLE IF NOT EXISTS pot_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pot_id INTEGER NOT NULL REFERENCES savings_pots(id) ON DELETE CASCADE,
    delta REAL NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS budget_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    rows_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_recurring_due ON recurring_rules(next_due_date, is_active);
CREATE INDEX IF NOT EXISTS idx_loans_status ON loans(status);
CREATE INDEX IF NOT EXISTS idx_loan_payments_loan ON loan_payments(loan_id);
CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name);
CREATE INDEX IF NOT EXISTS idx_budgets_month ON budgets(month);
CREATE INDEX IF NOT EXISTS idx_import_hashes_fingerprint ON transaction_import_hashes(fingerprint);
CREATE INDEX IF NOT EXISTS idx_transaction_splits_tx ON transaction_splits(transaction_id);
CREATE INDEX IF NOT EXISTS idx_transaction_tags_tag ON transaction_tags(tag);
"""
