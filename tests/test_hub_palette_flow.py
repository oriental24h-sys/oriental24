import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime
from functools import wraps

from flask import Flask, g, jsonify, request

from logistics import register_logistics


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class HubPaletteFlowTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.sqlite')
        os.close(fd)
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True

        @contextmanager
        def conn():
            db = sqlite3.connect(self.db_path)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        def auth(*roles):
            def decorate(fn):
                @wraps(fn)
                def wrapped(*args, **kwargs):
                    actor = getattr(g, 'actor', None)
                    if not actor or (roles and actor['role'] not in roles):
                        raise APIError('Forbidden', 403)
                    return fn(*args, **kwargs)
                return wrapped
            return decorate

        @self.app.before_request
        def set_actor():
            hub = request.headers.get('X-Hub')
            g.actor = {
                'id': int(request.headers.get('X-Actor', '1')),
                'name': request.headers.get('X-Name', 'Test actor'),
                'role': request.headers.get('X-Role', 'admin'),
                'agent_hub_id': int(hub) if hub else None,
            }

        @self.app.errorhandler(APIError)
        def api_error(exc):
            return jsonify(error=str(exc)), exc.status

        def now():
            return datetime.now().isoformat(timespec='seconds')

        def text(data, key, required=True, maxlen=255):
            value = data.get(key, '')
            if not isinstance(value, str) or len(value.strip()) > maxlen or (required and not value.strip()):
                raise APIError('Champ invalide : ' + key)
            return value.strip()

        def parcel(db, parcel_id, actor):
            row = db.execute('SELECT * FROM parcels WHERE id=?', (parcel_id,)).fetchone()
            if not row:
                raise APIError('Colis introuvable.', 404)
            if actor['role'] == 'hub_manager' and row['current_hub_id'] != actor.get('agent_hub_id'):
                raise APIError('Colis introuvable dans votre Hub.', 404)
            return dict(row)

        def append_audit_log(db, **kwargs):
            # Tests exercise business invariants; production uses the append-only audit service.
            return None

        self.revocations=[]
        def security_revoke_user(db, user_id, reason, actor_id):
            self.revocations.append((user_id,reason,actor_id))

        services = {
            'conn': conn,
            'auth': auth,
            'user': lambda: g.actor,
            'now': now,
            'text': text,
            'APIError': APIError,
            'event': lambda *args, **kwargs: None,
            'parcel': parcel,
            'generate_password_hash': lambda value: 'hash:' + value,
            'append_audit_log': append_audit_log,
        }
        with conn() as c:
            c.executescript('''
                CREATE TABLE cities(
                    id INTEGER PRIMARY KEY,name TEXT NOT NULL,region TEXT,
                    delivery INTEGER NOT NULL DEFAULT 1,pickup INTEGER NOT NULL DEFAULT 1,
                    hub_id INTEGER
                );
                CREATE TABLE users(
                    id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL DEFAULT '',role TEXT NOT NULL,company TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00',client_type TEXT NOT NULL DEFAULT 'vendeur',
                    agent_hub_id INTEGER,driver_hub_id INTEGER,team_lead_id INTEGER,driver_city_id INTEGER,
                    driver_address TEXT NOT NULL DEFAULT '',driver_revision INTEGER NOT NULL DEFAULT 1,
                    driver_blocked INTEGER NOT NULL DEFAULT 0,driver_archived INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE parcels(
                    id INTEGER PRIMARY KEY,tracking TEXT NOT NULL UNIQUE,recipient TEXT NOT NULL,
                    phone TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,amount REAL,driver_id INTEGER,
                    client_id INTEGER,city_id INTEGER,note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL,invoice_id INTEGER,
                    current_hub_id INTEGER,origin_hub_id INTEGER,ops_revision INTEGER NOT NULL DEFAULT 0,
                    reason_code TEXT,next_attempt_at TEXT
                );
                CREATE TABLE tickets(id INTEGER PRIMARY KEY,user_id INTEGER,subject TEXT,created_at TEXT);
                CREATE TABLE events(id INTEGER PRIMARY KEY,parcel_id INTEGER,status TEXT,details TEXT,created_at TEXT);
                CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE driver_statement_lines(id INTEGER PRIMARY KEY,parcel_id INTEGER,active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE driver_receipts(parcel_id INTEGER PRIMARY KEY,driver_id INTEGER,received_at TEXT,hub_id INTEGER);
                CREATE TABLE driver_workspace_audit(
                    id INTEGER PRIMARY KEY,driver_id INTEGER NOT NULL,actor_id INTEGER NOT NULL,
                    action TEXT NOT NULL,parcel_id INTEGER,details TEXT NOT NULL,created_at TEXT NOT NULL
                );
                INSERT INTO cities(id,name,region,hub_id) VALUES
                    (1,'Central City','Oriental',90),(2,'Secondary A','Oriental',10),(3,'Secondary B','Oriental',20);
                INSERT INTO users(id,name,email,password,role,company,phone,active,agent_hub_id,driver_hub_id,driver_revision)
                    VALUES(1,'Admin','admin@example.test','x','admin','ORIENTAL24','0600000000',1,NULL,NULL,1),
                          (910,'Manager A','manager-a@example.test','x','hub_manager','ORIENTAL24','0600000010',1,10,NULL,1),
                          (990,'Manager Central','manager-c@example.test','x','hub_manager','ORIENTAL24','0600000090',1,90,NULL,1),
                          (920,'Manager B','manager-b@example.test','x','hub_manager','ORIENTAL24','0600000020',1,20,NULL,1),
                          (101,'Courier A','courier-a@example.test','x','livreur','ORIENTAL24','0600000101',1,NULL,10,1),
                          (202,'Courier B','courier-b@example.test','x','livreur','ORIENTAL24','0600000202',1,NULL,20,1);
                INSERT INTO parcels(id,tracking,recipient,status,amount,driver_id,client_id,city_id,note,created_at,updated_at,invoice_id,current_hub_id,origin_hub_id)
                    VALUES(1,'TRK-RETURN-1','Customer One','Refusé',125.50,NULL,NULL,2,'', '2026-01-01T10:00:00','2026-01-01T10:00:00',700,10,10),
                          (2,'TRK-RETURN-2','Customer Two','Retourné',86.25,NULL,NULL,2,'', '2026-01-01T10:00:00','2026-01-01T10:00:00',701,10,NULL),
                          (3,'TRK-STANDARD','Customer Three','Réceptionné',40.00,NULL,NULL,2,'', '2026-01-01T10:00:00','2026-01-01T10:00:00',NULL,10,10),
                          (4,'TRK-INVOICED','Customer Four','Réceptionné',60.00,NULL,NULL,2,'', '2026-01-01T10:00:00','2026-01-01T10:00:00',702,10,10),
                          (5,'TRK-STATEMENT','Customer Five','Réceptionné',70.00,NULL,NULL,2,'', '2026-01-01T10:00:00','2026-01-01T10:00:00',NULL,10,10);
                INSERT INTO driver_statement_lines(id,parcel_id,active) VALUES(1,5,1);
            ''')

        self.services = services
        register_logistics(self.app, services)
        # register_security runs later in app.py; its service is added to this same dict.
        services['security_revoke_user']=security_revoke_user
        self.conn = conn
        with conn() as c:
            c.executemany('INSERT INTO ops_hubs(id,name,city_id,address,active,created_at) VALUES(?,?,?,?,1,?)',[
                (90,'Central Hub',1,'Central address','2026-01-01T00:00:00'),
                (10,'Hub A',2,'Address A','2026-01-01T00:00:00'),
                (20,'Hub B',3,'Address B','2026-01-01T00:00:00'),
            ])
            c.execute("INSERT INTO settings(key,value) VALUES('central_hub_id','90')")

        self.client = self.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    @staticmethod
    def headers(role, hub_id=None, actor_id=1):
        result = {'X-Role': role, 'X-Actor': str(actor_id), 'X-Name': 'Test actor'}
        if hub_id is not None:
            result['X-Hub'] = str(hub_id)
        return result

    def create_palette(self, role, hub_id, purpose, source, destination, parcel_ids, actor_id):
        return self.client.post('/api/logistics/documents', json={
            'kind': 'transfer', 'palette_purpose': purpose,
            'source_hub_id': source, 'destination_hub_id': destination,
            'parcel_ids': parcel_ids, 'transport': 'Test transport',
            'tracking_code': 'PAL-TEST-001', 'lots': 1, 'note': '',
        }, headers=self.headers(role, hub_id, actor_id))

    def scan_departure(self, doc_id, tracking, hub_id, actor_id):
        return self.client.post(f'/api/logistics/documents/{doc_id}/departure-scan',
                                json={'tracking': tracking},headers=self.headers('hub_manager',hub_id,actor_id))

    def receive(self, doc_id, tracking, hub_id, actor_id):
        return self.client.post(f'/api/logistics/documents/{doc_id}/receive',
                                json={'tracking': tracking},headers=self.headers('hub_manager',hub_id,actor_id))

    def visible_document_lines(self, doc_id, hub_id, actor_id):
        response=self.client.get('/api/logistics/documents',headers=self.headers('hub_manager',hub_id,actor_id))
        self.assertEqual(response.status_code,200,response.get_json())
        document=next(row for row in response.get_json() if row['id']==doc_id)
        return document['lines']

    def test_failed_delivery_returns_through_central_to_physical_origin_without_finance_changes(self):
        created = self.create_palette('hub_manager',10,'return_to_central',10,90,[1,2],910)
        self.assertEqual(created.status_code,200,created.get_json())
        doc_id=created.get_json()['id']
        default_tab=self.client.get('/api/logistics/palettes?tab=default',headers=self.headers('hub_manager',10,910))
        self.assertEqual(default_tab.status_code,200,default_tab.get_json())
        self.assertEqual(default_tab.get_json()['rows'],[])
        central_returns=self.client.get('/api/logistics/palettes?tab=retours',headers=self.headers('hub_manager',90,990))
        self.assertEqual(central_returns.status_code,200,central_returns.get_json())
        self.assertEqual({r['id'] for r in central_returns.get_json()['rows']},{doc_id})
        other_hub_returns=self.client.get('/api/logistics/palettes?tab=retours',headers=self.headers('hub_manager',20,920))
        self.assertEqual(other_hub_returns.status_code,200,other_hub_returns.get_json())
        self.assertEqual(other_hub_returns.get_json()['rows'],[])
        self.assertEqual({line['tracking'] for line in self.visible_document_lines(doc_id,10,910)},{'TRK-RETURN-1','TRK-RETURN-2'})
        self.assertEqual(self.scan_departure(doc_id,'TRK-RETURN-1',10,910).status_code,200)
        self.assertEqual({line['tracking'] for line in self.visible_document_lines(doc_id,10,910)},{'TRK-RETURN-1','TRK-RETURN-2'})
        departed=self.scan_departure(doc_id,'TRK-RETURN-2',10,910)
        self.assertEqual(departed.status_code,200,departed.get_json())
        self.assertEqual({line['tracking'] for line in self.visible_document_lines(doc_id,10,910)},{'TRK-RETURN-1','TRK-RETURN-2'})
        self.assertEqual({line['tracking'] for line in self.visible_document_lines(doc_id,90,990)},{'TRK-RETURN-1','TRK-RETURN-2'})

        with self.conn() as c:
            rows=c.execute('SELECT id,status,current_hub_id,origin_hub_id,amount,invoice_id FROM parcels WHERE id IN (1,2) ORDER BY id').fetchall()
        # Departure to Central keeps the delivery status (only the return state is set).
        self.assertEqual([(r['status'],r['current_hub_id'],r['origin_hub_id'],r['amount'],r['invoice_id']) for r in rows],
                         [('Refusé',None,10,125.5,700),('Retourné',None,None,86.25,701)])

        self.assertEqual(self.receive(doc_id,'TRK-RETURN-1',90,990).status_code,200)
        self.assertEqual(self.receive(doc_id,'TRK-RETURN-2',90,990).status_code,200)
        candidates=self.client.get('/api/logistics/palette-candidates?mode=return_to_origin&source_hub_id=90&destination_hub_id=10',headers=self.headers('admin'))
        self.assertEqual(candidates.status_code,200,candidates.get_json())
        self.assertEqual({r['id'] for r in candidates.get_json()['rows']},{1})

        unresolved=self.client.get('/api/logistics/palette-candidates?mode=unresolved_origin',headers=self.headers('admin'))
        self.assertEqual(unresolved.status_code,200,unresolved.get_json())
        self.assertEqual({r['id'] for r in unresolved.get_json()['rows']},{2})
        manager_unresolved=self.client.get('/api/logistics/palette-candidates?mode=unresolved_origin',headers=self.headers('hub_manager',90,990))
        self.assertEqual(manager_unresolved.status_code,403)

        review=self.client.post('/api/logistics/parcels/2/origin-review',json={
            'hub_id':10,'reason':'Vérification du registre physique de réception au Hub A',
            'evidence_reference':'PAPIER-RETOUR-2026-002','manual_physical_review':True,'confirmed':True,
        },headers=self.headers('admin'))
        self.assertEqual(review.status_code,200,review.get_json())

        candidates=self.client.get('/api/logistics/palette-candidates?mode=return_to_origin&source_hub_id=90&destination_hub_id=10',headers=self.headers('admin'))
        self.assertEqual({r['id'] for r in candidates.get_json()['rows']},{1,2})
        returned=self.create_palette('hub_manager',90,'return_to_origin',90,10,[1,2],990)
        self.assertEqual(returned.status_code,200,returned.get_json())
        second_id=returned.get_json()['id']
        incoming=self.client.get('/api/logistics/palettes?tab=a-recevoir',headers=self.headers('hub_manager',10,910))
        self.assertEqual(incoming.status_code,200,incoming.get_json())
        self.assertEqual(incoming.get_json()['rows'],[])
        self.assertEqual(self.scan_departure(second_id,'TRK-RETURN-1',90,990).status_code,200)
        self.assertEqual(self.scan_departure(second_id,'TRK-RETURN-2',90,990).status_code,200)
        incoming=self.client.get('/api/logistics/palettes?tab=a-recevoir',headers=self.headers('hub_manager',10,910))
        self.assertEqual({r['id'] for r in incoming.get_json()['rows']},{second_id})
        self.assertEqual(self.receive(second_id,'TRK-RETURN-1',10,910).status_code,200)
        self.assertEqual(self.receive(second_id,'TRK-RETURN-2',10,910).status_code,200)
        with self.conn() as c:
            rows=c.execute('SELECT id,status,current_hub_id,origin_hub_id,amount,invoice_id FROM parcels WHERE id IN (1,2) ORDER BY id').fetchall()
        # The return-to-origin journey never changed the delivery status either.
        self.assertEqual([(r['status'],r['current_hub_id'],r['origin_hub_id'],r['amount'],r['invoice_id']) for r in rows],
                         [('Refusé',10,10,125.5,700),('Retourné',10,10,86.25,701)])

    def test_manager_access_route_is_hub_scoped_and_blocking_revokes_access(self):
        blocked=self.client.post('/api/logistics/hub/drivers/101/access',json={
            'action':'block','reason':'Fin de collaboration locale','revision':1,'confirmed':True,
        },headers=self.headers('hub_manager',10,910))
        self.assertEqual(blocked.status_code,200,blocked.get_json())
        self.assertEqual(self.revocations,[(101,'Compte block par Hub Manager',910)])
        with self.conn() as c:
            driver=c.execute('SELECT active,driver_blocked,driver_revision FROM users WHERE id=101').fetchone()
        self.assertEqual((driver['active'],driver['driver_blocked'],driver['driver_revision']),(0,1,2))
        stale=self.client.post('/api/logistics/hub/drivers/101/access',json={
            'action':'unblock','reason':'Ancienne tentative','revision':1,'confirmed':True,
        },headers=self.headers('hub_manager',10,910))
        self.assertEqual(stale.status_code,409)

        cross_hub=self.client.post('/api/logistics/hub/drivers/101/access',json={
            'action':'unblock','reason':'Tentative inter-Hub','revision':2,'confirmed':True,
        },headers=self.headers('hub_manager',20,920))
        self.assertEqual(cross_hub.status_code,404)
        bypass=self.client.patch('/api/logistics/hub/drivers/101',json={
            'name':'Courier A','email':'courier-a@example.test','phone':'0600000101',
            'active':True,'password':'',
        },headers=self.headers('hub_manager',10,910))
        self.assertEqual(bypass.status_code,409)

    def test_standard_palette_candidates_exclude_invoiced_and_active_statement_lines(self):
        response=self.client.get('/api/logistics/palette-candidates?mode=standard&source_hub_id=10&destination_hub_id=90',
                                 headers=self.headers('hub_manager',10,910))
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual({r['id'] for r in response.get_json()['rows']},{3})

    def test_secondary_hub_cannot_send_directly_to_another_secondary(self):
        response=self.create_palette('hub_manager',10,'standard',10,20,[3],910)
        self.assertEqual(response.status_code,409,response.get_json())


    def parcel_state(self,pid):
        with self.conn() as c:
            return dict(c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone())

    def test_central_return_status_is_per_scanned_and_received_parcel(self):
        r=self.create_palette('hub_manager',10,'return_to_central',10,90,[1,2],910)
        self.assertEqual(r.status_code,200,r.get_json());did=r.get_json()['id']
        self.assertEqual(self.parcel_state(1)['status'],'Refusé')
        r=self.scan_departure(did,'TRK-RETURN-1',10,910)
        self.assertEqual(r.status_code,200,r.get_json())
        self.assertEqual(self.parcel_state(1)['status'],'Refusé')
        self.assertEqual(self.parcel_state(1)['return_state'],'envoye')
        self.assertIsNone(self.parcel_state(1)['current_hub_id'])
        self.assertEqual(self.parcel_state(2)['current_hub_id'],10)
        self.assertEqual(self.parcel_state(2)['status'],'Retourné')
        # Wrong Hub cannot receive, nor can the source mark its own shipment returned.
        self.assertEqual(self.receive(did,'TRK-RETURN-1',20,920).status_code,404)
        self.assertEqual(self.receive(did,'TRK-RETURN-1',10,910).status_code,404)
        self.assertEqual(self.receive(did,'TRK-RETURN-2',90,990).status_code,404)
        self.assertEqual(self.parcel_state(1)['status'],'Refusé')
        r=self.receive(did,'TRK-RETURN-1',90,990)
        self.assertEqual(r.status_code,200,r.get_json())
        self.assertEqual((self.parcel_state(1)['status'],self.parcel_state(1)['current_hub_id'],self.parcel_state(1)['return_state']),('Refusé',90,'recu_entrepot'))
        # The unscanned parcel stays at source, even after a partial Central receipt.
        self.assertEqual(self.parcel_state(2)['current_hub_id'],10)
        self.assertEqual(self.scan_departure(did,'TRK-RETURN-2',10,910).status_code,200)
        self.assertEqual(self.parcel_state(2)['status'],'Retourné')
        self.assertEqual(self.parcel_state(2)['return_state'],'envoye')
        self.assertEqual(self.receive(did,'TRK-RETURN-2',90,990).status_code,200)
        with self.conn() as c:self.assertEqual(c.execute('SELECT status FROM ops_documents WHERE id=?',(did,)).fetchone()[0],'Reçu')

    def test_admin_receipt_and_duplicate_scans_are_idempotent(self):
        r=self.create_palette('hub_manager',10,'return_to_central',10,90,[1],910);did=r.get_json()['id']
        self.assertEqual(self.scan_departure(did,'TRK-RETURN-1',20,920).status_code,404)
        self.assertEqual(self.scan_departure(did,'TRK-RETURN-1',10,910).status_code,200)
        revision=self.parcel_state(1)['ops_revision']
        r=self.scan_departure(did,'TRK-RETURN-1',10,910)
        self.assertTrue(r.get_json()['already_scanned']);self.assertEqual(self.parcel_state(1)['ops_revision'],revision)
        r=self.client.post(f'/api/logistics/documents/{did}/receive',json={'tracking':'TRK-RETURN-1'},headers=self.headers('admin'))
        self.assertEqual(r.status_code,200,r.get_json());self.assertEqual((self.parcel_state(1)['status'],self.parcel_state(1)['return_state']),('Refusé','recu_entrepot'))
        revision=self.parcel_state(1)['ops_revision']
        r=self.receive(did,'TRK-RETURN-1',90,990);self.assertTrue(r.get_json()['already_received'])
        self.assertEqual(self.parcel_state(1)['ops_revision'],revision)
        p=self.parcel_state(1);self.assertEqual((p['amount'],p['invoice_id']),(125.5,700))

    def test_new_transit_marker_rejects_status_tampering(self):
        r=self.create_palette('hub_manager',10,'return_to_central',10,90,[1],910);did=r.get_json()['id']
        self.assertEqual(self.scan_departure(did,'TRK-RETURN-1',10,910).status_code,200)
        # The delivery status is the source of truth for a return; if it is tampered to a
        # contradictory state, the Central receipt must be rejected.
        with self.conn() as c:c.execute("UPDATE parcels SET status='Livré' WHERE id=1")
        self.assertEqual(self.receive(did,'TRK-RETURN-1',90,990).status_code,404)
        r=self.client.post(f'/api/logistics/documents/{did}/receive',json={'tracking':'TRK-RETURN-1'},headers=self.headers('admin'))
        self.assertEqual(r.status_code,409)

    def test_legacy_inflight_return_can_still_be_received(self):
        r=self.create_palette('hub_manager',10,'return_to_central',10,90,[1],910);did=r.get_json()['id']
        # Simulate a return dispatched by the pre-update departure scan, which stamped the
        # legacy 'Vers Hub Central' transit marker on both the line and the parcel.
        with self.conn() as c:
            c.execute("UPDATE ops_documents SET status='En transit',dispatched_at='2026-10-10T12:00:00' WHERE id=?",(did,))
            c.execute("UPDATE ops_document_lines SET departure_scanned_at='2026-10-10T12:00:00',return_transit_status='Vers Hub Central' WHERE document_id=?",(did,))
            c.execute("UPDATE parcels SET current_hub_id=NULL,status='Vers Hub Central' WHERE id=1")
        self.assertEqual(self.receive(did,'TRK-RETURN-1',90,990).status_code,200)
        p=self.parcel_state(1)
        self.assertEqual(p['status'],'Vers Hub Central')  # legacy transit marker preserved
        self.assertEqual(p['return_state'],'recu_entrepot')
        self.assertEqual(p['current_hub_id'],90)

    def test_seller_collected_list_tracks_real_transfer_until_each_central_receipt(self):
        from ramassage_bon import register_ramassage_bon
        register_ramassage_bon(self.app,self.services)
        with self.conn() as c:
            c.execute("INSERT INTO users(id,name,email,role) VALUES(2,'Seller','seller@test','client')")
            c.execute("UPDATE parcels SET client_id=2,status='Créé',current_hub_id=NULL,invoice_id=NULL WHERE id IN (3,4)")
        admin=self.headers('admin');agent=self.headers('hub_manager',10,910)
        r=self.client.post('/api/ramassage-bons',headers=admin,json=dict(client_id=2,hub_id=10,city_id=2,address='Address',phone='0600000000',pickup_date='2026-11-01',parcel_ids=[3,4]))
        self.assertEqual(r.status_code,200,r.json);bid=r.json['id']
        self.client.post(f'/api/ramassage-bons/{bid}/validate',headers=admin)
        url='/api/ramassage-bons/hub/collected'
        self.assertEqual(self.client.get(url,headers=agent).json['total'],0)
        detail=self.client.get(f'/api/ramassage-bons/{bid}',headers=agent).json
        r=self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=agent,json=dict(parcel_ids=[3,4],snapshot=detail['snapshot'],confirmed=True,request_key='test-collected-central-001'))
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.client.get(url,headers=agent).json['counts'],{'at_hub':2})
        self.assertEqual(self.client.get(url,headers=self.headers('hub_manager',20,920)).json['total'],0)
        r=self.create_palette('hub_manager',10,'standard',10,90,[3,4],910)
        self.assertEqual(r.status_code,200,r.json);did=r.json['id']
        self.assertEqual(self.client.get(url,headers=agent).json['counts'],{'prepared':2})
        self.assertEqual(self.scan_departure(did,'TRK-STANDARD',10,910).status_code,200)
        self.assertEqual(self.client.get(url,headers=agent).json['counts'],{'transit':1,'prepared':1})
        self.assertEqual(self.receive(did,'TRK-STANDARD',90,990).status_code,200)
        self.assertEqual(self.client.get(url,headers=agent).json['total'],1)
        self.assertEqual(self.client.get(url,headers=agent).json['rows'][0]['parcel_id'],4)
        self.assertEqual(self.scan_departure(did,'TRK-INVOICED',10,910).status_code,200)
        self.assertEqual(self.client.get(url,headers=agent).json['counts'],{'transit':1})
        self.assertEqual(self.receive(did,'TRK-INVOICED',90,990).status_code,200)
        self.assertEqual(self.client.get(url,headers=agent).json['total'],0)
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM ramassage_central_receipts').fetchone()[0],2)
            c.execute("UPDATE settings SET value='20' WHERE key='central_hub_id'")
        self.assertEqual(self.client.get(url,headers=agent).json['total'],0)

    def test_standard_transfers_still_use_transit_then_receptionne(self):
        r=self.create_palette('hub_manager',10,'standard',10,90,[3],910)
        self.assertEqual(r.status_code,200,r.get_json());did=r.get_json()['id'];track=self.parcel_state(3)['tracking']
        self.assertEqual(self.scan_departure(did,track,10,910).status_code,200)
        self.assertEqual(self.parcel_state(3)['status'],'Transit')
        self.assertEqual(self.receive(did,track,90,990).status_code,200)
        self.assertEqual(self.parcel_state(3)['status'],'Réceptionné')

    def outbound_transfer(self):
        with self.conn() as c:
            c.execute('UPDATE parcels SET current_hub_id=90,city_id=2 WHERE id=3')
        r=self.create_palette('hub_manager',90,'standard',90,10,[3],990)
        self.assertEqual(r.status_code,200,r.get_json())
        return r.get_json()['id'],self.parcel_state(3)['tracking']

    def test_outbound_city_match_is_accepted_once(self):
        did,tracking=self.outbound_transfer()
        r=self.scan_departure(did,tracking,90,990)
        self.assertEqual(r.status_code,200,r.get_json())
        self.assertEqual(self.parcel_state(3)['status'],'Transit')
        again=self.scan_departure(did,tracking,90,990)
        self.assertTrue(again.get_json()['already_scanned'])
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND departure_scanned_at IS NOT NULL',(did,)).fetchone()[0],1)

    def test_city_mapping_is_rechecked_at_scan_without_mutation(self):
        did,tracking=self.outbound_transfer()
        with self.conn() as c:c.execute('UPDATE cities SET hub_id=20 WHERE id=2')
        before=self.parcel_state(3)
        r=self.scan_departure(did,tracking,90,990)
        self.assertEqual(r.status_code,409,r.get_json())
        self.assertIn('Choisissez un autre Hub',r.get_json()['error'])
        self.assertEqual(self.parcel_state(3),before)
        with self.conn() as c:
            self.assertIsNone(c.execute('SELECT departure_scanned_at FROM ops_document_lines WHERE document_id=?',(did,)).fetchone()[0])
            self.assertEqual(c.execute('SELECT status FROM ops_documents WHERE id=?',(did,)).fetchone()[0],'Préparé')
        r=self.client.post(f'/api/logistics/documents/{did}/departure-scan',json={'tracking':tracking},headers=self.headers('admin'))
        self.assertEqual(r.status_code,409,r.get_json())

    def test_unassigned_city_and_inactive_destination_are_rejected(self):
        did,tracking=self.outbound_transfer()
        with self.conn() as c:c.execute('UPDATE cities SET hub_id=NULL WHERE id=2')
        self.assertEqual(self.scan_departure(did,tracking,90,990).status_code,409)
        with self.conn() as c:
            c.execute('UPDATE cities SET hub_id=10 WHERE id=2')
            c.execute('UPDATE ops_hubs SET active=0 WHERE id=10')
        self.assertEqual(self.scan_departure(did,tracking,90,990).status_code,409)

    def test_unlisted_local_wrong_city_explained_but_foreign_not_disclosed(self):
        did,_=self.outbound_transfer()
        with self.conn() as c:
            c.execute('UPDATE parcels SET current_hub_id=90,city_id=3 WHERE id=4')
            tracking=c.execute('SELECT tracking FROM parcels WHERE id=4').fetchone()[0]
        r=self.scan_departure(did,tracking,90,990)
        self.assertEqual(r.status_code,409,r.get_json())
        self.assertIn('Secondary B',r.get_json()['error'])
        with self.conn() as c:c.execute('UPDATE parcels SET current_hub_id=20 WHERE id=4')
        r=self.scan_departure(did,tracking,90,990)
        self.assertEqual(r.status_code,404,r.get_json())
        self.assertNotIn('Secondary B',r.get_json()['error'])

if __name__=='__main__':
    unittest.main()
