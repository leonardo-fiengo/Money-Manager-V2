import copy
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from money_manager import create_app
from money_manager.db.connection import get_db
from money_manager.services.accounts import create_account, account_balances
from money_manager.services.activity_review import categorize_review
from money_manager.services.backup import export_bundle, validate_backup, restore_backup
from money_manager.services.budgets import upsert_budget
from money_manager.services.cockpit import cockpit_summary, plan_summary
from money_manager.services.pots import save_pot, spend_pot
from money_manager.services.profile import save_profile, local_profile
from money_manager.services.transactions import create_transaction, get_transaction, delete_transaction


class CockpitTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        config = type('Config', (), dict(DATA_DIR=root,DATABASE=root/'test.sqlite3',MERCHANT_LOGO_DIR=root/'logos',SECRET_KEY='test',TESTING=True))
        self.app = create_app(config)
        self.ctx = self.app.app_context(); self.ctx.push()
        self.client = self.app.test_client()
        self.bank = create_account('Everyday','bank',1000)
        self.tomorrow = (date.today()+timedelta(days=1)).isoformat()

    def tearDown(self):
        self.ctx.pop(); self.temp.cleanup()

    def tx(self, **changes):
        data = dict(date=date.today().isoformat(),type='expense',amount=10,account_id=self.bank,description='Review purchase')
        data.update(changes)
        return create_transaction(data)

    def test_available_excludes_income_investments_and_counts_card_debt_once(self):
        card = create_account('Credit','credit_card',-100,self.bank,20)
        investment = create_account('Invested','investment',8000)
        archived = create_account('Archived','bank',20000)
        get_db().execute('UPDATE accounts SET is_active=0 WHERE id=?',(archived,)); get_db().commit()
        save_pot('Future',200,100,sources={self.bank:100})
        self.tx(date=self.tomorrow,status='pending',amount=50,category='Groceries')
        self.tx(date=self.tomorrow,status='pending',type='income',amount=500)
        self.tx(date=self.tomorrow,status='pending',type='transfer',amount=100,destination_account_id=card)
        self.tx(date=self.tomorrow,status='pending',account_id=card,amount=20)
        self.tx(date=self.tomorrow,status='pending',account_id=investment,amount=200)
        result=cockpit_summary()
        self.assertEqual(result['available'],730)
        self.assertEqual(result['bills'],70)
        self.assertEqual(result['card_debt'],100)
        self.assertLessEqual(len(result['top_actions']),3)
        self.tx(date=self.tomorrow,status='pending',type='transfer',amount=15,destination_account_id=card)
        self.assertEqual(cockpit_summary()['available'],715)

    def test_monthly_budget_overlap_and_spent_goal_are_not_double_counted(self):
        self.tx(type='income',amount=1000)
        self.tx(amount=20,category='Groceries')
        self.tx(date=self.tomorrow,status='pending',amount=30,category='Groceries')
        category = get_db().execute("SELECT id FROM categories WHERE name='Groceries'").fetchone()['id']
        upsert_budget(dict(month=date.today().strftime('%Y-%m'),category_id=category,amount=100))
        pot=save_pot('Thing',50,50,sources={self.bank:50})
        self.assertEqual(plan_summary()['remainder'],850)
        spend_pot(pot,True)
        result=plan_summary()
        self.assertEqual(result['remainder'],850)
        self.assertEqual(result['flexible'],50)
        self.assertEqual(result['goal_contributions'],0)

    def imported(self):
        tx=self.tx()
        batch=get_db().execute("INSERT INTO import_batches(account_id,filename,headers_json,rows_json) VALUES(?,'review.csv','[]','[]')",(self.bank,)).lastrowid
        get_db().execute('INSERT INTO transaction_import_hashes(transaction_id,batch_id,fingerprint) VALUES(?,?,?)',(tx,batch,f'cockpit-{tx}'))
        get_db().commit()
        return tx

    def test_bulk_review_is_atomic_and_preserves_financial_fields(self):
        first,second=self.imported(),self.imported()
        before={row['id']:row['balance'] for row in account_balances()}
        with self.assertRaises(ValueError): categorize_review([first,99999],'Groceries')
        self.assertIsNone(get_transaction(first)['category'])
        self.assertEqual(categorize_review([first,second],'Groceries'),2)
        self.assertEqual(get_transaction(first)['amount_eur_minor'],1000)
        self.assertEqual(before,{row['id']:row['balance'] for row in account_balances()})
        with self.assertRaises(ValueError): categorize_review([first],'Health')

    def test_activity_views_recovery_and_side_panel_forms(self):
        imported=self.imported()
        pending=self.tx(date=self.tomorrow,status='pending',description='Upcoming purchase')
        self.assertIn('Review purchase',self.client.get('/transactions/?view=review').text)
        self.assertIn('Upcoming purchase',self.client.get('/transactions/?view=pending').text)
        self.assertNotIn('Review purchase</strong>',self.client.get('/transactions/?view=pending').text)
        delete_transaction(imported)
        response=self.client.get('/transactions/?view=deleted')
        self.assertEqual(response.status_code,200)
        self.assertIn('Restore transaction',response.text)
        panel=self.client.get(f'/transactions/{pending}/details?panel=1')
        self.assertEqual(panel.headers['X-Frame-Options'],'SAMEORIGIN')
        self.assertNotIn('class="app-navbar"',panel.text)
        response=self.client.post(f'/transactions/{pending}/details?panel=1',data=dict(action='notes',notes='A note'))
        self.assertIn('panel=1',response.location)
        self.assertEqual(get_transaction(pending)['notes'],'A note')
        self.assertEqual(self.client.get(f'/transactions/{pending}/details').headers['X-Frame-Options'],'DENY')

    def test_profile_and_roles_survive_backup_and_csrf(self):
        save_profile('Local person')
        get_db().execute("UPDATE accounts SET role='savings' WHERE id=?",(self.bank,));get_db().commit()
        bundle=export_bundle()
        save_profile('Changed')
        validate_backup(bundle);restore_backup(bundle)
        self.assertEqual(local_profile()['display_name'],'Local person')
        self.assertEqual(next(a for a in cockpit_summary()['accounts'] if a['id']==self.bank)['role_group'],'savings')
        old=copy.deepcopy(bundle);old['schema_version']=12;old['data'].pop('local_profile')
        for account in old['data']['accounts']: account.pop('role',None)
        validate_backup(old)
        self.app.config['CSRF_ENABLED']=True
        self.assertEqual(self.client.post('/profile/',data={'display_name':'No token'}).status_code,400)
        self.assertEqual(local_profile()['display_name'],'Local person')
        with self.assertRaises(ValueError): save_profile('x'*61)

    def test_workspaces_and_plan_tabs_render(self):
        save_pot('Reserved',100,20,sources={self.bank:20})
        for path in ['/', '/plan/', '/profile/', '/accounts/',f'/accounts/{self.bank}', '/transactions/?view=review','/transactions/?view=deleted']:
            with self.subTest(path=path):
                page=self.client.get(path)
                self.assertEqual(page.status_code,200)
                self.assertIn('aria-label="Quick controls"',page.text)
        for path in ['/plan/','/budgets/','/calendar/','/recurring/','/accounts/pots','/forecast/']:
            with self.subTest(path=path): self.assertIn('aria-label="Plan views"',self.client.get(path).text)
