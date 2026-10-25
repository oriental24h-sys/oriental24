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
            INSERT INTO users VALUES(1,'admin',1),(2,'agent',1),(3,'agent',1),(4,'livreur',1);
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
    def issue(self,key='manual:test',at=None):
        with self.conn() as c:
            c.execute('BEGIN IMMEDIATE');return generate(c,at or self.cutoff,1,key)

    def test_rates_and_outcomes_and_no_destination_inference(self):
        self.assertEqual(self.terms().status_code,200);self.assertEqual(self.terms(20).status_code,200)
        with self.conn() as c:d=preview(c,self.cutoff)
        self.assertEqual(len(d['hubs']),2);self.assertEqual(d['unassigned_count'],1)
        a=next(h for h in d['hubs'] if h['hub_id']==10)
        self.assertEqual((a['parcel_count'],a['cod_cents'],a['commission_cents']),(2,10000,1300))
        self.assertEqual(a['cash_due_cents'],10000);self.assertEqual(a['commission_due_cents'],1300)
        self.assertEqual(self.issue()['count'],2)
        self.assertEqual(self.issue('new-run')['count'],0)

    def test_hub_pdf_shared_layout_scope_and_frozen_identity(self):
        from pypdf import PdfReader
        from io import BytesIO
        self.terms();self.terms(20);self.issue()
        r=self.client.get('/api/hub-billing/1/pdf',headers={'X-Role':'agent','X-Hub':'10'})
        self.assertEqual(r.status_code,200)
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(r.data)).pages)
        for expected in ['Facture','Hub A','Total COD livré','Total Net','ID de suivi','Page :']:
            self.assertIn(expected,text)
        self.assertNotIn('Olivraison',text)
        with self.conn() as c:c.execute("UPDATE ops_hubs SET name='Changed' WHERE id=10")
        r=self.client.get('/api/hub-billing/1/pdf')
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(r.data)).pages)
        self.assertIn('Hub A',text);self.assertNotIn('Changed',text)
        self.assertEqual(self.client.get('/api/hub-billing/1/pdf',headers={'X-Role':'agent','X-Hub':'20'}).status_code,404)
        self.assertEqual(self.client.get('/api/hub-billing/1/pdf',headers={'X-Role':'livreur'}).status_code,403)

    def test_net_calculation_and_missing_terms(self):
        self.terms(mode='net')
        with self.conn() as c:d=preview(c,self.cutoff)
        self.assertEqual([h['id'] for h in d['missing_terms']],[20])
        g=d['hubs'][0];self.assertEqual((g['retained_cents'],g['cash_due_cents'],g['commission_due_cents']),(1300,8700,0))

    def test_manager_scope_read_detail_and_csv_and_admin_only_controls(self):
        self.terms();self.terms(20);self.issue()
        headers={'X-Role':'agent','X-Hub':'10'}
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
