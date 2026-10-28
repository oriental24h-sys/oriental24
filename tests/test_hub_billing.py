import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import wraps
from unittest.mock import patch
from flask import Flask, jsonify, request
from hub_billing import (register_hub_billing, preview, generate, scheduled_tick,
                         next_due, amount_cents, TZ)


class HubBillingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=self.tmp.name+'/db.sqlite'
        @contextmanager
        def conn():
            c=sqlite3.connect(self.db);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
            try:
                yield c;c.commit()
            except BaseException:
                c.rollback();raise
            finally:c.close()
        self.conn=conn
        with conn() as c:
            c.executescript('''
            CREATE TABLE users(id INTEGER PRIMARY KEY,role TEXT,active INTEGER);
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);
            CREATE TABLE cities(id INTEGER PRIMARY KEY,name TEXT);
            CREATE TABLE parcels(id INTEGER PRIMARY KEY,tracking TEXT,status TEXT,amount REAL,city_id INTEGER,
                driver_id INTEGER,current_hub_id INTEGER,status_updated_at TEXT,updated_at TEXT,created_at TEXT);
            CREATE TABLE ops_assignments(id INTEGER PRIMARY KEY,parcel_id INTEGER,new_driver_id INTEGER,hub_id INTEGER);
            CREATE TABLE ops_attempts(id INTEGER PRIMARY KEY,parcel_id INTEGER,driver_id INTEGER,outcome TEXT,operational_hub_id INTEGER);
            INSERT INTO users VALUES(1,'admin',1),(2,'hub_manager',1),(3,'hub_manager',1),(4,'livreur',1);
            INSERT INTO ops_hubs VALUES(10,'Hub A',1),(20,'Hub B',1),(30,'Inactive',0);
            INSERT INTO cities VALUES(1,'City');
            INSERT INTO parcels VALUES
                (1,'A','Livré',100,1,4,NULL,'2026-01-01T10:00:00','2026-01-01T10:00:00','2026-01-01T10:00:00'),
                (2,'B','Refusé',200,1,4,10,'2026-01-01T10:00:00','2026-01-01T10:00:00','2026-01-01T10:00:00'),
                (3,'C','Retourné',300,1,5,20,'2026-01-01T10:00:00','2026-01-01T10:00:00','2026-01-01T10:00:00'),
                (4,'Unproven','Livré',100,1,6,10,'2026-01-01T10:00:00','2026-01-01T10:00:00','2026-01-01T10:00:00'),
                (5,'Open','Reporté',100,1,4,10,'2026-01-01T10:00:00','2026-01-01T10:00:00','2026-01-01T10:00:00');
            INSERT INTO ops_assignments VALUES(1,1,4,10),(2,2,4,10),(3,3,5,20),(4,5,4,10);
            ''')
        self.app=Flask(__name__);self.app.config['TESTING']=True
        class Error(Exception):
            def __init__(self,message,status=400):super().__init__(message);self.status=status
        self.app.register_error_handler(Error,lambda e:(jsonify(error=str(e)),e.status))
        def user():
            role=request.headers.get('X-Role','admin')
            return dict(id=1 if role=='admin' else 2,name='Actor',role=role,
                        agent_hub_id=int(request.headers.get('X-Hub',10)))
        def auth(*roles):
            def dec(fn):
                @wraps(fn)
                def wrapped(*a,**kw):
                    if user()['role'] not in roles:raise Error('Forbidden',403)
                    return fn(*a,**kw)
                return wrapped
            return dec
        self.audits=[]
        register_hub_billing(self.app,dict(conn=conn,auth=auth,user=user,APIError=Error,
            now=lambda:'2026-01-02T23:00:00',append_audit_log=lambda c,**d:self.audits.append(d)))
        self.client=self.app.test_client()
        self.cutoff=datetime(2026,1,2,23,0,tzinfo=TZ)

    def tearDown(self):self.tmp.cleanup()
    def terms(self,hid=10,mode='gross',revision=0,**extra):
        return self.client.put(f'/api/hub-billing/terms/{hid}',json=dict(mode=mode,revision=revision,delivered='10',returned='4',refused='3',**extra))
    def issue(self,key='manual:test',at=None,hub_id=None):
        with self.conn() as c:
            c.execute('BEGIN IMMEDIATE');return generate(c,at or self.cutoff,1,key,hub_id=hub_id)

    def city_fixture(self):
        with self.conn() as c:
            c.execute('ALTER TABLE cities ADD COLUMN hub_id INTEGER')
            c.execute('UPDATE cities SET hub_id=10 WHERE id=1')
            c.execute("INSERT INTO cities VALUES(2,'City Two',10),(3,'Foreign City',20)")
            c.execute('UPDATE parcels SET city_id=2 WHERE id=2')
    def city_terms(self,revision=0,**changes):
        payload=dict(mode='gross',revision=revision,cities=[dict(city_id=1,delivered='10',returned='4',refused='3'),dict(city_id=2,delivered='25',returned='8',refused='7')])
        payload.update(changes)
        return self.client.put('/api/hub-billing/terms/10',json=payload)

    def test_city_rates_match_parcel_city_and_snapshot_old_invoices(self):
        self.city_fixture();self.assertEqual(self.city_terms().status_code,200)
        with self.conn() as c:
            d=preview(c,self.cutoff);h=d['hubs'][0]
            self.assertEqual(h['commission_cents'],1700)
            self.assertEqual([l['commission_cents'] for l in h['lines']],[1000,700])
        result=self.issue();sid=result['statement_ids'][0]
        before=self.client.get(f'/api/hub-billing/{sid}').json
        self.assertEqual(self.city_terms(1,mode='net',cities=[dict(city_id=1,delivered='99',returned='88',refused='77'),dict(city_id=2,delivered='66',returned='55',refused='44')]).status_code,200)
        self.assertEqual(self.client.get(f'/api/hub-billing/{sid}').json,before)
        self.assertIn('cities',self.audits[-1]['old_value'])

    def test_five_assigned_cities_all_require_their_own_rates(self):
        self.city_fixture()
        with self.conn() as c:
            c.execute("INSERT INTO cities VALUES(4,'Four',10),(5,'Five',10),(6,'Six',10)")
        cities=[dict(city_id=cid,delivered=str(cid),returned='0',refused='0') for cid in (1,2,4,5,6)]
        self.assertEqual(self.city_terms(cities=cities).status_code,200)
        h=next(h for h in self.client.get('/api/hub-billing').json['hubs'] if h['id']==10)
        self.assertEqual(len(h['cities']),5)
        self.assertTrue(h['city_mode'])
        self.assertEqual({c['id']:c['delivered_cents'] for c in h['cities']},{cid:cid*100 for cid in (1,2,4,5,6)})

    def test_new_city_without_rate_is_skipped_with_explicit_warning(self):
        self.city_fixture();self.city_terms()
        with self.conn() as c:
            c.execute("INSERT INTO cities VALUES(4,'New City',10)")
            c.execute('UPDATE parcels SET city_id=4 WHERE id=2')
            d=preview(c,self.cutoff)
            self.assertEqual(d['hubs'][0]['parcel_count'],1)
            self.assertEqual(d['missing_city_terms'],[dict(hub_id=10,hub_name='Hub A',city_id=4,city='New City')])
        result=self.issue();self.assertEqual(result['missing_city_terms'][0]['city_id'],4)
        with self.conn() as c:self.assertFalse(c.execute('SELECT 1 FROM hub_billing_lines WHERE parcel_id=2').fetchone())

    def test_city_validation_no_partial_or_foreign_or_duplicate_city_save(self):
        self.city_fixture()
        valid=[dict(city_id=1,delivered='10',returned='0',refused='0'),dict(city_id=2,delivered='20',returned='0',refused='0')]
        for cities in (valid[:1],valid+[dict(valid[0],city_id=3)]):
            self.assertEqual(self.city_terms(cities=cities).status_code,409)
        for cities in ([],None,valid+[valid[0]], [dict(valid[0],city_id=True),valid[1]], [dict(valid[0],delivered='-1'),valid[1]], [dict(valid[0],delivered=None),valid[1]]):
            self.assertEqual(self.city_terms(cities=cities).status_code,400)
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM hub_billing_city_terms').fetchone()[0],0)

    def test_city_mode_cannot_silently_revert_to_general_and_stale_revision_rejected(self):
        self.city_fixture();self.city_terms()
        self.assertEqual(self.terms(revision=1).status_code,409)
        self.assertEqual(self.city_terms().status_code,409)
        self.assertEqual(self.city_terms(1).status_code,200)

    def test_city_tariffs_do_not_infer_operational_hub_from_city(self):
        self.city_fixture();self.city_terms()
        with self.conn() as c:
            d=preview(c,self.cutoff)
            self.assertEqual(d['unassigned_count'],1)
            self.assertNotIn(4,[l['parcel_id'] for h in d['hubs'] for l in h['lines']])

    def test_legacy_general_rates_still_apply_until_explicit_city_configuration(self):
        self.city_fixture();self.terms()
        with self.conn() as c:self.assertEqual(preview(c,self.cutoff)['hubs'][0]['commission_cents'],1300)
        self.assertEqual(self.city_terms(1).status_code,200)
        with self.conn() as c:self.assertEqual(preview(c,self.cutoff)['hubs'][0]['commission_cents'],1700)

    def test_changed_city_mapping_rejects_stale_complete_form(self):
        self.city_fixture()
        with self.conn() as c:c.execute('UPDATE cities SET hub_id=20 WHERE id=2')
        self.assertEqual(self.city_terms().status_code,409)

    def test_city_rates_net_mode_and_zero_prices(self):
        self.city_fixture()
        self.assertEqual(self.city_terms(mode='net',cities=[dict(city_id=1,delivered='0',returned='0',refused='0'),dict(city_id=2,delivered='25',returned='8',refused='7')]).status_code,200)
        with self.conn() as c:
            h=preview(c,self.cutoff)['hubs'][0]
            self.assertEqual((h['commission_cents'],h['retained_cents'],h['cash_due_cents']),(700,700,9300))

    def test_manual_preview_and_generation_can_target_one_hub_only(self):
        self.terms(10);self.terms(20)
        with self.conn() as c:
            d=preview(c,self.cutoff,hub_id=10)
            self.assertEqual([h['hub_id'] for h in d['hubs']],[10])
            self.assertEqual(d['unassigned_count'],0)
        result=self.issue('manual:hub-a',hub_id=10)
        self.assertEqual(result['count'],1)
        with self.conn() as c:
            rows=c.execute('SELECT hub_id FROM hub_billing_statements ORDER BY id').fetchall()
            self.assertEqual([r['hub_id'] for r in rows],[10])
            self.assertEqual([r[0] for r in c.execute('SELECT parcel_id FROM hub_billing_lines ORDER BY parcel_id')],[1,2])
            other=preview(c,self.cutoff,hub_id=20)
            self.assertEqual([h['hub_id'] for h in other['hubs']],[20])
        second=self.issue('manual:hub-b',hub_id=20)
        self.assertEqual(second['count'],1)
        with self.conn() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT hub_id FROM hub_billing_statements ORDER BY id')],[10,20])

    def test_manual_api_requires_active_hub_and_keeps_all_hubs_scope(self):
        self.terms(10);self.terms(20)
        all_preview=self.client.get('/api/hub-billing/preview')
        one_preview=self.client.get('/api/hub-billing/preview?hub_id=10')
        self.assertEqual(all_preview.status_code,200);self.assertEqual(len(all_preview.json['hubs']),2)
        self.assertEqual(one_preview.status_code,200);self.assertEqual([h['hub_id'] for h in one_preview.json['hubs']],[10])
        self.assertEqual(self.client.get('/api/hub-billing/preview?hub_id=30').status_code,404)
        self.assertEqual(self.client.get('/api/hub-billing/preview?hub_id=abc').status_code,400)
        payload=dict(cutoff=one_preview.json['cutoff'],snapshot=one_preview.json['snapshot'],request_key='hub-only-request-123456',confirmed=True,hub_id=10)
        result=self.client.post('/api/hub-billing/generate',json=payload)
        self.assertEqual(result.status_code,200);self.assertEqual(result.json['count'],1)
        with self.conn() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT hub_id FROM hub_billing_statements')],[10])
        bad={**payload,'request_key':'hub-bad-request-123456','hub_id':30}
        self.assertEqual(self.client.post('/api/hub-billing/generate',json=bad).status_code,404)
        invalid={**payload,'request_key':'hub-invalid-request-123456','hub_id':True}
        self.assertEqual(self.client.post('/api/hub-billing/generate',json=invalid).status_code,400)

    def test_rates_and_outcomes_and_no_destination_inference(self):
        self.assertEqual(self.terms().status_code,200);self.assertEqual(self.terms(20).status_code,200)
        with self.conn() as c:d=preview(c,self.cutoff)
        self.assertEqual(len(d['hubs']),2);self.assertEqual(d['unassigned_count'],1)
        a=next(h for h in d['hubs'] if h['hub_id']==10)
        self.assertEqual((a['parcel_count'],a['cod_cents'],a['commission_cents']),(2,10000,1300))
        self.assertEqual(a['cash_due_cents'],10000);self.assertEqual(a['commission_due_cents'],1300)
        self.assertEqual(self.issue()['count'],2)
        self.assertEqual(self.issue('new-run')['count'],0)

    def payment(self,sid=1,key=None,**changes):
        import uuid
        payload=dict(amount_cents=10000,method='Espèces',reference='RECU-TEST',paid_on='2026-01-03',request_key=key or uuid.uuid4().hex,confirmed=True)
        payload.update(changes)
        return self.client.post(f'/api/hub-billing/{sid}/paid',json=payload)

    def test_full_receipt_paid_visible_to_manager_and_pdf_csv(self):
        from pypdf import PdfReader
        from io import BytesIO
        self.terms();self.issue()
        r=self.payment();self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['invoice']['state'],'Paid')
        self.assertEqual(r.json['invoice']['cash_remaining_cents'],0)
        # Gross-method commission stays payable and is never fabricated as paid.
        self.assertEqual(r.json['invoice']['commission_due_cents'],1300)
        headers={'X-Role':'hub_manager','X-Hub':'10'}
        detail=self.client.get('/api/hub-billing/1',headers=headers).json
        self.assertEqual(detail['invoice']['state'],'Paid')
        self.assertEqual(detail['receipt']['amount_cents'],10000)
        self.assertNotIn('payload_hash',detail['receipt'])
        self.assertEqual(self.client.get('/api/hub-billing',headers=headers).json['rows'][0]['state'],'Paid')
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(self.client.get('/api/hub-billing/1/pdf',headers=headers).data)).pages)
        self.assertIn('Paid',text);self.assertIn('RECU-TEST',text)
        self.assertIn('Paid',self.client.get('/api/hub-billing/1/csv',headers=headers).data.decode())
        self.assertEqual(self.audits[-1]['action'],'hub_invoice_paid')

    def test_reject_partial_overpaid_unconfirmed_and_bad_dates(self):
        self.terms();self.issue()
        for changes in [dict(amount_cents=9999),dict(amount_cents=10001),dict(amount_cents=0),dict(amount_cents=True),dict(confirmed=False),dict(paid_on='2999-01-01'),dict(paid_on='2026-02-30'),dict(reference=''),dict(method='bad')]:
            r=self.payment(**changes);self.assertIn(r.status_code,(400,409),r.json)
        with self.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM hub_billing_receipts').fetchone()[0],0)
        self.assertEqual(self.client.get('/api/hub-billing/1').json['invoice']['state'],'Not Paid')

    def test_receipt_replay_is_idempotent_and_new_or_altered_duplicate_rejected(self):
        key='receipt'+'a'*25;self.terms();self.issue()
        self.assertEqual(self.payment(key=key).status_code,200)
        r=self.payment(key=key);self.assertEqual(r.status_code,200);self.assertTrue(r.json['already_recorded'])
        self.assertEqual(self.payment(key=key,reference='OTHER').status_code,409)
        self.assertEqual(self.payment().status_code,409)
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM hub_billing_receipts').fetchone()[0],1)
            with self.assertRaises(sqlite3.IntegrityError):c.execute('UPDATE hub_billing_receipts SET amount_cents=1')
            with self.assertRaises(sqlite3.IntegrityError):c.execute('DELETE FROM hub_billing_receipts')

    def test_receipt_admin_only_manager_cannot_mark_own_or_foreign(self):
        self.terms();self.issue()
        for role,hid in [('hub_manager',10),('hub_manager',20),('livreur',10)]:
            r=self.client.post('/api/hub-billing/1/paid',json={},headers={'X-Role':role,'X-Hub':str(hid)})
            self.assertEqual(r.status_code,403)
        with self.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM hub_billing_receipts').fetchone()[0],0)

    def test_parallel_full_receipts_only_one_succeeds(self):
        from concurrent.futures import ThreadPoolExecutor
        import uuid
        self.terms();self.issue()
        def submit(_):
            with self.app.test_client() as client:
                return client.post('/api/hub-billing/1/paid',json=dict(amount_cents=10000,method='Espèces',reference='Concurrent',paid_on='2026-01-03',request_key=uuid.uuid4().hex,confirmed=True)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(submit,range(2)))
        self.assertEqual(sorted(statuses),[200,409])
        with self.conn() as c:self.assertEqual(c.execute('SELECT sum(amount_cents) FROM hub_billing_receipts').fetchone()[0],10000)

    def test_net_full_receipt_is_exact_net_not_gross_and_snapshots_unchanged(self):
        self.terms(mode='net');self.issue()
        with self.conn() as c:
            before=[tuple(r) for r in c.execute('SELECT * FROM hub_billing_statements')]
        self.assertEqual(self.payment().status_code,409)
        r=self.payment(amount_cents=8700);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['invoice']['state'],'Paid')
        with self.conn() as c:self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM hub_billing_statements')],before)

    def test_zero_cash_due_has_no_fake_receipt(self):
        self.client.put('/api/hub-billing/terms/10',json=dict(mode='net',revision=0,delivered='1000',returned='100',refused='100'))
        self.issue()
        self.assertEqual(self.client.get('/api/hub-billing/1').json['invoice']['state'],'Solde nul')
        self.assertIn(self.payment(amount_cents=1).status_code,(400,409))

    def test_hub_pdf_shared_layout_scope_and_frozen_identity(self):
        from pypdf import PdfReader
        from io import BytesIO
        self.terms();self.terms(20);self.issue()
        r=self.client.get('/api/hub-billing/1/pdf',headers={'X-Role':'hub_manager','X-Hub':'10'})
        self.assertEqual(r.status_code,200)
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(r.data)).pages)
        for expected in ['Facture','Hub A','Total COD livré','Total Net','ID de suivi','Page :']:
            self.assertIn(expected,text)
        self.assertNotIn('Olivraison',text)
        with self.conn() as c:c.execute("UPDATE ops_hubs SET name='Changed' WHERE id=10")
        r=self.client.get('/api/hub-billing/1/pdf')
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(r.data)).pages)
        self.assertIn('Hub A',text);self.assertNotIn('Changed',text)
        self.assertEqual(self.client.get('/api/hub-billing/1/pdf',headers={'X-Role':'hub_manager','X-Hub':'20'}).status_code,404)
        self.assertEqual(self.client.get('/api/hub-billing/1/pdf',headers={'X-Role':'livreur'}).status_code,403)

    def test_net_calculation_and_missing_terms(self):
        self.terms(mode='net')
        with self.conn() as c:d=preview(c,self.cutoff)
        self.assertEqual([h['id'] for h in d['missing_terms']],[20])
        g=d['hubs'][0];self.assertEqual((g['retained_cents'],g['cash_due_cents'],g['commission_due_cents']),(1300,8700,0))

    def test_manager_scope_read_detail_and_csv_and_admin_only_controls(self):
        self.terms();self.terms(20);self.issue()
        headers={'X-Role':'hub_manager','X-Hub':'10'}
        r=self.client.get('/api/hub-billing',headers=headers)
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json['rows']),1)
        self.assertNotIn('hubs',r.json);self.assertNotIn('schedule',r.json)
        sid=r.json['rows'][0]['id']
        self.assertEqual(self.client.get(f'/api/hub-billing/{sid}',headers=headers).status_code,200)
        self.assertEqual(self.client.get(f'/api/hub-billing/{sid}/csv',headers=headers).status_code,200)
        with self.conn() as c:foreign=c.execute('SELECT id FROM hub_billing_statements WHERE hub_id=20').fetchone()[0]
        self.assertEqual(self.client.get(f'/api/hub-billing/{foreign}',headers=headers).status_code,404)
        self.assertEqual(self.client.get(f'/api/hub-billing/{foreign}/csv',headers=headers).status_code,404)
        self.assertEqual(self.client.get('/api/hub-billing/preview',headers=headers).status_code,403)
        self.assertEqual(self.client.put('/api/hub-billing/terms/10',json={},headers=headers).status_code,403)
        self.assertEqual(self.client.put('/api/hub-billing/schedule',json={},headers=headers).status_code,403)
        self.assertEqual(self.client.post('/api/hub-billing/generate',json={},headers=headers).status_code,403)
        self.assertEqual(self.client.get('/api/hub-billing',headers={'X-Role':'livreur'}).status_code,403)

    def test_terms_snapshot_and_hub_name_never_recomputed(self):
        self.terms();self.issue()
        first=self.client.get('/api/hub-billing/1').json
        r=self.client.put('/api/hub-billing/terms/10',json=dict(mode='net',revision=1,delivered='100',returned='30',refused='20'))
        self.assertEqual(r.status_code,200)
        with self.conn() as c:c.execute("UPDATE ops_hubs SET name='Renamed' WHERE id=10")
        self.assertEqual(self.client.get('/api/hub-billing/1').json,first)
        with self.conn() as c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute('UPDATE hub_billing_statements SET cod_cents=0')

    def test_manual_preview_stale_rates_rejected_and_replay_safe(self):
        self.terms()
        d=self.client.get('/api/hub-billing/preview').json
        payload=dict(cutoff=d['cutoff'],snapshot=d['snapshot'],confirmed=True,request_key='a'*24)
        self.assertEqual(self.client.post('/api/hub-billing/generate',json=payload).status_code,200)
        r=self.client.post('/api/hub-billing/generate',json=payload)
        self.assertEqual(r.status_code,200);self.assertTrue(r.json['replayed'])
        self.assertEqual(r.json['count'],1)
        self.assertEqual(self.client.post('/api/hub-billing/generate',json={**payload,'snapshot':'bad'}).status_code,409)
        fresh=self.client.get('/api/hub-billing/preview').json
        self.client.put('/api/hub-billing/terms/10',json=dict(mode='gross',revision=1,delivered='30',returned='4',refused='3'))
        stale=dict(cutoff=fresh['cutoff'],snapshot=fresh['snapshot'],confirmed=True,request_key='b'*24)
        # No remaining configured invoices -> changing rates still does not create duplicate invoices.
        r=self.client.post('/api/hub-billing/generate',json=stale);self.assertEqual(r.status_code,200)
        self.assertEqual(r.json['count'],0)

    def test_preview_rejects_rate_change_before_first_issue(self):
        self.terms()
        d=self.client.get('/api/hub-billing/preview').json
        self.client.put('/api/hub-billing/terms/10',json=dict(mode='gross',revision=1,delivered='30',returned='4',refused='3'))
        r=self.client.post('/api/hub-billing/generate',json=dict(cutoff=d['cutoff'],snapshot=d['snapshot'],confirmed=True,request_key='c'*24))
        self.assertEqual(r.status_code,409)
        with self.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM hub_billing_runs').fetchone()[0],0)

    def test_replay_same_key_different_payload_rejected(self):
        self.terms();self.issue()
        with self.assertRaises(ValueError):self.issue(at=self.cutoff+timedelta(hours=1))

    def test_schedule_respects_time_disabled_no_duplicates_and_catchup(self):
        self.terms()
        at=datetime(2026,1,2,20,0,tzinfo=TZ)
        with patch('hub_billing.local_now',return_value=at):
            r=self.client.put('/api/hub-billing/schedule',json=dict(enabled=True,time='23:15',revision=0))
        self.assertEqual(r.status_code,200)
        due=datetime.fromisoformat(r.json['next_run'])
        self.assertEqual((due.hour,due.minute),(23,15))
        self.assertIsNone(scheduled_tick(self.conn,due-timedelta(seconds=1)))
        first=scheduled_tick(self.conn,due+timedelta(minutes=5));self.assertEqual(first['count'],1)
        self.assertIsNone(scheduled_tick(self.conn,due+timedelta(minutes=5)))
        # A missed time is processed later without requiring a browser request.
        self.assertEqual(scheduled_tick(self.conn,due+timedelta(days=2))['count'],0)
        with self.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM hub_billing_statements').fetchone()[0],1)
        self.client.put('/api/hub-billing/schedule',json=dict(enabled=False,time='12:00',revision=1))
        self.assertIsNone(scheduled_tick(self.conn,due+timedelta(days=10)))

    def test_parallel_scheduler_ticks_create_one_daily_run(self):
        from concurrent.futures import ThreadPoolExecutor
        self.terms()
        at=datetime(2026,1,2,20,0,tzinfo=TZ)
        with patch('hub_billing.local_now',return_value=at):
            self.client.put('/api/hub-billing/schedule',json=dict(enabled=True,time='23:15',revision=0))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:scheduled_tick(self.conn,at+timedelta(hours=4)),range(2)))
        self.assertEqual(sum(r is not None for r in results),1)
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM hub_billing_runs').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM hub_billing_statements').fetchone()[0],1)

    def test_disabled_configuring_admin_blocks_schedule(self):
        self.terms()
        at=datetime(2026,1,2,20,0,tzinfo=TZ)
        with patch('hub_billing.local_now',return_value=at):
            self.client.put('/api/hub-billing/schedule',json=dict(enabled=True,time='23:15',revision=0))
        with self.conn() as c:c.execute('UPDATE users SET active=0 WHERE id=1')
        self.assertIsNone(scheduled_tick(self.conn,at+timedelta(hours=4)))
        with self.conn() as c:
            self.assertIn('inactif',c.execute('SELECT last_error FROM hub_billing_schedule').fetchone()[0])
            self.assertEqual(c.execute('SELECT count(*) FROM hub_billing_runs').fetchone()[0],0)

    def test_cutoff_compares_against_application_server_timestamps(self):
        self.terms()
        before=(self.cutoff-timedelta(seconds=1)).astimezone().replace(tzinfo=None).isoformat()
        after=(self.cutoff+timedelta(seconds=1)).astimezone().replace(tzinfo=None).isoformat()
        with self.conn() as c:
            c.execute("UPDATE parcels SET status='Créé'")
            c.execute("UPDATE parcels SET status='Livré',status_updated_at=? WHERE id=1",(before,))
            c.execute("UPDATE parcels SET status='Refusé',status_updated_at=? WHERE id=2",(after,))
            d=preview(c,self.cutoff)
        self.assertEqual([l['parcel_id'] for l in d['hubs'][0]['lines']],[1])

    def test_schedule_timezone_validation_and_stale_revision(self):
        self.assertEqual(next_due('00:05',datetime(2026,1,2,23,0,tzinfo=TZ)).day,3)
        self.assertEqual(self.client.put('/api/hub-billing/schedule',json=dict(enabled=True,time='25:00',revision=0)).status_code,400)
        self.assertEqual(self.client.put('/api/hub-billing/schedule',json=dict(enabled=True,time='23:00',revision=9)).status_code,409)
        self.assertEqual(self.client.put('/api/hub-billing/schedule',json=dict(enabled='true',time='23:00',revision=0)).status_code,400)

    def test_bad_rates_rejected_and_version_guard(self):
        for val in ('-1','NaN','10001','0.001',True):
            r=self.client.put('/api/hub-billing/terms/10',json=dict(mode='gross',revision=0,delivered=val,returned=0,refused=0))
            self.assertEqual(r.status_code,400,r.json)
        self.assertEqual(amount_cents('0'),0);self.terms()
        self.assertEqual(self.terms().status_code,409)
        self.assertEqual(self.terms(30).status_code,404)

    def test_atomic_rollback_on_last_statement_line_failure(self):
        self.terms();self.terms(20)
        with self.conn() as c:c.execute("CREATE TRIGGER fail_last BEFORE INSERT ON hub_billing_lines WHEN NEW.parcel_id=3 BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.issue()
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM hub_billing_runs').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM hub_billing_statements').fetchone()[0],0)

    def test_closing_attempt_snapshot_beats_current_assignment_and_location(self):
        self.terms();self.terms(20)
        with self.conn() as c:
            c.execute("INSERT INTO ops_attempts VALUES(1,1,4,'Livré',20)")
            d=preview(c,self.cutoff)
        g=next(h for h in d['hubs'] if h['hub_id']==20)
        self.assertIn(1,[l['parcel_id'] for l in g['lines']])


if __name__=='__main__':unittest.main()
