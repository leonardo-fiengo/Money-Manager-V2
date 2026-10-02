import json
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from money_manager import create_app
from money_manager.db.connection import close_db
from money_manager.services.accounts import list_accounts
from money_manager.services.transactions import create_transaction


class CalendarPanelTest(unittest.TestCase):
    def test_calendar_panel_payload_preserves_prices_and_escapes_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = type('Config', (), dict(DATA_DIR=root, DATABASE=root / 'test.sqlite3', MERCHANT_LOGO_DIR=root / 'logos', SECRET_KEY='test', TESTING=True))
            app = create_app(config)
            with app.app_context():
                accounts = list_accounts()
                cash = next(a['id'] for a in accounts if a['name'] == 'Cash')
                card = next(a['id'] for a in accounts if a['name'] == 'Nexi')
                today = date.today().isoformat()
                note = '<script>alert("test")</script>'
                create_transaction(dict(date=today, type='expense', amount=12.50, account_id=cash, description=note))
                create_transaction(dict(date=today, type='transfer', amount=25, account_id=cash, destination_account_id=card, description='Move money'))
                future = (date.today() + timedelta(days=2)).isoformat()
                create_transaction(dict(date=future, status='pending', type='expense', amount=19.99, account_id=cash, description='Upcoming payment'))
                client = app.test_client()
                page = client.get('/calendar/').get_data(as_text=True)
                self.assertIn('data-calendar-panel', page)
                self.assertIn('data-open-payment="0"', page)
                self.assertIn('data-open-day="' + today + '"', page)
                raw = re.search(r'id="calendar-event-data">(.*?)</script>', page, re.S).group(1)
                self.assertNotIn('<script>', raw)
                events = json.loads(raw)
                expense = next(e for e in events[today] if e['name'] == note)
                self.assertEqual((expense['amount'], expense['price']), (-12.5, 12.5))
                transfer = next(e for e in events[today] if e['type'] == 'transfer')
                self.assertEqual((transfer['amount'], transfer['price']), (0, 25))
                if future[:7] == today[:7]:
                    self.assertTrue(any(e['name'] == 'Upcoming payment' and e['source'] == 'pending' for e in events[future]))
                empty = client.get('/calendar/?month=invalid')
                self.assertEqual(empty.status_code, 200)
                close_db()

