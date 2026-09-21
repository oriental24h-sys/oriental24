"""Incidents de réception, agent hub, alertes de retard, tarifs client."""
import secrets, unittest
import test_client_types as types, test_partner_palettes as palettes

system = types.system
P = '/api/partner-palettes'


class ReceptionExtrasTests(unittest.TestCase):
    data = types.ClientTypesTests.data
    mutate = types.ClientTypesTests.mutate
    make_account = types.ClientTypesTests.make_account
    shipment = palettes.PartnerPaletteTests.shipment
    create = palettes.PartnerPaletteTests.create
    parcel_by_tracking = palettes.PartnerPaletteTests.parcel_by_tracking
    draft_data = palettes.PartnerPaletteTests.draft_data
    draft = palettes.PartnerPaletteTests.draft
    detail = palettes.PartnerPaletteTests.detail
    action = palettes.PartnerPaletteTests.action
    dispatch = palettes.PartnerPaletteTests.dispatch
    state = palettes.PartnerPaletteTests.state

    def setUp(self):
        types.ClientTypesTests.setUp(self)
        self.hub = self.mutate(self.admin, '/api/logistics/hubs', dict(name='Hub Réception test', city_id=1, address='Adresse fictive')).json['id']
        self.ps = []
        for n in range(3):
            r = self.create(tracking=f'Soc-0000{n}/Ab')
            self.assertEqual(r.status_code, 200, r.json)
            self.ps.append(self.parcel_by_tracking(r.json['tracking']))
        self.did = self.draft()
        self.dispatch(self.did)

    def make_agent(self, hub=None):
        email = secrets.token_hex(6) + '@example.test'
        r = self.mutate(self.admin, '/api/users', dict(role='agent', name='Agent Test', email=email, password='Oriental24!Demo',
                                                       phone='0600000000', company='', agent_hub_id=hub or self.hub))
        self.assertEqual(r.status_code, 200, r.json)
        return self.login(email)

    def login(self, email):
        c = system.app.test_client()
        self.assertEqual(c.post('/api/login', json={'email': email, 'password': 'Oriental24!Demo'}).status_code, 200)
        return c

    def incident(self, path, payload, user=None, key=None):
        u = user or self.admin
        h = {'X-CSRF-Token': self.data(u)['csrf']}
        payload.setdefault('request_key', key or ('RX-' + secrets.token_hex(12)))
        return u.post(P + f'/{self.did}' + path, json=payload, headers=h)

    def incidents(self, user=None):
        return (user or self.admin).get(P + f'/{self.did}/incidents')

    def patch_parcel(self, user, pid, data):
        return user.patch(f'/api/parcels/{pid}', json=data, headers={'X-CSRF-Token': self.data(user)['csrf']})

    # ------------------------------------------------------------------
    def test_missing_line_released_palette_stays_open_then_closes_with_gaps(self):
        line = self.detail(self.did)['lines'][2]
        r = self.incident('/incidents', dict(kind='missing', line_id=line['id'], note='Absent au déchargement', confirmed=True))
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual((r.json['remaining'], r.json['status']), (2, 'En transit'))
        # Le colis déclaré manquant est déverrouillé mais PAS réceptionné.
        pid = line['parcel_id']
        parcel = self.admin.get(f'/api/parcels/{pid}').json['parcel']
        self.assertFalse(parcel['operations_locked'])
        self.assertEqual(parcel['status'], 'Créé')
        self.assertFalse(self.detail(self.did)['lines'][2]['active'])
        # Rejouer la MÊME clé avec la même saisie ne crée pas de second dossier.
        k = key()
        one = self.incident('/incidents', dict(kind='extra', tracking='Carton-Replay', note='Hors liste', confirmed=True, request_key=k))
        two = self.incident('/incidents', dict(kind='extra', tracking='Carton-Replay', note='Hors liste', confirmed=True, request_key=k))
        self.assertEqual((one.status_code, two.status_code, two.json['replayed']), (200, 200, True))
        self.assertEqual(len([x for x in self.incidents().json['rows'] if x['kind'] == 'missing']), 1)
        self.assertEqual(len([x for x in self.incidents().json['rows'] if x['kind'] == 'extra']), 1)
        # Impossible de scanner le colis déclaré manquant.
        r = self.action(self.did, 'receive', self.admin,
                        tracking=line['tracking'], confirmed=True, revision=self.detail(self.did)['revision'],
                        request_key=secrets.token_hex(16))
        self.assertEqual(r.status_code, 404)
        # Réceptionner les deux restants, révision obsolète rejetée, puis clôture avec écarts.
        for i, t in enumerate([self.ps[0]['tracking'], self.ps[1]['tracking']]):
            r = self.action(self.did, 'receive', self.admin, tracking=t, confirmed=True,
                            revision=self.detail(self.did)['revision'], request_key=secrets.token_hex(16))
            self.assertEqual(r.status_code, 200, r.json)
        r = self.action(self.did, 'close-gaps', self.admin, reason='Carton incomplet au déchargement', confirmed=True,
                        expected_remaining=0, revision=self.detail(self.did)['revision'], request_key=secrets.token_hex(16))
        self.assertEqual(r.status_code, 409)  # plus aucun colis à déclarer
        self.assertEqual(self.detail(self.did)['status'], 'Reçu')

    def test_company_follows_up_alerts_and_scans_blocked_tracking(self):
        unit = None

    # ------------------------------------------------------------------
    def test_extra_and_damaged_response_resolution_and_assignment_block(self):
        # Imprévu : note obligatoire et suivi sans mutation.
        r = self.incident('/incidents', dict(kind='extra', tracking='CARTON-SEUL', note='', confirmed=True))
        self.assertEqual(r.status_code, 400)
        r = self.incident('/incidents', dict(kind='extra', tracking='CARTON-SEUL', note='Hors palette', confirmed=True))
        self.assertEqual(r.status_code, 200, r.json)
        # Endommagé : photo obligatoire, réception physique, affectation suspendue.
        target = self.detail(self.did)['lines'][1]
        r = self.incident('/incidents', dict(kind='damaged', tracking=target['tracking'], note='Carton arraché', confirmed=True))
        self.assertEqual(r.status_code, 400)
        r = self.incident('/incidents', dict(kind='damaged', tracking=target['tracking'], note='Carton arraché', confirmed=True))
        self.assertEqual(r.status_code, 400)
        bad = dict(kind='damaged', tracking=target['tracking'], note='Carton arraché', confirmed=True,
                   photo={'name': 'note.txt', 'content': 'bm90ZXM='})
        r = self.incident('/incidents', bad)
        self.assertEqual(r.status_code, 400, r.json)
        good = dict(kind='damaged', tracking=target['tracking'], note='Carton arraché au déchargement', confirmed=True,
                    photo={'name': 'degat.png', 'content': TINY_PNG_B64})
        r = self.incident('/incidents', good)
        self.assertEqual(r.status_code, 200, r.json)
        iid = r.json.get('incident_id', None) or self.incidents().json['rows'][0]['id']
        pid = target['parcel_id']
        self.assertEqual(self.admin.get(f'/api/parcels/{pid}').json['parcel']['status'], 'Réceptionné')
        self.assertFalse(self.admin.get(f'/api/parcels/{pid}').json['parcel']['operations_locked'])
        # Affectation bloquée (patch admin + scan-preview).
        r = self.patch_parcel(self.admin, pid, {'driver_id': 3})
        self.assertEqual(r.status_code, 409)
        self.assertIn('endommagé', r.json['error'])
        # La société répond ; un autre client ne peut pas.
        resp = self.mutate(self.company_user, P + f'/{self.did}/incidents/{iid}/respond', {'response': 'Nous assumerons le dommage.'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.mutate(self.client, P + f'/{self.did}/incidents/{iid}/respond', {'response': 'x'}).status_code, 403)
        # Libération : release lève le blocage, notifications des deux côtés.
        r = self.mutate(self.admin, P + f'/{self.did}/incidents/{iid}/resolve', {'note': 'Réparé à l’atelier', 'action': 'release'})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(self.patch_parcel(self.admin, pid, {'driver_id': 3}).status_code, 200)
        photo = self.admin.get(f'/api/partner-palette-incidents/{iid}/photo')
        self.assertEqual(photo.status_code, 200)
        self.assertEqual(photo.mimetype, 'image/jpeg')
        self.assertEqual(self.client.get(f'/api/partner-palette-incidents/{iid}/photo').status_code, 404)
        notifs = self.company_user.get('/api/logistics/notifications').json
        titles = [n['title'] for n in notifs['items']]
        self.assertTrue(any('incident' in t.lower() for t in titles), titles)
        # Hold puis release garde le blocage jusqu'à la libération.
        r = self.incident('/incidents', dict(kind='damaged', tracking=self.ps[2]['tracking'], note='Humide', confirmed=True,
                                             photo={'name': 'h.png', 'content': TINY_PNG_B64}))
        iid2 = [x for x in self.incidents().json['rows'] if x['tracking'] == self.ps[2]['tracking']][0]['id']
        pid2 = [l for l in self.detail(self.did)['lines'] if l['tracking'] == self.ps[2]['tracking']][0]['parcel_id']
        self.assertEqual(self.mutate(self.admin, P + f'/{self.did}/incidents/{iid2}/resolve', {'note': 'On attend', 'action': 'hold'}).status_code, 200)
        self.assertEqual(self.patch_parcel(self.admin, pid2, {'driver_id': 3}).status_code, 409)
        # scan-preview côté livreur exclut le colis bloqué.
        admins_scan = self.admin.post('/api/scan', json={'tracking': self.ps[2]['tracking']},
                                      headers={'X-CSRF-Token': self.data(self.admin)['csrf']})
        self.assertEqual(admins_scan.status_code, 200)

    # ------------------------------------------------------------------
    def test_agent_hub_scoping_and_permissions(self):
        # Sans hub réservé ou avec hub inactive → Admin refuse la création.
        self.assertEqual(self.mutate(self.admin, '/api/users', dict(role='agent', name='A', email=secrets.token_hex(5) + '@x.test',
                                    password='Oriental24!Demo', phone='0600000000')).status_code, 400)
        agent = self.make_agent()
        rows = agent.get(P).json['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(agent.get('/api/partner-palettes/candidates').status_code, 403)
        self.assertEqual(self.mutate(agent, '/api/partner-palettes', {'parcel_ids': [1], 'destination_hub_id': self.hub,
                                      'request_key': secrets.token_hex(16)}).status_code, 403)
        # Réception d'un colis par l'agent du hub ; dispatch/interdit.
        t = self.ps[0]['tracking']
        r = self.action(self.did, 'receive', agent, tracking=t, confirmed=True,
                        revision=self.detail(self.did)['revision'], request_key=secrets.token_hex(16))
        self.assertEqual(r.status_code, 200, r.json)
        audit = self.detail(self.did)['audit']
        self.assertEqual(audit[0]['actor'], 'Agent Test')
        self.assertEqual(self.action(self.did, 'cancel', agent, confirmed=True,
                                     revision=self.detail(self.did)['revision'], request_key=secrets.token_hex(16)).status_code, 403)
        # Un agent d'un autre hub ne voit pas les documents du hub 1.
        other_agent = self.make_agent(self.second_hub())
        self.assertEqual(other_agent.get(P).json['total'], 0)
        self.assertEqual(other_agent.get(P + f'/{self.did}').status_code, 404)
        self.assertEqual(other_agent.get('/api/bootstrap').json['parcels'], [])
        self.assertEqual(other_agent.get('/api/invoices').status_code, 403)
        # Admin voit toujours tout ; agent_hub_id exposé aux listes Bootstrap.
        self.assertIn(self.did, [r['id'] for r in self.admin.get(P).json['rows']])
        boot = self.data(self.admin)
        agent_row = next(u for u in boot['users'] if u['role'] == 'agent')
        self.assertEqual(agent_row['agent_hub_id'], self.hub)
        uid = next(u['id'] for u in self.data(self.admin)['users'] if u['role'] == 'agent')
        u = next(u for u in self.data(self.admin)['users'] if u['id'] == uid)
        self.assertEqual(self.mutate(self.admin, f'/api/users/{uid}', {**u, 'active': False, 'agent_hub_id': self.hub}, 'patch').status_code, 200)
        self.assertEqual(agent.get('/api/bootstrap').status_code, 401)

    def second_hub(self):
        if not hasattr(self, '_hub2'):
            r = self.mutate(self.admin, '/api/logistics/hubs', dict(name='Hub Second test', city_id=1, address='Adresse fictive'))
            self._hub2 = r.json['id']
        return self._hub2

    # ------------------------------------------------------------------
    def test_tariffs_apply_only_to_new_parcels_and_audit(self):
        cid = self.company['id']
        r = self.admin.get(f'/api/clients/{cid}/tariffs')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json['cities'])
        city = next(c for c in r.json['cities'] if c['city'] == 'Oujda')['city_id']
        self.assertIsNone(next(c for c in r.json['cities'] if c['city_id'] == city)['fee'])
        self.assertEqual(self.mutate(self.admin, f'/api/clients/{cid}/tariffs/{city}', {'fee': 19.5, 'return_fee': 7}, 'put').status_code, 200)
        self.assertEqual(self.create(user=self.company_user, tracking='Soc-7777/Tr').status_code, 200)
        p = self.parcel_by_tracking('Soc-7777/Tr')
        self.assertEqual((p['fee'], p['return_fee']), (19.5, 7.0))
        # Les anciens colis restent aux décorations initiales.
        self.assertEqual(self.ps[0]['fee'], 25)
        # Idempotent PUT + audit.
        self.assertEqual(self.mutate(self.admin, f'/api/clients/{cid}/tariffs/{city}', {'fee': 19.5, 'return_fee': 7}, 'put').json['changed'], False)
        audit = self.admin.get(f'/api/clients/{cid}/tariffs').json['audit']
        self.assertEqual(audit[0]['new_fee'], 19.5)
        # DELETE : retour au défaut, historisé.
        self.assertEqual(self.mutate(self.admin, f'/api/clients/{cid}/tariffs/{city}', None, 'delete').status_code, 200)
        self.assertEqual(self.admin.get(f'/api/clients/{cid}/tariffs').json['audit'][0]['new_fee'], None)
        self.assertEqual(self.mutate(self.admin, f'/api/clients/{cid}/tariffs/{city}', {'fee': -1, 'return_fee': 7}, 'put').status_code, 400)
        self.assertEqual(self.mutate(self.client, f'/api/clients/{cid}/tariffs/{city}', {'fee': 1, 'return_fee': 1}, 'put').status_code, 403)
        self.assertEqual(self.mutate(self.admin, f'/api/clients/{cid}/tariffs/9999', {'fee': 1, 'return_fee': 1}, 'put').status_code, 404)
        self.assertEqual(self.mutate(self.admin, f'/api/clients/9999/tariffs/{city}', {'fee': 1, 'return_fee': 1}, 'put').status_code, 404)

    # ------------------------------------------------------------------
    def test_alerts_thresholds_scoping_and_settings(self):
        with system.conn() as c:
            c.execute("UPDATE ops_documents SET dispatched_at=datetime('now','-3 days') WHERE id=?", (self.did,))
        # Réception partielle ancienne : transit + partial + unassigned (colis réceptionné non affecté).
        line = self.detail(self.did)['lines'][0]
        rev = self.detail(self.did)['revision']
        self.assertEqual(self.action(self.did, 'receive', self.admin, tracking=line['tracking'], confirmed=True, revision=rev,
                                     request_key=secrets.token_hex(16)).status_code, 200)
        with system.conn() as c:
            c.execute("UPDATE parcels SET updated_at=datetime('now','-2 days') WHERE id=(SELECT parcel_id FROM ops_document_lines WHERE document_id=? AND received_at IS NOT NULL LIMIT 1)", (self.did,))
        g = {x['kind']: x for x in self.admin.get('/api/alerts').json['groups']}
        self.assertEqual(len(g['unassigned']['items']), 1)
        self.assertEqual(len(g['partial']['items']), 1)
        self.assertEqual(self.client.get('/api/alerts').status_code, 403)
        self.assertEqual(self.admin.get('/api/alerts').status_code, 200)
        agent = self.make_agent()
        ga = {x['kind']: x for x in agent.get('/api/alerts').json['groups']}
        self.assertEqual(len(ga['partial']['items']), 1)
        self.assertEqual(len(ga['unassigned']['items']), 1)
        # Seuils : 0 désactive ; >720 invalide ; mise à jour côté settings.
        st = {'announcement': '', 'alert_partial_hours': 0, 'alert_transit_hours': 48, 'alert_unassigned_hours': 24}
        self.assertEqual(self.mutate(self.admin, '/api/settings', st, 'patch').status_code, 200)
        self.assertEqual({x['kind']: x for x in self.admin.get('/api/alerts').json['groups']}['partial']['items'], [])
        st['alert_transit_hours'] = 721
        self.assertEqual(self.mutate(self.admin, '/api/settings', st, 'patch').status_code, 400)
        st.update({'announcement': self.data(self.admin)['settings']['announcement'], 'alert_transit_hours': 48, 'alert_partial_hours': 24})
        self.assertEqual(self.mutate(self.admin, '/api/settings', st, 'patch').status_code, 200)

    # ------------------------------------------------------------------
    def test_partner_company_follows_received_and_missing_states(self):
        line = self.detail(self.did)['lines'][1]
        self.assertEqual(self.incident('/incidents', dict(kind='missing', line_id=line['id'], note='Non reçu', confirmed=True)).status_code, 200)
        rev = self.detail(self.did)['revision']
        self.assertEqual(self.action(self.did, 'receive', self.admin, tracking=self.ps[0]['tracking'], confirmed=True, revision=rev,
                                     request_key=secrets.token_hex(16)).status_code, 200)
        d = self.mutate(self.company_user, P + f'/{self.did}', {}, 'get')
        lines = {l['tracking']: l for l in self.detail(self.did)['lines']}
        self.assertEqual(self.company_user.get(P + f'/{self.did}').status_code, 200)
        detail = self.company_user.get(P + f'/{self.did}').json
        self.assertIn('missing', detail)
        self.assertEqual(detail['missing'], 1)
        cols = self.company_user.get(P).json['rows'][0]
        self.assertEqual(cols['missing'], 1)
        # La société ne peut ni déclarer ni décider.
        self.assertEqual(self.mutate(self.company_user, P + f'/{self.did}/incidents', dict(kind='extra', tracking='X', note='n', confirmed=True)).status_code, 403)
        # CSV disponible côté société, montants inchangés.
        csv = self.company_user.get(P + f'/{self.did}/csv')
        self.assertEqual(csv.status_code, 200)
        self.assertIn('Manquant déclaré', csv.data.decode('utf-8-sig'))
        p = self.parcel_by_tracking(line['tracking'])
        self.assertEqual((p['amount'], p['fee']), (self.ps[1]['amount'], 25))


TINY_PNG_B64 = None


def key():
    return secrets.token_hex(16)


def setUpModule():
    global TINY_PNG_B64
    import base64, io
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (16, 16), (200, 40, 40)).save(buf, 'PNG')
    globals()['TINY_PNG_B64'] = base64.b64encode(buf.getvalue()).decode()


if __name__ == '__main__':
    unittest.main()
