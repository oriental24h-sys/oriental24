"""Atomic logistics, notifications, documents, historical metrics and stock preparation."""
import unittest,secrets
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import test_app as fixtures
import test_driver_finance as finance_fixtures
system=fixtures.system
L='/api/logistics'
F='/api/fulfillment/orders'

class LogisticsTests(unittest.TestCase):
    data=fixtures.PlatformTests.data
    mutate=fixtures.PlatformTests.mutate
    new_parcel=fixtures.PlatformTests.new_parcel
    parallel=finance_fixtures.DriverFinanceTests.parallel
    def setUp(self):
        fixtures.PlatformTests.setUp(self)
        self.hubs=[]
        for name,cid in [('Hub de test A',1),('Hub de test B',2)]:
            r=self.mutate(self.admin,L+'/hubs',dict(name=name,city_id=cid,address='Adresse test'))
            self.assertEqual(r.status_code,200,r.json);self.hubs.append(r.json['id'])
    def p(self,status='Créé',driver=3):
        p=self.new_parcel();r=self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(driver_id=driver,status=status),'patch');self.assertEqual(r.status_code,200,r.json)
        return self.admin.get('/api/parcels/'+str(p['id'])).json['parcel']
    def doc(self,parcels,kind='pickup',**kw):
        d=dict(kind=kind,parcel_ids=[p['id'] for p in parcels],client_id=2,driver_id=3,source_hub_id=self.hubs[0],destination_hub_id=self.hubs[1],note='Document de test');d.update(kw)
        return self.mutate(self.admin,L+'/documents',d)
    def action(self,did,action,**kw):return self.mutate(self.admin,L+f'/documents/{did}/{action}',kw)
    def attempt(self,p,outcome='Livré',**kw):
        d=dict(outcome=outcome,revision=p['ops_revision'],request_key=secrets.token_hex(16),receiver='Réceptionnaire test',collected_amount=p['amount']);d.update(kw)
        return self.mutate(self.driver,L+f'/parcels/{p["id"]}/attempts',d)
    def order_data(self,qty=3,**kw):
        d=dict(items=[dict(product_id=1,quantity=qty)],recipient='Destinataire stock',phone='0600000000',address='Adresse fictive',city_id=1,amount='199.90',request_key=secrets.token_hex(16));d.update(kw);return d
    def reserve(self,qty=3,**kw):return self.mutate(self.client,F,self.order_data(qty,**kw))
    def stock(self):return next(p for p in self.client.get('/api/products').json if p['id']==1)
    def test_config_hub_and_reason_access(self):
        self.assertEqual(len(self.admin.get(L+'/config').json['hubs']),2)
        self.assertEqual(self.mutate(self.client,L+'/hubs',{}).status_code,403)
        self.assertEqual(self.mutate(self.admin,L+'/reasons',dict(code='travel',label='Destinataire en voyage',active=True)).status_code,200)
        self.assertEqual(self.mutate(self.admin,L+'/reasons',dict(code='bad code',label='Test')).status_code,400)
    def test_future_appointment_required_even_on_legacy_patch(self):
        p=self.p('En livraison')
        self.assertEqual(self.mutate(self.driver,'/api/parcels/'+str(p['id']),dict(status='Programmé'),'patch').status_code,400)
        self.assertEqual(self.attempt(p,'Programmé',reason_code='appointment',next_attempt_at='2000-01-01T10:00').status_code,400)
        future=(datetime.now(ZoneInfo('Africa/Casablanca'))+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        self.assertEqual(self.attempt(p,'Programmé',reason_code='appointment',next_attempt_at=future).status_code,200)
        data=self.driver.get(L+f'/parcels/{p["id"]}').json;self.assertTrue(data['parcel']['next_attempt_at'].startswith(future));self.assertEqual(data['attempts'][0]['reason_label'],'Rendez-vous demandé')
    def test_attempt_exactly_once_precision_and_stale_revision(self):
        p=self.p('En livraison');key=secrets.token_hex(16)
        self.assertEqual(self.attempt(p,collected_amount=1).status_code,400)
        a=self.attempt(p,request_key=key);b=self.attempt(p,request_key=key)
        self.assertEqual(a.status_code,200,a.json);self.assertEqual(a.json['id'],b.json['id']);self.assertTrue(b.json['already_recorded'])
        self.assertEqual(self.attempt(p,request_key=key,receiver='Autre').status_code,409)
        self.assertEqual(self.attempt(p).status_code,409)
        self.assertEqual(len(self.driver.get(L+f'/parcels/{p["id"]}').json['attempts']),1)
    def test_attempt_role_and_financial_lock(self):
        p=self.p('En livraison');self.assertEqual(self.mutate(self.client,L+f'/parcels/{p["id"]}/attempts',{}).status_code,403)
        other=self.p('En livraison',5);self.assertEqual(self.attempt(other).status_code,404)
        self.attempt(p)
        r=self.mutate(self.admin,'/api/invoices',dict(client_id=2));self.assertEqual(r.status_code,200)
        self.assertEqual(self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(status='En livraison'),'patch').status_code,400)
    def test_reasons_are_snapshotted(self):
        p=self.p('En livraison');self.assertEqual(self.attempt(p,'Refusé',reason_code='refused').status_code,200)
        self.mutate(self.admin,L+'/reasons',dict(code='refused',label='Nouveau libellé',active=False))
        a=self.driver.get(L+f'/parcels/{p["id"]}').json['attempts'][0];self.assertEqual(a['reason_label'],'Refus du destinataire')
        p=self.p('En livraison');self.assertEqual(self.attempt(p,'Refusé',reason_code='refused').status_code,400)
    def test_partial_receipts_duplicates_and_completion(self):
        a,b=self.p(),self.p();r=self.doc([a,b]);self.assertEqual(r.status_code,200,r.json);did=r.json['id']
        self.assertEqual(self.action(did,'receive',tracking=a['tracking']).status_code,409)
        self.assertEqual(self.action(did,'dispatch',revision=1).status_code,200)
        self.assertEqual(self.action(did,'receive',tracking=a['tracking']).status_code,200)
        d=self.admin.get(L+f'/documents/{did}').json;self.assertEqual((d['status'],d['received']),('Partiellement reçu',1))
        self.assertTrue(self.action(did,'receive',tracking=a['tracking']).json['already_received'])
        self.assertEqual(self.action(did,'receive',tracking='O24-UNKNOWN').status_code,404)
        self.assertEqual(self.action(did,'cancel',revision=d['revision'],reason='Test').status_code,409)
        self.action(did,'receive',tracking=b['tracking'])
        d=self.admin.get(L+f'/documents/{did}').json;self.assertEqual((d['status'],d['received']),('Reçu',2));self.assertTrue(d['qr'].startswith('data:image/png;base64,'))
        pa=self.admin.get('/api/parcels/'+str(a['id'])).json['parcel'];self.assertEqual(pa['current_hub_id'],self.hubs[1]);self.assertEqual(pa['status'],'Au hub');self.assertFalse(pa['operations_locked'])
    def test_document_locks_old_endpoint_and_other_documents(self):
        p=self.p();did=self.doc([p]).json['id']
        for patch in [dict(driver_id=5),dict(status='Ramassé')]:self.assertEqual(self.mutate(self.admin,'/api/parcels/'+str(p['id']),patch,'patch').status_code,409)
        self.assertEqual(self.doc([p]).status_code,409)
        self.assertEqual(self.action(did,'cancel',revision=1,reason='Erreur préparation').status_code,200)
        self.assertEqual(self.doc([p]).status_code,200)
    def test_document_snapshot_scope_and_transfer_hub_validation(self):
        p=self.p('Au hub');r=self.doc([p],'transfer');self.assertEqual(r.status_code,200,r.json);did=r.json['id']
        self.assertEqual(self.client.get(L+f'/documents/{did}').status_code,404)
        self.assertEqual(self.driver.get(L+f'/documents/{did}').status_code,200)
        self.assertEqual(self.mutate(self.driver,L+f'/documents/{did}/dispatch',dict(revision=1)).status_code,403)
        self.mutate(self.admin,L+'/hubs/'+str(self.hubs[0]),dict(name='Hub renommé',address='Adresse',city_id=1,active=True),'patch')
        self.assertEqual(self.admin.get(L+f'/documents/{did}').json['source_name'],'Hub de test A')
        p2=self.p('Au hub');self.assertEqual(self.doc([p2],'transfer',destination_hub_id=self.hubs[0]).status_code,400)
    def test_return_document_does_not_change_money_or_status(self):
        p=self.p('Retourné');self.mutate(self.admin,'/api/invoices',dict(client_id=2));r=self.doc([p],'return');self.assertEqual(r.status_code,200,r.json)
        did=r.json['id'];self.action(did,'dispatch',revision=1);self.action(did,'receive',tracking=p['tracking'])
        after=self.admin.get('/api/parcels/'+str(p['id'])).json['parcel'];self.assertEqual(after['status'],'Retourné');self.assertEqual(after['amount'],p['amount']);self.assertEqual(after['updated_at'],p['updated_at'])
    def test_parallel_document_creation_one_active(self):
        p=self.p();d=dict(kind='pickup',client_id=2,driver_id=3,destination_hub_id=self.hubs[0],parcel_ids=[p['id']])
        rs=self.parallel([('post',L+'/documents',d),('post',L+'/documents',d)])
        self.assertEqual(sorted(r.status_code for r in rs),[200,409])
    def test_parallel_receipt_exactly_once(self):
        p=self.p();did=self.doc([p]).json['id'];self.action(did,'dispatch',revision=1)
        task=('post',L+f'/documents/{did}/receive',dict(tracking=p['tracking']))
        rs=self.parallel([task,task]);self.assertEqual([r.status_code for r in rs],[200,200]);self.assertEqual(sum(r.json['already_received'] for r in rs),1)
    def test_bulk_assignment_preview_confirm_stale_and_replay(self):
        a,b=self.p(),self.p();d=dict(driver_id=5,parcel_ids=[a['id'],b['id']]);p=self.mutate(self.admin,L+'/assignments/preview',d).json
        self.mutate(self.admin,'/api/parcels/'+str(b['id']),dict(status='Ramassé'),'patch')
        self.assertEqual(self.mutate(self.admin,L+'/assignments/'+p['token']+'/confirm',{}).status_code,409)
        self.assertEqual(self.admin.get('/api/parcels/'+str(a['id'])).json['parcel']['driver_id'],3)
        p=self.mutate(self.admin,L+'/assignments/preview',d).json
        url=L+'/assignments/'+p['token']+'/confirm';self.assertEqual(self.mutate(self.admin,url,{}).status_code,200);self.assertTrue(self.mutate(self.admin,url,{}).json['already_created'])
    def test_notifications_private_and_read(self):
        p=self.p('En livraison');self.attempt(p)
        notices=self.client.get(L+'/notifications').json;self.assertGreater(notices['unread'],0)
        self.assertTrue(all(n['user_id']==2 for n in notices['items']))
        self.mutate(self.client,L+'/notifications',dict(all=True),'patch');self.assertEqual(self.client.get(L+'/notifications').json['unread'],0)
    def test_linked_ticket_priority_owner_response_and_scope(self):
        p=self.p();r=self.mutate(self.client,L+f'/parcels/{p["id"]}/tickets',dict(subject='Question',body='Test',priority='Haute'));self.assertEqual(r.status_code,200,r.json);tid=r.json['id']
        self.assertEqual(self.driver.get('/api/tickets/'+str(tid)).status_code,404)
        self.assertEqual(self.mutate(self.admin,L+f'/tickets/{tid}',dict(priority='Normale',assigned_to=1),'patch').status_code,200)
        self.mutate(self.admin,'/api/tickets/'+str(tid),dict(body='Réponse test'))
        t=self.client.get('/api/tickets/'+str(tid)).json['ticket'];self.assertEqual(t['tracking'],p['tracking']);self.assertTrue(t['first_response_at']);self.assertEqual(t['assigned_to'],1)
    def test_analytics_no_fabricated_history_and_scoped_metrics(self):
        data=self.admin.get(L+'/analytics').json;self.assertTrue(all(d['attempts']==0 and d['assignment_events']==0 for d in data['drivers']))
        p=self.p('En livraison');self.attempt(p);d=next(d for d in self.admin.get(L+'/analytics').json['drivers'] if d['id']==3)
        self.assertEqual((d['assignment_events'],d['attempts'],d['delivered_attempts']),(1,1,1))
        self.assertEqual(self.client.get(L+'/analytics').status_code,403)
        self.assertEqual(self.admin.get(L+'/analytics?from=2026-12-01&to=2026-01-01').status_code,400)
    def test_reservation_available_stock_and_movement_guards(self):
        r=self.reserve(20);self.assertEqual(r.status_code,200,r.json);s=self.stock();self.assertEqual((s['quantity'],s['reserved'],s['available']),(24,20,4))
        self.assertEqual(self.reserve(5).status_code,409)
        self.assertEqual(self.mutate(self.admin,'/api/products/1/movements',dict(delta=-5,note='Test')).status_code,400)
        self.assertEqual(self.mutate(self.client,'/api/stock/requests',dict(product_id=1,kind='Sortie',quantity=5,reason='Test')).status_code,400)
    def test_reservation_cancellation_and_scope(self):
        oid=self.reserve().json['id'];self.assertEqual(self.mutate(self.client,F+f'/{oid}/cancel',dict(reason='Test')).status_code,200)
        self.assertEqual(self.stock()['available'],24)
        self.assertEqual(self.mutate(self.client,F+f'/{oid}/cancel',dict(reason='Test')).status_code,409)
        self.assertEqual(self.driver.get(F).status_code,403)
    def test_reservation_request_replay_and_input_validation(self):
        d=self.order_data();a=self.mutate(self.client,F,d);b=self.mutate(self.client,F,d);self.assertEqual(a.json['id'],b.json['id']);self.assertTrue(b.json['already_created'])
        d['amount']='200';self.assertEqual(self.mutate(self.client,F,d).status_code,409)
        self.assertEqual(self.reserve(items=[dict(product_id=1,quantity=1),dict(product_id=1,quantity=1)]).status_code,400)
    def test_preparation_creates_exact_parcel_and_debits_once(self):
        oid=self.reserve(3).json['id'];url=F+f'/{oid}/ship';d=dict(hub_id=self.hubs[0],checked=True)
        self.assertEqual(self.mutate(self.client,url,d).status_code,403)
        self.assertEqual(self.mutate(self.admin,url,d).status_code,200)
        self.assertEqual(self.mutate(self.admin,url,d).status_code,409)
        o=self.client.get(F+'/'+str(oid)).json;self.assertEqual(o['status'],'Préparé');self.assertTrue(o['tracking'].startswith('O24-'))
        p=self.client.get('/api/parcels/'+str(o['parcel_id'])).json['parcel'];self.assertEqual(p['status'],'Au hub');self.assertEqual(p['current_hub_id'],self.hubs[0]);self.assertEqual(p['amount'],199.9)
        s=self.stock();self.assertEqual((s['quantity'],s['available'],s['reserved']),(21,21,0))
    def test_restock_inspection_exactly_once(self):
        oid=self.reserve(3).json['id'];self.mutate(self.admin,F+f'/{oid}/ship',dict(hub_id=self.hubs[0],checked=True));o=self.client.get(F+'/'+str(oid)).json
        d=dict(checked=True,reason='Toutes unités vérifiées')
        self.assertEqual(self.mutate(self.admin,F+f'/{oid}/restock',d).status_code,400)
        self.mutate(self.admin,'/api/parcels/'+str(o['parcel_id']),dict(status='Retourné'),'patch')
        self.assertEqual(self.mutate(self.admin,F+f'/{oid}/restock',d).status_code,200)
        self.assertEqual(self.mutate(self.admin,F+f'/{oid}/restock',d).status_code,409);self.assertEqual(self.stock()['quantity'],24)
    def test_parallel_reservations_do_not_oversell(self):
        tasks=[('post',F,self.order_data(20,client_id=2)) for _ in range(2)];r=self.parallel(tasks)
        self.assertEqual(sorted(x.status_code for x in r),[200,409]);self.assertEqual(self.stock()['available'],4)
    def test_reservations_protect_pending_stock_request_approval(self):
        req=self.mutate(self.client,'/api/stock/requests',dict(product_id=1,kind='Sortie',quantity=20,reason='Test')).json['id']
        self.reserve(20)
        self.assertEqual(self.mutate(self.admin,'/api/stock/requests/'+str(req),dict(status='Validée'),'patch').status_code,409)
        self.assertEqual(self.stock()['quantity'],24)
    def test_new_routes_csrf(self):
        for url in [L+'/hubs',L+'/documents',F]:self.assertEqual(self.admin.post(url,json={}).status_code,403)
        self.assertEqual(system.app.test_client().get(L+'/config').status_code,401)

    def test_historical_hub_activity_uses_real_dated_events(self):
        p=self.p('Au hub');did=self.doc([p],'transfer').json['id'];self.action(did,'dispatch',revision=1);self.action(did,'receive',tracking=p['tracking']);self.action(did,'receive',tracking=p['tracking'])
        a=self.admin.get(L+'/analytics').json['hub_activity'];self.assertEqual(next(h for h in a if h['id']==self.hubs[0])['departed'],1);self.assertEqual(next(h for h in a if h['id']==self.hubs[1])['received'],1)
        old=self.admin.get(L+'/analytics?from=2000-01-01&to=2000-01-31').json;self.assertTrue(all(h['received']==0 and h['departed']==0 for h in old['hub_activity']))
    def test_stock_analytics_scope_and_physical_movement_totals(self):
        oid=self.reserve(3).json['id'];self.mutate(self.admin,F+f'/{oid}/ship',dict(hub_id=self.hubs[0],checked=True))
        rows=self.client.get('/api/fulfillment/analytics').json['products'];self.assertTrue(all(p['client_id']==2 for p in rows));p=next(p for p in rows if p['id']==1);self.assertEqual((p['prepared'],p['outgoing'],p['available']),(3,3,21))
        self.assertEqual(self.driver.get('/api/fulfillment/analytics').status_code,403)
        self.assertEqual(self.client.get('/api/fulfillment/analytics?from=2026-12-01&to=2026-01-01').status_code,400)

if __name__=='__main__':unittest.main()
