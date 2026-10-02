from contextlib import contextmanager
from uuid import uuid4


@contextmanager
def atomic(db):
    """Serialize writers, and keep nested operations inside their parent's commit."""
    nested = db.in_transaction
    name = "save_" + uuid4().hex
    db.execute(f"SAVEPOINT {name}" if nested else "BEGIN IMMEDIATE")
    try:
        yield
        db.execute(f"RELEASE SAVEPOINT {name}") if nested else db.commit()
    except Exception:
        if nested:
            db.execute(f"ROLLBACK TO SAVEPOINT {name}")
            db.execute(f"RELEASE SAVEPOINT {name}")
        else:
            db.rollback()
        raise
