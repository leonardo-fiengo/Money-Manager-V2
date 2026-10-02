import re

from money_manager.utils.money import MONEY_COLUMNS, to_minor


def migrate_money(db):
    """Rebuild legacy money tables atomically, preserving IDs, FKs and indexes.

    Integer minor units are the stored values. Generated major-unit columns keep
    existing templates and read queries compatible without duplicate storage.
    """
    db.commit()
    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.execute("BEGIN IMMEDIATE")
        for table, money_columns in MONEY_COLUMNS.items():
            columns = [row["name"] for row in db.execute(f"PRAGMA table_info({table})")]
            if money_columns[0] + "_minor" in columns:
                continue
            rows = db.execute(f"SELECT * FROM {table}").fetchall()
            indexes = [row["sql"] for row in db.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL", (table,)
            )]
            sql = db.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()["sql"]
            for column in money_columns:
                match = re.search(rf"\b{column}\s+REAL\b", sql, flags=re.I)
                if not match:
                    raise ValueError(f"Cannot migrate {table}.{column} safely.")
                # ALTER TABLE can append the final column beside the table's
                # closing parenthesis. Find the column boundary, not a newline.
                end, depth, quoted = match.end(), 0, False
                while end < len(sql):
                    char = sql[end]
                    if char == "'":
                        quoted = not quoted
                    elif not quoted:
                        if char == "(":
                            depth += 1
                        elif char == ")":
                            if depth == 0:
                                break
                            depth -= 1
                        elif char == "," and depth == 0:
                            break
                    end += 1
                constraints = re.sub(rf"\b{column}\b", column + "_minor", sql[match.end():end]).rstrip()
                replacement = (f"{column}_minor INTEGER{constraints} CHECK(typeof({column}_minor) = 'integer'), "
                               f"{column} REAL GENERATED ALWAYS AS ({column}_minor / 100.0) VIRTUAL")
                sql = sql[:match.start()] + replacement + sql[end:]
            db.execute(f"DROP TABLE {table}")
            db.execute(sql)
            storage_columns = [column + "_minor" if column in money_columns else column for column in columns]
            for row in rows:
                db.execute(f"INSERT INTO {table} ({','.join(storage_columns)}) VALUES ({','.join('?' for _ in columns)})",
                           [to_minor(row[column], rounding=True) if column in money_columns else row[column] for column in columns])
            for index in indexes:
                db.execute(index)
        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError("Money migration failed its foreign-key check.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys = ON")
