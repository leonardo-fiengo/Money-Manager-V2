from money_manager.db.connection import get_db


def list_merchants():
    return get_db().execute("SELECT * FROM merchants ORDER BY name").fetchall()


def get_merchant(merchant_id):
    return get_db().execute("SELECT * FROM merchants WHERE id = ?", (merchant_id,)).fetchone()


def create_merchant(name, logo=None, website=None, default_category=None):
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO merchants (name, logo, website, default_category)
        VALUES (?, ?, ?, ?)
        """,
        (name, logo, website, default_category),
    )
    db.commit()
    return cursor.lastrowid


def update_merchant(merchant_id, name, logo=None, website=None, default_category=None):
    db = get_db()
    db.execute(
        """
        UPDATE merchants
        SET name = ?, logo = ?, website = ?, default_category = ?
        WHERE id = ?
        """,
        (name, logo, website, default_category, merchant_id),
    )
    db.commit()


def normalize_merchant_logos(uploaded_filenames):
    db = get_db()
    merchants = list_merchants()
    lowered = {name.lower(): name for name in uploaded_filenames}
    for merchant in merchants:
        logo = (merchant["logo"] or "").strip().strip('"').strip("'")
        if not logo or logo.startswith(("http://", "https://", "/static/")):
            continue

        filename = logo.replace("\\", "/").split("/")[-1]
        candidates = [filename.lower(), f"{merchant['name'].lower()}.png"]
        match = next((lowered[name] for name in candidates if name in lowered), None)
        if not match:
            continue

        db.execute(
            "UPDATE merchants SET logo = ? WHERE id = ?",
            (f"/static/uploads/merchants/{match}", merchant["id"]),
        )
    db.commit()
