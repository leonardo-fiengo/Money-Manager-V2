import base64
import copy
import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from werkzeug.datastructures import FileStorage
from money_manager import create_app
from money_manager.db.connection import get_db
from money_manager.services.accounts import create_account, account_balances
from money_manager.services.backup import export_bundle, validate_backup, restore_backup
from money_manager.services.contacts import save_contact, set_contact_active, get_contact
from money_manager.services.loans import create_loan, get_loan, list_loans, add_payment
from money_manager.services.profile import save_profile, local_profile, profile_photo
from money_manager.services.taxes import calculate_irpef, save_estimate, save_tax, record_payment, get_tax, tax_years
from money_manager.services.transactions import create_transaction, update_transaction, get_transaction, list_transactions, delete_transaction, restore_transaction
from money_manager.services.inbox import money_inbox


class PeopleTaxesTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name)
        self.app=create_app(type('Config',(),dict(DATA_DIR=root,DATABASE=root/'test.sqlite3',MERCHANT_LOGO_DIR=root/'logos',SECRET_KEY='test',TESTING=True)))
        self.ctx=self.app.app_context(); self.ctx.push(); self.client=self.app.test_client()
        self.bank=create_account('Everyday','bank',1000)
        self.contact=save_contact(dict(name='Alex Example',email='alex@example.test',phone='+39 123',notes='Friend'))
        self.today=date.today().isoformat()

    def tearDown(self):
        self.ctx.pop(); self.temp.cleanup()

    def payment(self,**changes):
        data=dict(type='expense',amount=25,date=self.today,account_id=self.bank,contact_id=self.contact)
        data.update(changes)
        return create_transaction(data)

    def debt(self,**changes):
        data=dict(direction='borrowed',principal_amount=100,expected_total_amount=120,start_date=self.today,contact_id=self.contact,kind='debt')
        data.update(changes)
        return create_loan(data)

    def tax(self,**changes):
        data=dict(name='IRPEF balance',amount='100.05',tax_year=date.today().year,due_date=self.today)
        data.update(changes)
        return save_tax(data)

    def test_contact_payments_search_edit_recovery_and_archive_preserve_ledger(self):
        transaction=self.payment()
        self.assertEqual(list_transactions({'search':'Alex Example'})[0]['id'],transaction)
        self.assertEqual(list_transactions({'contact_id':self.contact})[0]['contact_name'],'Alex Example')
        data=dict(get_transaction(transaction)); data.pop('contact_id'); data['description']='Dinner'
        update_transaction(transaction,data)
        self.assertEqual(get_transaction(transaction)['contact_id'],self.contact)
        trash=delete_transaction(transaction); restore_transaction(trash)
        set_contact_active(self.contact,False)
        self.assertEqual(list_transactions({'contact_id':self.contact})[0]['amount_minor'],2500)
        self.assertEqual(next(a for a in account_balances() if a['id']==self.bank)['balance'],975)
        self.assertIn('Alex Example (archived)',self.client.get(f'/transactions/{transaction}/edit').text)
        self.assertIn('Alex Example',self.client.get('/transactions/').text)

    def test_merchant_and_contact_cannot_both_be_selected(self):
        merchant=get_db().execute('SELECT id FROM merchants LIMIT 1').fetchone()
        if not merchant: merchant=dict(id=get_db().execute("INSERT INTO merchants(name) VALUES('Store')").lastrowid);get_db().commit()
        with self.assertRaises(ValueError): self.payment(merchant_id=merchant['id'])
        with self.assertRaises(ValueError): self.payment(contact_id=99999)
        self.assertEqual(get_db().execute('SELECT COUNT(*) AS n FROM transactions').fetchone()['n'],0)

    def test_contact_payment_form_and_route(self):
        page=self.client.get(f'/transactions/new?contact_id={self.contact}')
        self.assertIn(f'value="{self.contact}" selected',page.text)
        response=self.client.post('/transactions/new',data=dict(type='income',date=self.today,amount='15',account_id=self.bank,payee_kind='contact',contact_id=self.contact))
        self.assertEqual(response.status_code,302)
        row=get_db().execute('SELECT * FROM transactions ORDER BY id DESC LIMIT 1').fetchone()
        self.assertEqual(row['contact_id'],self.contact)
        self.assertIsNone(row['merchant_id'])

    def test_debts_and_loans_share_records_without_duplicate_totals(self):
        debt=self.debt(); loan=self.debt(kind='loan',direction='lent_out',principal_amount=50,expected_total_amount=50)
        self.assertEqual(len(list_loans()),2);self.assertEqual(len(list_loans(kind='loan')),1)
        self.assertEqual(get_loan(debt)['counterparty'],'Alex Example')
        add_payment(debt,dict(date=self.today,amount=20))
        self.assertEqual(get_loan(debt)['outstanding_amount'],100)
        with self.assertRaises(ValueError): add_payment(debt,dict(date=self.today,amount=101))
        with self.assertRaises(ValueError): add_payment(loan,dict(date=(date.today()+timedelta(days=1)).isoformat(),amount=5))
        add_payment(debt,dict(date=self.today,amount=100))
        self.assertEqual(get_loan(debt)['status'],'closed')
        self.assertIn('Someone owes me',self.client.get('/loans/new').text)
        self.assertEqual(self.client.get('/loans/999999').status_code,404)
        self.assertEqual(next(a for a in account_balances() if a['id']==self.bank)['balance'],1000)

    def test_tax_partial_payment_limits_edit_and_archive(self):
        tax=self.tax(tax_year=date.today().year-1)
        record_payment(tax,dict(amount='30.02',date=self.today))
        self.assertEqual(get_tax(tax)['remaining'],70.03)
        with self.assertRaises(ValueError): record_payment(tax,dict(amount='70.04',date=self.today))
        with self.assertRaises(ValueError): save_tax(dict(name='Change',amount=20,tax_year=2026,due_date=self.today),tax)
        record_payment(tax,dict(amount='70.03',date=self.today))
        self.assertEqual(get_tax(tax)['remaining'],0)
        self.assertIn(date.today().year-1,tax_years())
        page=self.client.get(f'/taxes/?year={date.today().year-1}')
        self.assertIn('Year archive',page.text);self.assertIn('IRPEF balance',page.text)
        self.client.post(f'/taxes/{tax}/delete')
        self.assertIsNotNone(get_tax(tax))
        self.assertEqual(next(a for a in account_balances() if a['id']==self.bank)['balance'],1000)

    def test_tax_deadlines_reach_money_inbox_and_paid_records_leave_it(self):
        tax=self.tax(due_date=(date.today()-timedelta(days=1)).isoformat())
        self.assertTrue(any(i['href']=='taxes.detail' for i in money_inbox()))
        record_payment(tax,dict(amount='100.05',date=self.today))
        self.assertFalse(any(i['href']=='taxes.detail' for i in money_inbox()))

    def test_irpef_progressive_boundaries_old_rates_and_inputs(self):
        for income,expected in [(0,0),(28000,6440),(50000,13700),(60000,18000),(28000.01,6440)]:
            self.assertEqual(calculate_irpef(dict(tax_year=2026,income=income))[1]['gross'],expected)
        self.assertEqual(calculate_irpef(dict(tax_year=2025,income=50000))[1]['gross'],14140)
        inputs,result=calculate_irpef(dict(tax_year=2026,income=40000,deductions=2000,credits=1000,local_tax=500,withheld=10000))
        self.assertEqual(result['taxable'],38000); self.assertEqual(result['balance'],-760)
        for invalid in [dict(tax_year=2027,income=10000),dict(tax_year=2026,income=-1),dict(tax_year=2026,income=10,deductions=11),dict(tax_year=2026,income='NaN')]:
            with self.assertRaises(ValueError): calculate_irpef(invalid)

    def test_saved_estimate_is_frozen_and_tax_year_archive_keeps_it(self):
        estimate=save_estimate(dict(tax_year=2025,income=50000))
        row=get_db().execute('SELECT * FROM tax_estimates WHERE id=?',(estimate,)).fetchone()
        self.assertEqual(json.loads(row['result_json'])['gross'],14140)
        self.assertIn('2025',self.client.get(f'/taxes/estimates/{estimate}').text)
        self.assertIn('2025',self.client.get('/taxes/').text)
        self.assertEqual(self.client.post('/taxes/calculator',data=dict(tax_year=2026,income='40000',action='save')).status_code,302)

    def test_profile_photo_contacts_taxes_and_debts_roundtrip_in_backup(self):
        raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jhCkAAAAASUVORK5CYII=')
        photo=profile_photo(FileStorage(stream=io.BytesIO(raw),filename='avatar.png'))
        save_profile('Me','me@example.test','+39 555',photo)
        self.payment();self.debt();tax=self.tax();record_payment(tax,dict(amount=20,date=self.today));save_estimate(dict(tax_year=2026,income=28000))
        bundle=export_bundle(); validate_backup(bundle)
        save_profile('Changed'); set_contact_active(self.contact,False)
        restore_backup(bundle)
        self.assertEqual(local_profile()['avatar_data'],photo); self.assertEqual(local_profile()['email'],'me@example.test')
        self.assertTrue(get_contact(self.contact)['is_active']);self.assertEqual(get_tax(tax)['paid'],20)
        self.assertEqual(export_bundle()['data'],bundle['data'])
        with self.assertRaises(ValueError): profile_photo(FileStorage(stream=io.BytesIO(b'<svg></svg>'),filename='avatar.svg'))
        old=copy.deepcopy(bundle);old['schema_version']=13
        for table in ('contacts','taxes','tax_payments','tax_estimates'): old['data'].pop(table)
        for row in old['data']['transactions']: row.pop('contact_id')
        for row in old['data']['loans']: row.pop('contact_id');row.pop('kind')
        for row in old['data']['local_profile']:
            for column in ('email','phone','avatar_data'): row.pop(column)
        validate_backup(old)

    def test_profile_multipart_upload_rejection_and_removal(self):
        raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jhCkAAAAASUVORK5CYII=')
        response=self.client.post('/profile/',data=dict(display_name='Photo test',email='me@example.test',phone='+39 000',photo=(io.BytesIO(raw),'avatar.png')),content_type='multipart/form-data')
        self.assertEqual(response.status_code,302)
        photo=local_profile()['avatar_data']
        self.assertIn('alt="Your profile photo"',self.client.get('/profile/').text)
        self.assertIn(photo,self.client.get('/').text)
        self.assertEqual(self.client.post('/profile/',data=dict(display_name='Bad photo',photo=(io.BytesIO(b'<svg>bad</svg>'),'avatar.svg')),content_type='multipart/form-data').status_code,400)
        self.assertEqual(local_profile()['avatar_data'],photo)
        self.assertEqual(local_profile()['display_name'],'Photo test')
        self.client.post('/profile/',data=dict(display_name='Photo test',remove_photo='1'))
        self.assertIsNone(local_profile()['avatar_data'])

    def test_navigation_separate_settings_and_csrf(self):
        for path in ['/settings/','/settings/appearance','/settings/payments','/settings/organization','/settings/review','/settings/data','/debts/','/loans/','/taxes/','/taxes/calculator','/taxes/new','/profile/contacts/','/profile/contacts/new','/profile/']:
            with self.subTest(path=path): self.assertEqual(self.client.get(path).status_code,200)
        self.assertNotIn('Tools &amp; settings',self.client.get('/').text)
        self.assertIn('aria-label="Money inbox"',self.client.get('/').text)
        self.assertNotIn('id="payments-title"',self.client.get('/settings/appearance').text)
        self.assertIn('id="payments-title"',self.client.get('/settings/payments').text)
        self.assertEqual(self.client.get('/settings/nope').status_code,404)
        self.app.config['CSRF_ENABLED']=True
        for path in ['/profile/contacts/new','/taxes/new','/taxes/calculator','/loans/new','/settings/payments']:
            self.assertEqual(self.client.post(path,data={}).status_code,400)
