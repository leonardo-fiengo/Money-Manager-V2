from money_manager.db.connection import get_db


DEFAULT_CATEGORIES = [
    ("Groceries", "expense", "#147d64", "basket"),
    ("Restaurants", "expense", "#d45f3a", "utensils"),
    ("Subscription", "expense", "#376fd0", "repeat"),
    ("Transport", "expense", "#d9941f", "car"),
    ("Health", "expense", "#be3455", "heart"),
    ("Salary", "income", "#128051", "$"),
    ("Investments", "investment", "#275eb8", "chart"),
]


def seed_default_categories():
    db = get_db()
    for name, category_type, color, icon in DEFAULT_CATEGORIES:
        db.execute(
            """
            INSERT OR IGNORE INTO categories (name, type, color, icon)
            VALUES (?, ?, ?, ?)
            """,
            (name, category_type, color, icon),
        )
        db.execute(
            "UPDATE categories SET icon = ?, color = ? WHERE name = ? AND icon IN ('G', 'R', 'S', 'T', 'H', 'I', 'arrow-up', 'trending-up')",
            (icon, color, name),
        )
    db.commit()


def list_categories(active_only=True):
    where = "WHERE is_active = 1" if active_only else ""
    return get_db().execute(
        f"SELECT * FROM categories {where} ORDER BY type, name"
    ).fetchall()


def get_category(category_id):
    return get_db().execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()


def create_category(data):
    _validate_category(data)
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO categories (name, type, color, icon, is_active)
        VALUES (?, ?, ?, ?, 1)
        """,
        (data["name"].strip(), data["type"], data.get("color") or "#64748b", data.get("icon") or None),
    )
    db.commit()
    return cursor.lastrowid


def update_category(category_id, data):
    _validate_category(data)
    db = get_db()
    db.execute(
        """
        UPDATE categories
        SET name = ?, type = ?, color = ?, icon = ?, is_active = ?
        WHERE id = ?
        """,
        (
            data["name"].strip(),
            data["type"],
            data.get("color") or "#64748b",
            data.get("icon") or None,
            int(data.get("is_active", True)),
            category_id,
        ),
    )
    db.commit()


def category_names():
    return [row["name"] for row in list_categories()]


def _validate_category(data):
    if not (data.get("name") or "").strip():
        raise ValueError("Category name is required.")
    if data.get("type") not in {"expense", "income", "investment", "transfer", "any"}:
        raise ValueError("Unsupported category type.")
