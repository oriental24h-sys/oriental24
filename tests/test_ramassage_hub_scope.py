import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime
from functools import wraps

from flask import Flask, g, jsonify, request

from ramassage_tower import register_ramassage_tower
from tour_control import register_tour_control


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class RamassageHubScopeTests(unittest.TestCase):
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
                    if not actor or actor['role'] not in roles:
                        raise APIError('Forbidden', 403)
                    return fn(*args, **kwargs)
                return wrapped
            return decorate

        @self.app.before_request
        def set_actor():
            raw_hub = request.headers.get('X-Hub')
            g.actor = {
                'id': int(request.headers.get('X-Actor', '900')),
                'role': request.headers.get('X-Role', 'agent'),
                'agent_hub_id': int(raw_hub) if raw_hub else None,
                'name': 'Test actor',
            }

        @self.app.errorhandler(APIError)
        def api_error(exc):
            return jsonify(error=str(exc)), exc.status

        def now():
            return datetime.now().isoformat(timespec='seconds')

        services = {
            'conn': conn,
            'auth': auth,
            'user': lambda: g.actor,
            'now': now,
            'APIError': APIError,
            'event': lambda *args, **kwargs: None,
            'parcel': lambda *args, **kwargs: None,
        }
        with conn() as c:
            c.executescript('''
                CREATE TABLE cities(
                    id INTEGER PRIMARY KEY,name TEXT NOT NULL,region TEXT,
                    delivery INTEGER NOT NULL DEFAULT 1,pickup INTEGER NOT NULL DEFAULT 1,
                    hub_id INTEGER
                );
                CREATE TABLE ops_hubs(
                    id INTEGER PRIMARY KEY,name TEXT NOT NULL,city_id INTEGER NOT NULL,
                    address TEXT NOT NULL DEFAULT '',active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00'
                );
                CREATE TABLE users(
                    id INTEGER PRIMARY KEY,name TEXT NOT NULL,phone TEXT,role TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,driver_hub_id INTEGER,driver_city_id INTEGER,agent_hub_id INTEGER
                );
                CREATE TABLE parcels(
                    id INTEGER PRIMARY KEY,tracking TEXT,recipient TEXT,status TEXT,amount REAL,
                    driver_id INTEGER,updated_at TEXT,city_id INTEGER
                );
                CREATE TABLE vehicles(
                    id INTEGER PRIMARY KEY,driver_id INTEGER,label TEXT,type TEXT,plate TEXT,
                    battery_pct REAL,state TEXT,active INTEGER NOT NULL DEFAULT 1
                );
                INSERT INTO cities(id,name,region,pickup,hub_id) VALUES
                    (1,'Oujda','Oriental',1,10),(2,'Berkane','Oriental',1,20);
                INSERT INTO ops_hubs(id,name,city_id,address,active) VALUES
                    (10,'Hub Oujda',1,'Oujda',1),(20,'Hub Berkane',2,'Berkane',1);
                INSERT INTO users(id,name,phone,role,active,driver_hub_id,driver_city_id,agent_hub_id) VALUES
                    (101,'Livreur Oujda','0600000001','livreur',1,10,1,NULL),
                    (202,'Livreur Berkane','0600000002','livreur',1,20,2,NULL),
                    (910,'Manager Oujda','0600000010','agent',1,NULL,NULL,10),
                    (920,'Manager Berkane','0600000020','agent',1,NULL,NULL,20);
                INSERT INTO vehicles(id,driver_id,label,type,state,active) VALUES
                    (1,101,'Moto Oujda','moto','available',1),(2,202,'Moto Berkane','moto','available',1);
            ''')

        register_tour_control(self.app, services)
        register_ramassage_tower(self.app, services)
        self.conn = conn
        self.now = now
        stamp = now()
        with conn() as c:
            c.execute('INSERT INTO driver_positions(driver_id,lat,lng,city_id,created_at) VALUES(101,34.681,-1.912,1,?)', (stamp,))
            c.execute('INSERT INTO driver_positions(driver_id,lat,lng,city_id,created_at) VALUES(202,34.929,-1.979,2,?)', (stamp,))
            c.execute("INSERT INTO ramassage_driver_state(driver_id,availability,full_load,gps_enabled,updated_at) VALUES(101,'available',0,1,?)", (stamp,))
            c.execute("INSERT INTO ramassage_driver_state(driver_id,availability,full_load,gps_enabled,updated_at) VALUES(202,'available',0,1,?)", (stamp,))
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except FileNotFoundError:
            pass

    def request_as(self, role, hub_id=None, actor_id=900):
        headers = {'X-Role': role, 'X-Actor': str(actor_id)}
        if hub_id is not None:
            headers['X-Hub'] = str(hub_id)
        return headers

    @staticmethod
    def pickup_body(city_id, maps_url):
        return {
            'name': 'Client test',
            'phone': '+212600000000',
            'maps_url': maps_url,
            'city_id': city_id,
            'parcels_count': 2,
        }

    def create_pickup(self, hub_id, city_id, maps_url):
        return self.client.post(
            '/api/control-tower/ramassage',
            json=self.pickup_body(city_id, maps_url),
            headers=self.request_as('agent', hub_id, actor_id=900 + hub_id),
        )

    def test_manager_tower_payload_exposes_only_own_hub_zone_and_drivers(self):
        local = self.create_pickup(10, 1, 'https://www.google.com/maps/@34.681,-1.912,15z')
        remote = self.create_pickup(20, 2, 'https://www.google.com/maps/@34.929,-1.979,15z')
        self.assertEqual(local.status_code, 200, local.get_json())
        self.assertEqual(remote.status_code, 200, remote.get_json())

        response = self.client.get('/api/control-tower', headers=self.request_as('agent', 10))
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload['manager_hub']['id'], 10)
        self.assertEqual({d['id'] for d in payload['map_drivers']}, {101})
        self.assertEqual({j['id'] for j in payload['ramassage_jobs']}, {local.get_json()['job_id']})
        self.assertEqual({c['city_id'] for c in payload['ramassage_clients']}, {1})
        self.assertEqual({h['id'] for h in payload['hubs']}, {10})
        self.assertNotIn('parcels', payload)
        self.assertEqual(payload['drivers'], [])

        map_response = self.client.get('/api/control-tower/map-data', headers=self.request_as('agent', 10))
        self.assertEqual(map_response.status_code, 200, map_response.get_json())
        self.assertEqual({d['id'] for d in map_response.get_json()['map_drivers']}, {101})

    def test_creation_and_candidate_assignment_are_hub_and_city_scoped(self):
        outside = self.create_pickup(10, 2, 'https://www.google.com/maps/@34.929,-1.979,15z')
        self.assertEqual(outside.status_code, 403, outside.get_json())

        created = self.create_pickup(20, 2, 'https://www.google.com/maps/@34.929,-1.979,15z')
        self.assertEqual(created.status_code, 200, created.get_json())
        job_id = created.get_json()['job_id']

        candidates = self.client.get(
            f'/api/control-tower/ramassage/{job_id}/candidates',
            headers=self.request_as('agent', 10),
        )
        self.assertEqual(candidates.status_code, 404)
        assign = self.client.post(
            f'/api/control-tower/ramassage/{job_id}/assign',
            json={'driver_id': 101},
            headers=self.request_as('agent', 10),
        )
        self.assertEqual(assign.status_code, 404)

    def test_automatic_assignment_uses_only_the_managers_hub_drivers(self):
        # Even with the other Hub's driver physically standing inside Oujda, hub membership wins.
        stamp = self.now()
        with self.conn() as c:
            c.execute('UPDATE driver_positions SET lat=34.681,lng=-1.912,city_id=1,created_at=? WHERE driver_id=202', (stamp,))
            c.execute("UPDATE ramassage_driver_state SET gps_enabled=1,availability='available',full_load=0,updated_at=? WHERE driver_id=202", (stamp,))
            c.execute("UPDATE ramassage_settings SET value='1' WHERE key='auto_dispatch'")

        created = self.create_pickup(10, 1, 'https://www.google.com/maps/@34.681,-1.912,15z')
        self.assertEqual(created.status_code, 200, created.get_json())
        self.assertTrue(created.get_json()['auto_dispatched'])
        with self.conn() as c:
            job = c.execute('SELECT driver_id,hub_id FROM ramassage_jobs WHERE id=?', (created.get_json()['job_id'],)).fetchone()
        self.assertEqual(job['driver_id'], 101)
        self.assertEqual(job['hub_id'], 10)

    def test_manager_cannot_read_another_hubs_driver_route_history(self):
        denied = self.client.get('/api/control-tower/route-history/202', headers=self.request_as('agent', 10))
        self.assertEqual(denied.status_code, 404)
        allowed = self.client.get('/api/control-tower/route-history/101', headers=self.request_as('agent', 10))
        self.assertEqual(allowed.status_code, 200, allowed.get_json())
        self.assertGreaterEqual(allowed.get_json()['count'], 1)


if __name__ == '__main__':
    unittest.main()
