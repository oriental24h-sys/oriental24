"""v1.4.17 audit pilotage : every refused physical reception is recorded with who and why."""
import unittest, secrets
import test_client_types as types

system = types.system
P = '/api/partner-palettes'


class ReceptionGuardAuditTests(unittest.TestCase):
    data = types.ClientTypesTests.data
    mutate = types.ClientTypesTests.mutate
    make_account = types.ClientTypesTests.make_account
    shipment = types.ClientTypesTests.shipment
    create = types.ClientTypesTests.create
    parcel_by_tracking = types.ClientTypesTests.parcel_by_tracking

    def setUp(self):
        types.ClientTypesTests.setUp(self)
        self.hub = self.mutate(self.admin, '/api/logistics/hubs', dict(name='Hub Audit refus', city_id=1, address='Fictif')).json['id']
        self.hub2 = self.mutate(self.admin, '/api/logistics/hubs', dict(name='Hub second', city_id=2, address='Fictif bis')).json['id']
        self.ps = []
        for n in range(2):
            r = self.create(tracking=f'Refus-000{n}/T')
            self.assertEqual(r.status_code, 200, r.json)
            self.ps.append(self.parcel_by_tracking(r.json['tracking']))
        d = dict(client_id=self.company['id'], destination_hub_id=self.hub,
                 parcel_ids=[p['id'] for p in self.ps], request_key=secrets.token_hex(16))
        r = self.mutate(self.company_user, P, d)
        self.assertEqual(r.status_code, 200, r.json)
        self.did = r.json['id']
        snd = dict(revision=1, confirmed=True, request_key=secrets.token_hex(16))
        self.assertEqual(self.mutate(self.admin, f'{P}/{self.did}/dispatch', snd).status_code, 200)
        self.local = self.make_agent(self.hub)
        self.foreign = self.make_agent(self.hub2)

    def make_agent(self, hub):
        email = secrets.token_hex(6) + '@example.test'
        r = self.mutate(self.admin, '/api/users', dict(role='agent', name='Agent Audit', email=email,
                                                       password='Oriental24!Demo', phone='0600000000',
                                                       company='', agent_hub_id=hub))
        self.assertEqual(r.status_code, 200, r.json)
        c = system.app.test_client()
        c.post('/api/login', json=dict(email=email, password='Oriental24!Demo'))
        return c

    def payload(self, **kw):
        d = dict(revision=self.admin.get(f'{P}/{self.did}').json['revision'], confirmed=True,
                 request_key=secrets.token_hex(16), tracking=self.ps[0]['tracking'])
        d.update(kw)
        return d

    def refusals(self):
        return [a for a in self.admin.get(f'{P}/{self.did}').json['audit'] if a['action'] == 'Réception refusée']

class RoleRefusalAudit(ReceptionGuardAuditTests):
    def test_company_role_refusal_is_recorded_with_who_and_why(self):
        r = self.mutate(self.company_user, f'{P}/{self.did}/receive', self.payload())
        self.assertEqual(r.status_code, 403, r.json)
        rows = self.refusals()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]['details']['reason'], 'Rôle non autorisé à la réception physique')
        self.assertEqual(rows[0]['details']['actor_role'], 'client')
        self.assertTrue(rows[0]['actor'], rows[0])

    def test_livreur_role_refusal_is_recorded_too(self):
        r = self.mutate(self.driver, f'{P}/{self.did}/receive', self.payload())
        self.assertEqual(r.status_code, 403, r.json)
        rows = self.refusals()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]['details']['actor_role'], 'livreur')

class HubRefusalAudit(ReceptionGuardAuditTests):
    def test_wrong_hub_agent_is_blocked_recorded_and_not_leaking(self):
        self.assertEqual(self.foreign.get(f'{P}/{self.did}').status_code, 404)
        r = self.mutate(self.foreign, f'{P}/{self.did}/receive', self.payload())
        self.assertEqual(r.status_code, 404, r.json)
        self.assertEqual(r.json['error'], 'Palette introuvable pour votre hub.')
        rows = self.refusals()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]['details']['reason'], 'Agent rattaché à un autre hub')
        self.assertEqual((rows[0]['details']['actor_hub_id'], rows[0]['details']['palette_hub_id']),
                         (self.hub2, self.hub))

    def test_legit_hub_agent_receives_and_audit_stays_clean(self):
        self.assertEqual(self.refusals(), [])
        r = self.mutate(self.local, f'{P}/{self.did}/receive', self.payload())
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(self.refusals(), [])
        self.assertIn('Colis scanné reçu', [a['action'] for a in self.admin.get(f'{P}/{self.did}').json['audit']])

class UnknownPaletteNoAudit(ReceptionGuardAuditTests):
    def test_unknown_document_errors_without_orphan_audit_row(self):
        r = self.mutate(self.company_user, P + '/99999/receive', self.payload())
        self.assertEqual(r.status_code, 403, r.json)
        r2 = self.mutate(self.local, P + '/99999/receive', self.payload())
        self.assertEqual(r2.status_code, 404, r2.json)
        self.assertEqual(self.refusals(), [])

if __name__ == '__main__':
    unittest.main()
