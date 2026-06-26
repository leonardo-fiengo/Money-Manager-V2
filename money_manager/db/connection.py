import sqlite3

from flask import current_app, g


def dict_factory(cursor, row):
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = dict_factory
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
