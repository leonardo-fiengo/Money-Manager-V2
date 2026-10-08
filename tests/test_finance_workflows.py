import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from werkzeug.datastructures import FileStorage

from money_manager import create_app
from money_manager.db.connection import get_db
from money_manager.db.migration import run_migrations
from money_manager.services.accounts import account_balances, create_account, list_accounts
from money_manager.services.analytics import dashboard_metrics
from money_manager.services.backup import export_bundle, read_backup, restore_backup, validate_backup, create_snapshot
from money_manager.services.backup_encryption import configure_encryption, decrypt_snapshot, encrypt_snapshot
from money_manager.services.importing import create_batch, save_mapping, save_profile, preview_batch, confirm_batch, rollback_batch, get_batch
from money_manager.services.transactions import create_transaction, update_transaction, delete_transaction, get_transaction, list_transactions, restore_transaction
from money_manager.services.transaction_details import save_tags, save_splits, link_refund
from money_manager.services.rules import apply_rules, save_alias, save_finance_rule, preview_rule
from money_manager.services.relationships import match_transfer, unmatch_transfer
from money_manager.services.reconciliation import balance_at, check_payload, preview_balances, record_checks, reopen_session, reconciliation_history
from money_manager.services.forecasting import cash_forecast, save_scenario, list_scenarios
from money_manager.services.subscriptions import detected_subscriptions, track_subscription
from money_manager.services.attachments import save_attachment, attachments_for, attachment_directory
from money_manager.services.history import save_widgets
from money_manager.services.planning import save_pot, savings_summary
from money_manager.services.merchants import create_merchant


class FinanceWorkflowsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        config=type('TestConfig',(),dict(DATA_DIR=root,DATABASE=root/'test.sqlite3',MERCHANT_LOGO_DIR=root/'logos',SECRET_KEY='test',TESTING=True))
        self.app=create_app(config)
        self.ctx=self.app.app_context(); self.ctx.push()
        self.client=self.app.test_client()
        self.cash=next(a['id'] for a in list_accounts() if a['name']=='Cash')
        self.bank=create_account('Bank review','bank')
        create_merchant('Amazon review',default_category='Groceries')

    def tearDown(self):
        self.ctx.pop(); self.temp.cleanup()

    def tx(self, **extra):
        data=dict(date=date.today().isoformat(),type='expense',amount='10.00',account_id=self.cash,description='Review payment')
        data.update(extra)
        return create_transaction(data)

    def batch(self, account=None, content=None):
        content=content or f'date,description,amount\n{date.today().isoformat()},Review imported,-12.34\n'
        file=FileStorage(io.BytesIO(content.encode('utf-16')),filename='bank.csv')
        batch=create_batch(file,account or self.cash)
        if get_batch(batch)['status']=='mapping':
            save_mapping(batch,dict(date='date',description='description',amount='amount',date_format='ymd',expense_sign='negative',default_currency='EUR'))
        return batch

    def test_all_review_pages_render_and_back_is_only_on_subpages(self):
        for path in ['/','/settings/','/accounts/','/tools/rules','/tools/imports','/tools/recovery','/tools/transfers','/tools/aliases','/tools/reconciliation','/tools/net-worth','/forecast/?days=60','/recurring/subscriptions','/accounts/check','/backup/','/accounts/pots']:
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,200)
                self.assertNotIn('Traceback',response.text)
                if path in ['/','/settings/','/accounts/']:
                    self.assertNotIn('data-page-back',response.text)

    def test_import_profile_encoding_idempotency_and_rollback(self):
        batch=self.batch(); save_profile(batch,'Bank statement')
        self.assertEqual(get_batch(batch)['encoding'],'utf-16')
        self.assertEqual(confirm_batch(batch,[0]),1)
        with self.assertRaises(ValueError): confirm_batch(batch,[0])
        retry=self.batch()
        self.assertEqual(get_batch(retry)['status'],'review')
        self.assertTrue(preview_batch(retry)[0]['duplicate'])
        self.assertEqual(confirm_batch(retry,[]),0)
        self.assertEqual(rollback_batch(batch),1)
        self.assertEqual(get_batch(batch)['status'],'rolled_back')
        fresh=self.batch()
        self.assertFalse(preview_batch(fresh)[0]['duplicate'])

    def test_old_import_snapshots_ignore_only_the_new_empty_contact_field(self):
        batch=self.batch()
        confirm_batch(batch,[0])
        saved=json.loads(get_batch(batch)['original_json'])
        for original in saved['transactions'].values(): original.pop('contact_id',None)
        for details in saved['details'].values():
            for settlement in details.get('settlements',[]): settlement.pop('contact_id',None)
        get_db().execute('UPDATE import_batches SET original_json=? WHERE id=?',(json.dumps(saved),batch));get_db().commit()
        self.assertEqual(rollback_batch(batch),1)

    def test_rollback_refuses_changed_details_atomically(self):
        b=self.batch(content=f'date,description,amount\n{date.today().isoformat()},First,-10\n{date.today().isoformat()},Second,-20\n')
        confirm_batch(b,[0,1])
        ids=[r['transaction_id'] for r in get_db().execute('SELECT transaction_id FROM transaction_import_hashes WHERE batch_id=?',(b,))]
        save_tags(ids[1],'Changed after import')
        with self.assertRaisesRegex(ValueError,'changed'): rollback_batch(b)
        self.assertTrue(all(get_transaction(i) for i in ids))
        self.assertEqual(get_batch(b)['status'],'done')

    def test_card_import_rollback_and_relationship_recovery(self):
        card=create_account('Review credit card','credit_card',0,self.bank,20)
        b=self.batch(card); confirm_batch(b,[0])
        self.assertEqual(get_db().execute('SELECT COUNT(*) AS n FROM transaction_relationships').fetchone()['n'],1)
        rollback_batch(b)
        self.assertEqual(get_db().execute('SELECT COUNT(*) AS n FROM transactions').fetchone()['n'],0)
        trash=get_db().execute('SELECT id FROM transaction_trash').fetchone()['id']; restore_transaction(trash)
        self.assertEqual(get_db().execute('SELECT COUNT(*) AS n FROM transaction_relationships').fetchone()['n'],1)

    def test_rule_priority_preview_alias_and_ignore(self):
        merchant=get_db().execute('SELECT id FROM merchants LIMIT 1').fetchone()['id']
        save_alias(merchant,'AMZN Mktp IT')
        self.tx(description='AMZN Mktp IT')
        lower=dict(name='Ordinary',priority=1,contains='AMZN',category='Groceries')
        upper=dict(name='Priority',priority=20,pattern='amzn',min_amount='5',max_amount='50',account_id=str(self.cash),tags='Work, Iceland',rename='Amazon purchase',subscription='1')
        self.assertEqual(len(preview_rule(upper)),1)
        self.assertEqual(get_db().execute('SELECT COUNT(*) AS n FROM finance_rules').fetchone()['n'],0)
        save_finance_rule(lower); save_finance_rule(upper)
        b=self.batch(content=f'date,description,amount\n{date.today().isoformat()},AMZN Mktp IT,-23\n')
        row=preview_batch(b)[0]['item']
        self.assertEqual(row['merchant_id'],merchant)
        self.assertEqual(row['matched_rule'],'Priority')
        confirm_batch(b,[0])
        imported=get_db().execute('SELECT * FROM transactions ORDER BY id DESC LIMIT 1').fetchone()
        self.assertEqual(imported['description'],'Amazon purchase')
        self.assertEqual(imported['is_subscription'],1)
        self.assertEqual(len(get_db().execute('SELECT * FROM transaction_tags WHERE transaction_id=?',(imported['id'],)).fetchall()),2)
        save_finance_rule(dict(name='Ignore',priority=100,contains='AMZN',ignore='1'))
        self.assertTrue(preview_batch(self.batch())[0]['item'].get('ignored',False)==False)
        with self.assertRaises(ValueError): save_finance_rule(dict(name='Bad',pattern='(',ignore='1'))

    def test_manual_merchant_correction_teaches_alias(self):
        tx=self.tx(description='CARD UNFAMILIAR SHOP')
        merchant=get_db().execute('SELECT id FROM merchants LIMIT 1').fetchone()['id']
        data=dict(get_transaction(tx),merchant_id=merchant)
        update_transaction(tx,data)
        self.assertEqual(get_db().execute('SELECT merchant_id FROM merchant_aliases').fetchone()['merchant_id'],merchant)

    def test_transfer_pair_preserves_balances_and_historical_booking_dates(self):
        yesterday=(date.today()-timedelta(days=1)).isoformat()
        outgoing=self.tx(date=yesterday,amount='25')
        incoming=self.tx(type='income',account_id=self.bank,amount='25')
        before=account_balances()
        before_history=balance_at(self.bank,yesterday)
        relationship=match_transfer(outgoing,incoming)
        self.assertEqual(account_balances(),before)
        self.assertEqual(balance_at(self.bank,yesterday),before_history)
        metrics=dashboard_metrics(); self.assertEqual(metrics['income'],0);self.assertEqual(metrics['expenses'],0)
        self.assertEqual(len(list_transactions()),1)
        with self.assertRaises(ValueError): delete_transaction(incoming)
        with self.assertRaises(ValueError): update_transaction(outgoing,dict(get_transaction(outgoing),amount=30))
        unmatch_transfer(relationship)
        self.assertEqual(account_balances(),before)
        self.assertEqual(len(list_transactions()),2)

    def test_reconciliation_cutoff_overlapping_sessions_and_delete_guard(self):
        yesterday=(date.today()-timedelta(days=1)).isoformat()
        older=self.tx(date=yesterday)
        newer=self.tx(amount=5)
        record_checks(check_payload(preview_balances({str(self.cash):'-10'},yesterday)),[],'First')
        self.assertTrue(get_transaction(older)['reconciled_session_id'])
        self.assertFalse(get_transaction(newer)['reconciled_session_id'])
        record_checks(check_payload(preview_balances({str(self.cash):'-15'})),[],'Second')
        history=reconciliation_history(); newest=history[0]['id']; first=history[1]['id']
        self.assertEqual([r['transaction_count'] for r in history],[2,1])
        reopen_session(newest)
        self.assertEqual(get_transaction(older)['reconciled_session_id'],first)
        with self.assertRaises(ValueError): delete_transaction(older)
        reopen_session(first); delete_transaction(older)
        self.assertIsNone(get_transaction(older))

    def test_reconciliation_explains_duplicate_and_stale_preview(self):
        self.tx(); self.tx()
        rows=preview_balances({str(self.cash):'-10'})
        self.assertTrue(rows[0]['candidates'][0]['possible_duplicate'])
        payload=check_payload(rows); self.tx(amount=1)
        with self.assertRaisesRegex(ValueError,'changed'): record_checks(payload,[str(self.cash)],'')
        self.assertEqual(len(reconciliation_history()),0)

    def test_forecast_transfer_zero_total_scenarios_do_not_write_transactions(self):
        future=(date.today()+timedelta(days=2)).isoformat()
        self.tx(type='transfer',amount=100,account_id=self.bank,destination_account_id=self.cash,date=future,status='pending')
        baseline=cash_forecast(60)
        self.assertEqual(baseline['projected'],baseline['opening'])
        self.assertEqual(baseline['events'][0]['amount'],0)
        save_scenario('Spend less',spending=-300)
        scenario=cash_forecast(60,list_scenarios()[0]['id'])
        self.assertGreater(scenario['projected'],baseline['projected'])
        self.assertEqual(get_db().execute('SELECT COUNT(*) AS n FROM transactions').fetchone()['n'],1)
        self.assertEqual(len(scenario['curve']),61)

    def test_subscription_pattern_price_increase_and_tracking(self):
        merchant=get_db().execute('SELECT id FROM merchants LIMIT 1').fetchone()['id']
        for when,amount in [((date.today()-timedelta(days=90)).isoformat(),20),((date.today()-timedelta(days=60)).isoformat(),20),((date.today()-timedelta(days=30)).isoformat(),23)]:
            self.tx(date=when,amount=amount,merchant_id=merchant)
        candidates=detected_subscriptions();self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]['price_increase'],3)
        track_subscription(candidates[0]['id'])
        self.assertEqual(detected_subscriptions(),[])
        self.assertEqual(self.client.get('/recurring/subscriptions').status_code,200)

    def test_notes_fts_attachments_and_backup_roundtrip(self):
        tx=self.tx()
        self.assertEqual(self.client.post(f'/transactions/{tx}/details',data=dict(action='notes',notes='Iceland university receipt')).status_code,302)
        self.assertEqual(list_transactions({'search':'iceland university'})[0]['id'],tx)
        save_attachment(tx,FileStorage(io.BytesIO(b'review receipt'),filename='receipt.txt'))
        attachment=attachments_for(tx)[0]
        with self.client.get(f"/tools/attachments/{attachment['id']}") as response:
            self.assertEqual(response.data,b'review receipt')
        payload=export_bundle(); validate_backup(payload)
        delete_transaction(tx);restore_backup(payload)
        self.assertEqual(attachments_for(tx)[0]['filename'],'receipt.txt')
        self.assertEqual(list_transactions({'search':'iceland'})[0]['id'],tx)
        snapshot=create_snapshot('roundtrip')
        with snapshot.open('rb') as file: validate_backup(read_backup(file))

    def test_encrypted_snapshot_wrong_passphrase_and_tampering(self):
        configure_encryption('a long review passphrase')
        encrypted=encrypt_snapshot(b'private review data')
        self.assertEqual(decrypt_snapshot(encrypted,'a long review passphrase'),b'private review data')
        with self.assertRaises(ValueError): decrypt_snapshot(encrypted,'wrong passphrase')
        with self.assertRaises(ValueError): decrypt_snapshot(encrypted[:-8]+b'corrupt!')
        snapshot=create_snapshot('encrypted-test')
        self.assertEqual(snapshot.suffix,'.mmbackup')
        with snapshot.open('rb') as file: validate_backup(read_backup(file,'a long review passphrase'))

    def test_chargeback_net_expenses_and_over_refund_edit_guard(self):
        expense=self.tx(amount=100,category='Groceries')
        refund=self.tx(type='income',amount=25)
        link_refund(refund,expense,'chargeback')
        metrics=dashboard_metrics();self.assertEqual(metrics['income'],0);self.assertEqual(metrics['expenses'],75)
        with self.assertRaises(ValueError):update_transaction(refund,dict(get_transaction(refund),amount=101))

    def test_goals_widgets_schema_and_integrity(self):
        self.tx(type='income',amount=1000)
        save_pot('Trip',500,50,target_date='2027-06-01')
        self.assertEqual(savings_summary()['pots'][0]['target_date'],'2027-06-01')
        save_widgets(['accounts'])
        page=self.client.get('/?view=workspace').text
        self.assertNotIn('studio-cashflow',page);self.assertIn('studio-accounts',page)
        before=get_db().execute('SELECT COUNT(*) AS n FROM schema_migrations').fetchone()['n']
        run_migrations(get_db())
        self.assertEqual(get_db().execute('SELECT COUNT(*) AS n FROM schema_migrations').fetchone()['n'],before)
        self.assertEqual(get_db().execute('PRAGMA integrity_check').fetchone()['integrity_check'],'ok')
        self.assertIsNone(get_db().execute('PRAGMA foreign_key_check').fetchone())

    def test_forecast_pending_card_purchase_includes_settlement_once(self):
        card=create_account('Forecast card','credit_card',0,self.bank,20)
        self.tx(date=(date.today()+timedelta(days=1)).isoformat(),account_id=card,status='pending',amount=50)
        forecast=cash_forecast(60)
        self.assertEqual(forecast['projected'],forecast['opening']-50)
        self.assertEqual(len([e for e in forecast['events'] if e['type']=='transfer']),1)
        self.assertEqual(next(a for a in forecast['accounts'] if a['id']==card)['scheduled_balance'],0)

    def test_foreign_subscription_keeps_currency_and_saved_conversion(self):
        from unittest.mock import patch
        from money_manager.services.recurring import create_rule, get_rule, generate_due_recurring
        quote=dict(rate='0.90',date=date.today().isoformat(),source='test')
        with patch('money_manager.utils.exchange.exchange_quote',return_value=quote):
            rule=create_rule(dict(name='Dollar subscription',type='expense',amount=20,currency='USD',account_id=self.cash,frequency='monthly',next_due_date=date.today().isoformat(),is_subscription=True))
        self.assertEqual(get_rule(rule)['amount_eur_minor'],1800)
        self.assertEqual(cash_forecast(30)['events'][0]['minor'],1800)
        with patch('money_manager.services.transactions.exchange_quote',return_value=quote):
            generate_due_recurring()
        tx=get_db().execute('SELECT * FROM transactions WHERE recurring_rule_id=?',(rule,)).fetchone()
        self.assertEqual(tx['currency'],'USD');self.assertEqual(tx['amount_eur_minor'],1800)
        self.assertEqual(tx['is_subscription'],1)
        validate_backup(export_bundle())

    def test_review_http_writes_and_recovery(self):
        response=self.client.post('/tools/rules',data=dict(name='Review rule',contains='Review',tags='Project',action='preview'))
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.post('/tools/rules',data=dict(name='Review rule',contains='Review',tags='Project')).status_code,302)
        self.assertEqual(self.client.post('/forecast/',data=dict(name='What if',spending='-300',income='0',investment='200')).status_code,302)
        tx=self.tx(); trash=delete_transaction(tx)
        self.assertIn('Review payment',self.client.get('/tools/recovery').text)
        self.assertEqual(self.client.post(f'/transactions/restore/{trash}').status_code,302)
        self.assertTrue(get_transaction(tx))
        self.assertEqual(self.client.post(f'/accounts/{self.bank}/archive').status_code,302)
        self.assertFalse(next(a for a in list_accounts(False) if a['id']==self.bank)['is_active'])

    def test_reconciled_opening_balance_cannot_bypass_financial_lock(self):
        from money_manager.services.accounts import get_account,update_account
        record_checks(check_payload(preview_balances({str(self.cash):'0'})),[],'Checked')
        account=get_account(self.cash)
        with self.assertRaisesRegex(ValueError,'Reopen'):
            update_account(self.cash,account['name'],account['type'],100,None,None)
        self.assertEqual(get_account(self.cash)['opening_balance_minor'],0)

    def test_malformed_backup_metadata_and_attachment_records_are_rejected(self):
        payload=export_bundle()
        payload['version']=[]
        with self.assertRaises(ValueError):validate_backup(payload)
        payload['version']=3;payload['data']['transaction_attachments']=['invalid']
        with self.assertRaises(ValueError):validate_backup(payload)


if __name__=='__main__': unittest.main()
