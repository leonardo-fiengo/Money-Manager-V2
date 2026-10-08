import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from money_manager import create_app
from money_manager.db.connection import get_db, close_db
from money_manager.services.accounts import create_account, account_balances
from money_manager.services.analytics import cumulative_balance, dashboard_metrics
from money_manager.services.dashboard_overview import balance_series, flow_summary, overview_summary
from money_manager.services.reconciliation import check_payload, preview_balances, record_checks
from money_manager.services.relationships import match_transfer
from money_manager.services.transaction_details import link_refund
from money_manager.services.transactions import create_transaction


class DashboardOverviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        config = type('Config', (), dict(DATA_DIR=root,DATABASE=root/'test.sqlite3',
            MERCHANT_LOGO_DIR=root/'logos',SECRET_KEY='test',TESTING=True))
        self.app = create_app(config)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()
        self.bank = create_account('Overview bank','bank',1000)
        self.today = date.today()

    def tearDown(self):
        close_db()
        self.ctx.pop()
        self.temp.cleanup()

    def tx(self, **changes):
        data = dict(date=self.today.isoformat(),type='expense',amount=10,
                    account_id=self.bank,description='Overview test')
        data.update(changes)
        return create_transaction(data)

    def test_history_reconciles_openings_transfers_cards_archived_fx_and_pending(self):
        card = create_account('Overview credit','credit_card',-100,self.bank,20)
        archived = create_account('Overview old','wallet',200)
        investment = create_account('Overview investments','investment',2000)
        self.tx(type='income',amount=300)
        self.tx(type='transfer',amount=250,destination_account_id=investment)
        self.tx(type='transfer',amount=40,destination_account_id=archived)
        self.tx(account_id=card,amount=25)
        fx = self.tx(amount=5)
        get_db().execute('UPDATE transactions SET currency=?,amount_minor=?,amount_eur_minor=? WHERE id=?',('USD',1000,900,fx))
        self.tx(status='pending',amount=500,date=(self.today+timedelta(days=2)).isoformat())
        get_db().execute('UPDATE accounts SET is_active=0 WHERE id=?',(archived,))
        get_db().commit()
        expected=sum(a['balance'] for a in account_balances())
        for period in ['1w','1m','3m','1y','all']:
            with self.subTest(period=period):
                result=balance_series(period)
                self.assertEqual(result['total'],expected)
                self.assertEqual(result['points'][-1]['balance'],expected)
                self.assertEqual(result['change'],266)
        self.assertEqual(expected,3366)

    def test_matched_transfer_mirror_never_adds_income_to_combined_balance(self):
        other=create_account('Overview other','cash',100)
        outgoing=self.tx(amount=25)
        incoming=self.tx(type='income',account_id=other,amount=25)
        match_transfer(outgoing,incoming)
        result=balance_series('all')
        self.assertEqual(result['total'],1100)
        self.assertEqual(result['change'],0)
        self.assertEqual(dashboard_metrics()['income'],0)

    def test_reconciliation_adjustment_uses_statement_date(self):
        yesterday=(self.today-timedelta(days=1)).isoformat()
        self.tx(date=yesterday,amount=10)
        rows=preview_balances({str(self.bank):'980'},yesterday)
        record_checks(check_payload(rows),[str(self.bank)],'Statement date')
        points={p['date']:p['balance'] for p in cumulative_balance()}
        self.assertEqual(points[yesterday],980)
        self.assertEqual(balance_series()['total'],980)

    def test_positive_baseline_percentage_and_no_fake_zero_baseline_growth(self):
        self.tx(type='income',amount=100)
        self.assertEqual(balance_series('1m')['percent'],10)
        get_db().execute('UPDATE accounts SET opening_balance_minor=0')
        get_db().commit()
        self.assertIsNone(balance_series('1m')['percent'])

    def test_future_posted_import_is_flagged_instead_of_faking_today_history(self):
        self.tx(amount=40,date=(self.today+timedelta(days=1)).isoformat())
        result=balance_series()
        self.assertTrue(result['has_future'])
        self.assertEqual(result['total'],960)

    def test_cash_flow_excludes_refunds_from_income_and_investments_from_net(self):
        self.tx(type='income',amount=400)
        expense=self.tx(amount=100)
        refund=self.tx(type='income',amount=25)
        link_refund(refund,expense)
        self.tx(type='investment',amount=50)
        self.tx(type='transfer',amount=10,destination_account_id=create_account('Flow wallet','wallet'))
        result=flow_summary(3)
        self.assertEqual(result['rows'][-1]['income'],400)
        self.assertEqual(result['rows'][-1]['expenses'],75)
        self.assertEqual(result['rows'][-1]['net'],275)
        self.assertIsNone(result['comparisons']['income'])
        self.assertEqual(flow_summary(999)['months'],6)

    def test_safe_spend_requires_review_for_unlinked_due_taxes(self):
        get_db().execute('INSERT INTO taxes(name,tax_year,amount_minor,due_date) VALUES(?,?,?,?)',('Test tax',self.today.year,10000,self.today.isoformat()))
        get_db().commit()
        overview=overview_summary()
        self.assertIsNone(overview['safe_available'])
        self.assertEqual(overview['unlinked_due'],1)

    def test_upcoming_preserves_overdue_date_and_pending_detail_link(self):
        due=(self.today-timedelta(days=3)).isoformat()
        tx=self.tx(date=due,status='pending',description='Overdue fixture')
        item=next(row for row in overview_summary()['upcoming'] if row['transaction_id']==tx)
        self.assertEqual(item['date'],due)
        self.assertTrue(item['overdue'])
        page=self.client.get('/').text
        self.assertIn('Overdue · ',page)
        self.assertIn(f'href="/transactions/{tx}/details"',page)

    def test_overview_routes_empty_states_and_custom_workspace_are_read_only(self):
        before=[tuple(row.values()) for row in get_db().execute('SELECT * FROM transactions')]
        page=self.client.get('/')
        self.assertEqual(page.status_code,200)
        for value in ['overviewBalanceChart','overviewFlowChart','Safe to Spend','Recent Transactions','Custom workspace']:
            self.assertIn(value,page.text)
        self.assertNotIn('money-garden',page.text)
        self.assertEqual(self.client.get('/overview/balance?range=bad').json['period'],'3m')
        self.assertEqual(self.client.get('/overview/cash-flow?months=12').json['months'],12)
        self.assertIn('today-widget-grid',self.client.get('/?view=workspace').text)
        after=[tuple(row.values()) for row in get_db().execute('SELECT * FROM transactions')]
        self.assertEqual(before,after)
