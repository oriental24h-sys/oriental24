"""API partenaire : clés révocables, idempotence, tarifs client, pagination, débit."""
import re, secrets, unittest
import partner_api
import test_client_types as types

system = types.system


class PartnerApiTests(unittest.TestCase):
    data = types.ClientTypesTests.data
    mutate = types.ClientTypesTests.mutate
    make_account = types.ClientTypesTests.make_account

    def setUp(self):
        partner_api._rate.clear()  # limiteur en mémoire : chaque test part d'un quota plein
        types.ClientTypesTests.setUp(self)
        r = self.mutate(self.admin, '/api/users',
                        dict(role='client', name='TransHelios', email='helios@example.test', password='Oriental24!Demo',
                             phone='0600000000', company='TransHelios Express', client_type='societe_livraison'))
        self.assertEqual(r.status_code, 200, r.json)
        self.cid = r.json['id']

    def key(self, client_id=None, label='Intégration ERP test'):
        r = self.mutate(self.admin, '/api/partner-api-keys', {'client_id': client_id or self.cid, 'label': label})
        self.assertEqual(r.status_code, 200, r.json)
        return r.json

    def api(self, key=None, method='get', url='/api/partner/v1/cities', **kwargs):
        headers = kwargs.pop('headers', {})
        if key is not None:
            headers['Authorization'] = 'Bearer ' + key
        return getattr(system.app.test_client(), method)(url, headers=headers, **kwargs)

    def idem(self):
        return 'IDEM-' + secrets.token_hex(12)

    # ------------------------------------------------------------------
    def test_key_lifecycle_admin_only_single_active_and_revocable(self):
        # Un client ne gère pas les clés.
        self.assertEqual(self.client.post('/api/partner-api-keys', json={}).status_code, 403)
        self.assertEqual(self.client.get('/api/partner-api-keys').status_code, 403)
        # Création : la clé complète n'est renvoyée qu'une fois, format imposé.
        k = self.key()
        self.assertTrue(re.fullmatch(r'O24K-[0-9a-f]{32}', k['key']), k)
        # Une société vendeur n'est pas éligible.
        self.assertEqual(self.mutate(self.admin, '/api/partner-api-keys', {'client_id': 2, 'label': 'x'}).status_code, 404)
        # Une seule clé active par société.
        self.assertEqual(self.mutate(self.admin, '/api/partner-api-keys',
                                     {'client_id': self.cid, 'label': 'autre'}).status_code, 409)
        # La liste ne contient jamais le secret ni l'empreinte.
        rows = self.admin.get('/api/partner-api-keys').json['rows']
        self.assertEqual(len(rows), 1)
        self.assertNotIn('key', rows[0])
        self.assertNotIn('key_hash', rows[0])
        # La clé fonctionne ; mauvaise clé et format refusés.
        self.assertEqual(self.api(key=k['key']).status_code, 200)
        self.assertEqual(self.api(key='O24K-' + '0' * 32).status_code, 401)
        self.assertEqual(self.api().status_code, 401)
        self.assertIn('O24K', self.api().json['error'])
        # Révocation : idempotente, puis la clé est morte.
        r = self.mutate(self.admin, f"/api/partner-api-keys/{rows[0]['id']}/revoke", {})
        self.assertEqual((r.status_code, r.json['changed']), (200, True))
        self.assertEqual(self.mutate(self.admin, f"/api/partner-api-keys/{rows[0]['id']}/revoke", {}).json['changed'], False)
        self.assertEqual(self.api(key=k['key']).status_code, 401)
        # Une nouvelle clé peut être créée après révocation.
        self.assertTrue(self.key()['key'])

    # ------------------------------------------------------------------
    def test_parcel_create_idempotency_tracking_scope_and_client_tariffs(self):
        k = self.key()
        # Tarif spécifique société sur Oujda : appliqué aux créations API (nouveaux colis uniquement).
        self.assertEqual(self.mutate(self.admin, f'/api/clients/{self.cid}/tariffs/1',
                                     {'fee': 21.0, 'return_fee': 8.0}, 'put').status_code, 200)
        cities = self.api(key=k['key']).json['cities']
        oujda = next(c for c in cities if c['name'] == 'Oujda')
        self.assertEqual((oujda['fee'], oujda['return_fee']), (21.0, 8.0))
        # Idempotency-Key obligatoire.
        payload = dict(tracking='HX-1000', recipient='Lina', phone='0611223344', address='Bd Zerktouni',
                       city='Oujda', amount=250.0, product='Robe')
        r = self.api(key=k['key'], method='post', url='/api/partner/v1/parcels', json=payload)
        self.assertEqual(r.status_code, 400)
        self.assertIn('Idempotency-Key', r.json['error'])
        # Création conforme : tarifs du contrat, tracking conservé (société = code maison).
        idem = self.idem()
        r = self.api(key=k['key'], method='post', url='/api/partner/v1/parcels',
                     json=payload, headers={'Idempotency-Key': idem})
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual((r.json['tracking'], r.json['status']), ('HX-1000', 'Créé'))
        self.assertEqual((r.json['fee'], r.json['return_fee']), (21.0, 8.0))
        # Rejouer la même clé renvoie le même résultat sans dupliquer.
        again = self.api(key=k['key'], method='post', url='/api/partner/v1/parcels',
                         json=payload, headers={'Idempotency-Key': idem})
        self.assertEqual((again.status_code, again.json['id'], again.json['replayed']), (201, r.json['id'], True))
        other = dict(payload, recipient='Autre')
        conflict = self.api(key=k['key'], method='post', url='/api/partner/v1/parcels',
                            json=other, headers={'Idempotency-Key': idem})
        self.assertEqual(conflict.status_code, 409)
        # Doublon de tracking chez la même société : refusé explicite.
        dup = self.api(key=k['key'], method='post', url='/api/partner/v1/parcels',
                       json=dict(payload, recipient='Dup'), headers={'Idempotency-Key': self.idem()})
        self.assertEqual(dup.status_code, 409)
        self.assertIn('société', dup.json['error'])
        self.assertEqual(len([p for p in self.data(self.admin)['parcels'] if p['tracking'] == 'HX-1000']), 1)
        # Consultation unitaire avec historique des événements.
        one = self.api(key=k['key'], url='/api/partner/v1/parcels/hx-1000')
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json['tracking'], 'HX-1000')
        self.assertIn('clé', one.json['events'][0]['note'])
        self.assertEqual(self.api(key=k['key'], url='/api/partner/v1/parcels/ABSENT').status_code, 404)

    # ------------------------------------------------------------------
    def test_list_pagination_filters_and_rate_limit(self):
        k = self.key()
        for n in range(3):
            self.assertEqual(self.api(key=k['key'], method='post', url='/api/partner/v1/parcels',
                     json=dict(tracking=f'HX-20{n:02d}', recipient='R', phone='0611223344', address='Rue', city='Oujda',
                               amount=100.0), headers={'Idempotency-Key': self.idem()}).status_code, 201)
        # Filtres stricts.
        self.assertEqual(self.api(key=k['key'], url='/api/partner/v1/parcels?updated_since=hier').status_code, 400)
        self.assertEqual(self.api(key=k['key'], url='/api/partner/v1/parcels?size=200').status_code, 400)
        self.assertEqual(self.api(key=k['key'], url='/api/partner/v1/parcels?page=0').status_code, 400)
        rows = self.api(key=k['key'], url='/api/partner/v1/parcels?size=50').json
        self.assertEqual(rows['total'], 3)
        since = rows['rows'][0]['updated_at']
        self.assertEqual(self.api(key=k['key'], url=f'/api/partner/v1/parcels?updated_since={since}&size=50').json['total'], 0)
        # En-tête anti-cache.
        self.assertIn('no-store', self.api(key=k['key'], url='/api/partner/v1/parcels?size=50').headers.get('Cache-Control', ''))
        # Plafond de débit : 120 requêtes/minute par clé (déjà ~10 consommées ci-dessus).
        last = None
        for _ in range(115):
            last = self.api(key=k['key'])
        self.assertEqual(last.status_code, 403)
        self.assertIn('indisponible', last.json['error'])


if __name__ == '__main__':
    unittest.main()
