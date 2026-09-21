"""Functional API tests. Uses isolated temporary databases, never the demo database."""
import os, tempfile, shutil, unittest
TEMP = tempfile.mkdtemp(prefix='oriental24-tests-')
os.environ['DB_PATH'] = os.path.join(TEMP, 'seed.sqlite')
import app as system

class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.path=os.path.join(TEMP, self._testMethodName+'.sqlite')
        shutil.copyfile(os.environ['DB_PATH'],self.path)
        system.DB=self.path
        system.app.config['TESTING']=True
        self.admin,self.client,self.driver=[system.app.test_client() for _ in range(3)]
        for client,role in [(self.admin,'admin'),(self.client,'client'),(self.driver,'livreur')]:
            self.assertEqual(client.post('/api/login',json={'email':role+'@oriental24.ma','password':'Oriental24!Demo'}).status_code,200)
    def data(self,client):return client.get('/api/bootstrap').get_json()
    def mutate(self,client,url,data,method='post'):
        return getattr(client,method)(url,json=data,headers={'X-CSRF-Token':self.data(client)['csrf']})
    def new_parcel(self,**kwargs):
        d={'recipient':'Test Recipient','phone':'0600000000','address':'Test address','city_id':1,'amount':199.90,'product':'Test'}
        d.update(kwargs)
        r=self.mutate(self.client,'/api/parcels',d)
        self.assertEqual(r.status_code,200,r.get_json())
        return next(p for p in self.data(self.client)['parcels'] if p['tracking']==r.get_json()['tracking'])
    def test_authentication(self):
        self.assertEqual(system.app.test_client().get('/api/bootstrap').status_code,401)
        self.assertEqual(system.app.test_client().post('/api/login',json={'email':'admin@oriental24.ma','password':'wrong'}).status_code,401)
        self.assertEqual(self.admin.patch('/api/settings',json={'announcement':'x'}).status_code,403)
        self.assertEqual(self.mutate(self.client,'/api/settings',{'announcement':'x'},'patch').status_code,403)
    def test_data_isolation(self):
        ad,cl,dr=map(self.data,[self.admin,self.client,self.driver])
        self.assertEqual(len(ad['parcels']),48)
        self.assertTrue(all(p['client_id']==cl['user']['id'] for p in cl['parcels']))
        self.assertTrue(all(p['driver_id']==dr['user']['id'] for p in dr['parcels']))
        other=next(p for p in ad['parcels'] if p['client_id']!=cl['user']['id'])
        self.assertEqual(self.client.get('/api/parcels/'+str(other['id'])).status_code,404)
        self.assertEqual(cl['users'],[])
        self.assertEqual(self.mutate(self.driver,'/api/cities',{}).status_code,403)
    def test_city_expansion_and_tariffs(self):
        d={'name':'Fès','region':'Fès-Meknès','fee':39.5,'return_fee':12,'delivery':True,'pickup':False}
        self.assertEqual(self.mutate(self.admin,'/api/cities',d).status_code,200)
        c=next(c for c in self.data(self.admin)['cities'] if c['name']=='Fès')
        p=self.new_parcel(city_id=c['id']);self.assertEqual(p['fee'],39.5)
        d.update(fee=50,delivery=False)
        self.assertEqual(self.mutate(self.admin,'/api/cities/'+str(c['id']),d,'patch').status_code,200)
        self.assertEqual(self.client.get('/api/parcels/'+str(p['id'])).get_json()['parcel']['fee'],39.5)
        self.assertNotIn('Fès',[c['name'] for c in self.client.get('/api/public').get_json()['cities']])
        bad=self.mutate(self.client,'/api/parcels',{'city_id':c['id']})
        self.assertEqual(bad.status_code,400)
        self.assertEqual(self.mutate(self.client,'/api/pickups',{'city_id':c['id']}).status_code,400)
    def test_creation_validation(self):
        p=self.new_parcel();self.assertEqual(p['status'],'Créé')
        self.assertEqual(len(self.client.get('/api/parcels/'+str(p['id'])).get_json()['events']),1)
        for amount in [-1,'nan','infinity',1000001]:
            r=self.mutate(self.client,'/api/parcels',{'recipient':'Test','phone':'0600000000','address':'Test','city_id':1,'amount':amount})
            self.assertEqual(r.status_code,400)
        self.assertEqual(self.mutate(self.driver,'/api/parcels',{}).status_code,403)
    def test_assignment_and_driver_workflow(self):
        p=self.new_parcel();url='/api/parcels/'+str(p['id'])
        self.assertEqual(self.mutate(self.driver,url,{'status':'Ramassé'},'patch').status_code,404)
        self.assertEqual(self.mutate(self.admin,url,{'driver_id':3},'patch').status_code,200)
        self.assertEqual(self.mutate(self.driver,url,{'status':'Livré'},'patch').status_code,400)
        for s in ['Ramassé','Au hub','En livraison','Livré']:
            self.assertEqual(self.mutate(self.driver,url,{'status':s,'note':'Test transition'},'patch').status_code,200)
        self.assertEqual(self.mutate(self.driver,url,{'status':'Créé'},'patch').status_code,400)
        self.assertEqual(self.mutate(self.driver,url,{'driver_id':5},'patch').status_code,403)
    def test_invoicing_and_locking(self):
        r=self.mutate(self.admin,'/api/invoices',{'client_id':2})
        self.assertEqual(r.status_code,200,r.get_json())
        i=self.admin.get('/api/invoices').get_json()[0]
        d=self.admin.get('/api/invoices/'+str(i['id'])).get_json()
        expected_cod=sum(p['amount'] for p in d['parcels'] if p['status']=='Livré')
        expected_fees=sum(p['fee'] if p['status']=='Livré' else p['return_fee'] for p in d['parcels'])
        self.assertAlmostEqual(i['total'],expected_cod-expected_fees,2)
        self.assertEqual(self.mutate(self.admin,'/api/invoices',{'client_id':2}).status_code,400)
        pid=d['parcels'][0]['id']
        self.assertEqual(self.mutate(self.admin,'/api/parcels/'+str(pid),{'status':'Créé'},'patch').status_code,400)
        self.assertEqual(self.mutate(self.client,'/api/invoices/'+str(i['id']),{},'patch').status_code,403)
        self.assertEqual(self.mutate(self.admin,'/api/invoices/'+str(i['id']),{},'patch').status_code,200)
        self.assertEqual(self.client.get('/api/invoices/'+str(i['id'])).get_json()['invoice']['status'],'Réglée')
    def test_price_request_approval(self):
        p=self.new_parcel()
        self.assertEqual(self.mutate(self.client,'/api/requests',{'parcel_id':p['id'],'amount':149.5,'reason':'Correction'}).status_code,200)
        r=self.admin.get('/api/requests').get_json()[0]
        self.assertEqual(self.mutate(self.admin,'/api/requests/'+str(r['id']),{'status':'Acceptée'},'patch').status_code,200)
        self.assertEqual(self.client.get('/api/parcels/'+str(p['id'])).get_json()['parcel']['amount'],149.5)
        self.assertEqual(self.mutate(self.admin,'/api/requests/'+str(r['id']),{'status':'Acceptée'},'patch').status_code,400)
    def test_ticket_messages_and_permissions(self):
        self.assertEqual(self.mutate(self.client,'/api/tickets',{'subject':'Question','category':'Autre','body':'Bonjour'}).status_code,200)
        t=self.client.get('/api/tickets').get_json()[0]
        self.assertEqual(self.driver.get('/api/tickets/'+str(t['id'])).status_code,404)
        self.assertEqual(self.mutate(self.admin,'/api/tickets/'+str(t['id']),{'body':'Bonjour, voici notre réponse.'}).status_code,200)
        self.assertEqual(len(self.client.get('/api/tickets/'+str(t['id'])).get_json()['messages']),2)
        self.assertEqual(self.mutate(self.admin,'/api/tickets/'+str(t['id']),{'status':'Résolu'},'patch').status_code,200)
    def test_stock_movements(self):
        self.assertEqual(self.mutate(self.admin,'/api/products/1/movements',{'delta':-25,'note':'Test'}).status_code,400)
        self.assertEqual(self.mutate(self.client,'/api/products/1/movements',{'delta':10,'note':'Test'}).status_code,403)
        self.assertEqual(self.mutate(self.admin,'/api/products/1/movements',{'delta':-4,'note':'Sortie test'}).status_code,200)
        self.assertEqual(self.client.get('/api/products').get_json()[0]['quantity'],20)
        self.assertEqual(len(self.client.get('/api/products/1/movements').get_json()),1)
    def test_profile_transaction_rollback(self):
        u=self.data(self.client)['user']
        r=self.mutate(self.client,'/api/profile',{'name':'Changed','phone':'0600000000','company':'Test','password':'newstrongpassword','current_password':'wrong'},'patch')
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.data(self.client)['user']['name'],u['name'])
    def test_user_deactivation(self):
        u=self.data(self.admin)['users'][2]
        self.assertEqual(self.mutate(self.admin,'/api/users/3',{**u,'active':False},'patch').status_code,200)
        self.assertEqual(self.driver.get('/api/bootstrap').status_code,401)
    def test_export_scoping(self):
        r=self.client.get('/api/export');self.assertEqual(r.status_code,200)
        body=r.data.decode('utf-8-sig')
        self.assertIn('ORIENTAL24-colis.csv',r.headers['Content-Disposition'])
        for p in self.data(self.admin)['parcels']:
            self.assertEqual(p['tracking'] in body,p['client_id']==2)
    def test_registration_forces_client_role(self):
        guest=system.app.test_client()
        r=guest.post('/api/register',json={'name':'New Test','email':'new@example.test','company':'Test','phone':'0600000000','password':'StrongPass123!','role':'admin'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.data(guest)['user']['role'],'client')
        self.assertEqual(self.data(guest)['parcels'],[])
    def test_pallet_reception(self):
        self.assertEqual(self.mutate(self.admin,'/api/pallets',{'source':'Oujda','destination':'Berkane','transport':'Test','count':5}).status_code,200)
        p=self.admin.get('/api/pallets').get_json()[0]
        self.assertEqual(self.mutate(self.admin,'/api/pallets/'+str(p['id']),{},'patch').status_code,200)
        self.assertEqual(self.admin.get('/api/pallets').get_json()[0]['status'],'Réceptionnée')
        self.assertEqual(self.client.get('/api/pallets').status_code,403)

if __name__=='__main__':
    try: unittest.main(verbosity=2)
    finally: shutil.rmtree(TEMP,ignore_errors=True)
