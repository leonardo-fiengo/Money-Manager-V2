import copy
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from money_manager import create_app
from money_manager.db.connection import get_db
from money_manager.db.migration import run_migrations
from money_manager.services.accounts import account_balances, create_account
from money_manager.services.account_detail import account_detail
from money_manager.services.backup import export_bundle, validate_backup, restore_backup
from money_manager.services.pots import save_pot, move_pot, assign_sources, spend_pot, delete_pot, restore_pot, savings_summary
from money_manager.services.relationships import match_transfer
from money_manager.services.transactions import create_transaction, list_transactions
from money_manager.services.transaction_details import save_splits, link_refund


class AccountGoalsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        config = type('TestConfig',(),dict(DATA_DIR=root,DATABASE=root/'test.sqlite3',MERCHANT_LOGO_DIR=root/'logos',SECRET_KEY='test',TESTING=True))
        self.app = create_app(config)
        self.ctx = self.app.app_context(); self.ctx.push()
        self.client = self.app.test_client()
        self.bank = create_account('Goal bank','bank',100)
        self.wallet = create_account('Goal wallet','wallet',200)

    def tearDown(self):
        self.ctx.pop(); self.temp.cleanup()

    def balances(self):
        return {a['id']:a['balance'] for a in account_balances()}

    def transaction(self, **changes):
        data = dict(date=date.today().isoformat(),type='expense',amount=10,account_id=self.bank,description='Goal test')
        data.update(changes)
        return create_transaction(data)

    def test_split_contributions_release_and_spend_exactly_once(self):
        before = self.balances()
        pot = save_pot('Trip',100,60,sources={self.bank:20,self.wallet:40})
        move_pot(pot,50,'add',sources={self.bank:20,self.wallet:30})
        move_pot(pot,10,'release',sources={self.bank:10})
        self.assertEqual(self.balances(),before)
        self.assertEqual(savings_summary()['reserved'],100)
        with self.assertRaises(ValueError): spend_pot(pot)
        spend_pot(pot,True)
        after = self.balances()
        self.assertEqual(after[self.bank],before[self.bank]-30)
        self.assertEqual(after[self.wallet],before[self.wallet]-70)
        self.assertEqual(savings_summary()['reserved'],0)
        self.assertEqual(len(savings_summary()['spent']),1)
        with self.assertRaises(ValueError): spend_pot(pot,True)
        self.assertEqual(self.balances(),after)
        expenses = get_db().execute("SELECT * FROM transactions WHERE description='Savings goal: Trip'").fetchall()
        self.assertEqual([r['amount_eur_minor'] for r in expenses],[3000,7000])

    def test_source_validation_and_other_reservations(self):
        save_pot('First',90,90,sources={self.bank:90})
        for sources in [{self.bank:11},{self.bank:-1},{99999:1}]:
            with self.assertRaises(ValueError): save_pot('Bad',20,sum(sources.values()),sources=sources)
        with self.assertRaises(ValueError): save_pot('Wrong sum',100,20,sources={self.wallet:19.99})
        with self.assertRaises(ValueError): save_pot('Fractions',10,'1.001',sources={self.wallet:'1.001'})
        card = create_account('Debt source','credit_card',100)
        with self.assertRaises(ValueError): save_pot('Credit is not savings',10,10,sources={card:10})
        self.assertEqual(len(savings_summary()['pots']),1)

    def test_spending_depleted_or_archived_sources_is_atomic(self):
        pot = save_pot('Trip',100,100,sources={self.bank:50,self.wallet:50})
        self.transaction(amount=175,account_id=self.wallet)
        before = self.balances()
        with self.assertRaises(ValueError): spend_pot(pot,True)
        self.assertEqual(self.balances(),before)
        self.assertEqual(savings_summary()['reserved'],100)
        # Release remains possible when the balance has fallen below the reservation.
        move_pot(pot,30,'release',sources={self.wallet:30})
        self.assertEqual(savings_summary()['reserved'],70)
        get_db().execute('UPDATE accounts SET is_active=0 WHERE id=?',(self.bank,)); get_db().commit()
        move_pot(pot,10,'release',sources={self.bank:10})
        with self.assertRaises(ValueError): move_pot(pot,1,'add',sources={self.bank:1})

    def test_mid_spend_failure_rolls_back_first_expense(self):
        pot = save_pot('Trip',100,100,sources={self.bank:50,self.wallet:50})
        before = self.balances()
        def fail_second(data, **kwargs):
            if data['account_id']==self.wallet: raise ValueError('Second account failed')
            return create_transaction(data,**kwargs)
        with patch('money_manager.services.transactions.create_transaction',side_effect=fail_second):
            with self.assertRaises(ValueError): spend_pot(pot,True)
        self.assertEqual(self.balances(),before)
        self.assertEqual(get_db().execute('SELECT COUNT(*) AS n FROM pot_spending').fetchone()['n'],0)
        self.assertEqual(savings_summary()['reserved'],100)

    def test_delete_restore_preserves_balances_and_cannot_overreserve(self):
        before = self.balances()
        pot = save_pot('Dream',100,100,sources={self.bank:100})
        delete_pot(pot)
        self.assertEqual(self.balances(),before)
        self.assertEqual(savings_summary()['reserved'],0)
        other = save_pot('Replacement',100,100,sources={self.bank:100})
        with self.assertRaises(ValueError): restore_pot(pot)
        delete_pot(other); restore_pot(pot)
        self.assertEqual(savings_summary()['reserved'],100)
        spend_pot(pot,True)
        after = self.balances()
        delete_pot(pot); restore_pot(pot)
        self.assertEqual(self.balances(),after)
        self.assertEqual(len(savings_summary()['spent']),1)

    def test_legacy_pot_requires_sources_and_backup_keeps_them(self):
        pot = save_pot('Old dream',50,50)
        with self.assertRaises(ValueError): spend_pot(pot,True)
        assign_sources(pot,{self.bank:20,self.wallet:30})
        payload = export_bundle(); validate_backup(payload)
        spend_pot(pot,True)
        spent = export_bundle(); validate_backup(spent)
        restore_backup(payload)
        self.assertEqual(savings_summary()['reserved'],50)
        self.assertEqual(len(savings_summary()['pots'][0]['sources']),2)
        restore_backup(spent)
        self.assertEqual(len(savings_summary()['spent'][0]['spending']),2)
        old = copy.deepcopy(payload)
        old['schema_version']=11
        for table in ['pot_sources','pot_movement_sources','pot_spending']: old['data'].pop(table)
        for row in old['data']['savings_pots']:
            row.pop('spent_at'); row.pop('deleted_at')
        restore_backup(old)
        self.assertEqual(savings_summary()['pots'][0]['unattributed'],50)
        before = get_db().execute('SELECT COUNT(*) AS n FROM schema_migrations').fetchone()['n']
        run_migrations(get_db())
        self.assertEqual(get_db().execute('SELECT COUNT(*) AS n FROM schema_migrations').fetchone()['n'],before)
        self.assertIsNone(get_db().execute('PRAGMA foreign_key_check').fetchone())

    def test_account_detail_incoming_transfers_refunds_splits_and_history(self):
        self.transaction(type='transfer',account_id=self.wallet,destination_account_id=self.bank,amount=20)
        expense = self.transaction(amount=40,category='Groceries')
        save_splits(expense,[('Groceries',25),('Transport',15)])
        refund = self.transaction(type='income',amount=10)
        link_refund(refund,expense,'refund')
        self.transaction(status='pending',amount=999)
        detail = account_detail(self.bank)
        self.assertEqual(detail['account']['balance'],90)
        self.assertEqual(detail['month_in'],20)
        self.assertEqual(detail['monthly_spending'],30)
        self.assertEqual(detail['spent'],30)
        self.assertEqual(detail['history'][-1]['balance'],90)
        self.assertEqual(len(detail['recent']),3)
        page = self.client.get(f'/accounts/{self.bank}')
        self.assertEqual(page.status_code,200)
        self.assertIn('accountBalanceChart',page.text)
        self.assertIn('data-page-back',page.text)
        self.assertIn(f'/accounts/{self.bank}',self.client.get('/accounts/').text)
        self.assertEqual(self.client.get('/accounts/999999').status_code,404)

    def test_paired_transfer_uses_incoming_booking_date_once(self):
        yesterday = (date.today()-timedelta(days=1)).isoformat()
        outgoing = self.transaction(type='expense',amount=20,date=yesterday,account_id=self.wallet)
        incoming = self.transaction(type='income',amount=20)
        match_transfer(outgoing,incoming)
        detail = account_detail(self.bank)
        self.assertEqual(detail['month_in'],20)
        self.assertEqual([r['id'] for r in detail['recent']],[incoming])
        self.assertEqual(len(list_transactions(dict(account_id=self.bank,account_activity=True))),1)
        self.assertEqual(len(list_transactions(dict(account_activity=True))),1)

    def test_http_pot_workflow_confirmation_and_csrf(self):
        response = self.client.post('/accounts/pots',data={'name':'Holiday','target':'50','reserved':'50',f'source_{self.bank}':'20',f'source_{self.wallet}':'30'})
        self.assertEqual(response.status_code,302)
        pot = savings_summary()['pots'][0]['id']
        page = self.client.get('/accounts/pots').text
        self.assertIn('Spend them already',page)
        self.assertIn('Where from?',page)
        before = self.balances()
        self.client.post(f'/accounts/pots/{pot}/spend')
        self.assertEqual(self.balances(),before)
        self.client.post(f'/accounts/pots/{pot}/spend',data={'confirm':'yes'})
        self.assertEqual(self.balances()[self.bank],before[self.bank]-20)
        self.app.config['CSRF_ENABLED']=True
        self.assertEqual(self.client.post(f'/accounts/pots/{pot}/delete').status_code,400)


if __name__=='__main__': unittest.main()
