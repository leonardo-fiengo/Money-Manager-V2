import json
import tempfile
import unittest
from pathlib import Path

from money_manager import create_app
from money_manager.db.connection import get_db
from money_manager.services.backup import export_bundle, restore_backup
from money_manager.services.history import dashboard_layout, dashboard_widgets, save_widgets


class WorkspaceEditorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        config = type('Config', (), dict(DATA_DIR=root, DATABASE=root/'test.sqlite3',
                      MERCHANT_LOGO_DIR=root/'logos', SECRET_KEY='test', TESTING=True))
        self.app = create_app(config)
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.context.pop()
        self.temp.cleanup()

    def test_legacy_selection_keeps_core_cards_and_new_default_matches_home(self):
        self.assertEqual(dashboard_widgets(), ['position','actions','pulse','upcoming','budgets','accounts','cashflow'])
        get_db().execute('INSERT INTO app_preferences(id,widgets_json) VALUES(1,?)', (json.dumps(['accounts']),))
        get_db().commit()
        self.assertEqual(dashboard_widgets(), ['position','actions','pulse','accounts'])
        response = self.client.post('/settings/', data=dict(action='widgets', widgets=['accounts']))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(dashboard_widgets(), ['position','actions','pulse','accounts'])

    def test_order_sizes_and_empty_canvas_survive_save_and_backup(self):
        save_widgets(['accounts','position','cashflow'], {'accounts':'half','position':'full'})
        before = dashboard_layout()
        self.assertEqual([block['id'] for block in before], ['accounts','position','cashflow'])
        self.assertEqual([block['width'] for block in before], ['half','full','full'])
        page = self.client.get('/?view=workspace').text
        self.assertLess(page.index('data-widget-id="accounts"'), page.index('data-widget-id="position"'))
        bundle = export_bundle()
        save_widgets([])
        self.assertIn('A blank canvas.', self.client.get('/?view=workspace').text)
        restore_backup(bundle)
        self.assertEqual(dashboard_layout(), before)

    def test_invalid_widgets_or_widths_leave_saved_layout_unchanged(self):
        save_widgets(['pulse'])
        for widgets, widths in [(['unknown'], {}), (['pulse'], {'pulse':'tiny'}), (['pulse'], {'accounts':'full'})]:
            with self.assertRaises(ValueError):
                save_widgets(widgets, widths)
            self.assertEqual(dashboard_widgets(), ['pulse'])
        for payload in [dict(widgets=['accounts','accounts'],widths=['half','full']),
                        dict(widgets=['accounts'],widths=[]), dict(widgets=['accounts'],widths=['tiny'])]:
            self.assertEqual(self.client.post('/settings/workspace', data=payload).status_code, 400)
            self.assertEqual(dashboard_widgets(), ['pulse'])

    def test_editor_save_has_csrf_and_never_changes_financial_records(self):
        self.app.config['CSRF_ENABLED'] = True
        db = get_db()
        accounts = [tuple(row) for row in db.execute('SELECT * FROM accounts')]
        transactions = [tuple(row) for row in db.execute('SELECT * FROM transactions')]
        page = self.client.get('/settings/workspace')
        self.assertEqual(page.status_code, 200)
        self.assertIn('data-workspace-editor', page.text)
        data = dict(widgets=['accounts','pulse'], widths=['half','full'])
        self.assertEqual(self.client.post('/settings/workspace', data=data).status_code, 400)
        with self.client.session_transaction() as session:
            data['csrf_token'] = session['csrf_token']
        response = self.client.post('/settings/workspace', data=data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(dashboard_widgets(), ['accounts','pulse'])
        self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM accounts')], accounts)
        self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM transactions')], transactions)


if __name__ == '__main__':
    unittest.main()
