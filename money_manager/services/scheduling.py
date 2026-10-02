import threading

from money_manager.db.atomic import atomic
from money_manager.db.connection import get_db
from money_manager.services.pending import execute_due_pending
from money_manager.services.recurring import generate_due_recurring


def process_scheduled():
    with atomic(get_db()):
        generate_due_recurring()
        execute_due_pending()


def start_scheduler(app):
    stop = threading.Event()

    def work():
        while not stop.wait(60):
            try:
                with app.app_context():
                    from money_manager.services.backup import create_snapshot
                    create_snapshot()
                    process_scheduled()
                    from money_manager.services.history import capture_net_worth
                    capture_net_worth()
            except Exception:
                app.logger.exception("Scheduled payments could not be processed")

    threading.Thread(target=work, name="money-manager-scheduler", daemon=True).start()
    return stop
