import unittest,base64,io,secrets
from PIL import Image
import test_app as f
import test_driver_finance as finance

class ParcelClaimTests(unittest.TestCase):
    setUp=f.PlatformTests.setUp
    data=f.PlatformTests.data
    mutate=f.PlatformTests.mutate
    new_parcel=f.PlatformTests.new_parcel
    parallel=finance.DriverFinanceTests.parallel
    def payload(self,**kw):
        d=dict(subject='Question concernant la livraison',category='Autre',body='Description de test',priority='Normale',request_key=secrets.token_hex(16),attachments=[]);d.update(kw);return d
    def create(self,p,d=None,client=None):return self.mutate(client or self.admin,f'/api/logistics/parcels/{p["id"]}/tickets',d or self.payload())
    def file(self,raw=b'%PDF-1.4\nTest fictif\n%%EOF',name='preuve.pdf'):return dict(name=name,content=base64.b64encode(raw).decode())
    def image(self):
        b=io.BytesIO();Image.new('RGB',(10,10),'orange').save(b,format='PNG');return self.file(b.getvalue(),'photo.png')
    def count(self):
        with f.system.conn() as c:return tuple(c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['tickets','messages','ops_ticket_links','claim_attachments','claim_requests','ops_notifications'])
    def test_link_category_attachment_and_parcel_unchanged(self):
        p=self.new_parcel();url='/api/parcels/'+str(p['id']);before=self.admin.get(url).json
        d=self.payload(category='Retour',attachments=[self.file(),self.image()]);r=self.create(p,d);self.assertEqual(r.status_code,200,r.json);tid=r.json['id'];detail=self.admin.get('/api/tickets/'+str(tid)).json
        self.assertEqual(detail['ticket']['parcel_id'],p['id']);self.assertEqual(detail['ticket']['category'],'Retour');self.assertEqual(detail['messages'][0]['body'],d['body']);self.assertEqual(len(detail['attachments']),2);self.assertNotIn('content',detail['attachments'][0]);self.assertEqual(detail['attachments'][1]['mime'],'image/jpeg');self.assertTrue(detail['attachments'][1]['name'].endswith('.jpg'));self.assertEqual(self.admin.get(url).json,before)
    def test_permissions_scope_and_csrf(self):
        p=self.new_parcel();url=f'/api/logistics/parcels/{p["id"]}/tickets'
        self.assertEqual(self.admin.post(url,json=self.payload()).status_code,403);self.assertEqual(f.system.app.test_client().post(url,json=self.payload()).status_code,401);self.assertEqual(self.create(p,client=self.driver).status_code,404)
        other=next(x for x in self.data(self.admin)['parcels'] if x['client_id']!=2);self.assertEqual(self.create(other,client=self.client).status_code,404)
        self.assertEqual(self.create(p,client=self.client).status_code,200);self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(driver_id=3),'patch');self.assertEqual(self.create(p,client=self.driver).status_code,200)
        self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(driver_id=None),'patch');self.assertEqual(self.create(p,client=self.driver).status_code,404)
    def test_download_private_and_safe_headers(self):
        p=self.new_parcel();tid=self.create(p,self.payload(attachments=[self.file(name='../../preuve.html')]),self.client).json['id'];a=self.client.get('/api/tickets/'+str(tid)).json['attachments'][0];url='/api/claim-attachments/'+str(a['id'])
        for user in [self.client,self.admin]:
            r=user.get(url);self.assertEqual(r.status_code,200);self.assertEqual(r.mimetype,'application/pdf');self.assertIn('attachment;',r.headers['Content-Disposition']);self.assertIn('no-store',r.headers['Cache-Control']);self.assertEqual(r.headers['X-Content-Type-Options'],'nosniff');self.assertNotIn('../',r.headers['Content-Disposition'])
        self.assertEqual(self.driver.get(url).status_code,404);self.assertEqual(f.system.app.test_client().get(url).status_code,401);self.assertEqual(self.driver.get('/api/tickets/'+str(tid)).status_code,404)
    def test_validations_rollback_no_partial_ticket(self):
        p=self.new_parcel();before=self.count()
        bad=[dict(subject=' '),dict(subject=None),dict(subject='x'*181),dict(body=''),dict(body='a'*3001),dict(category='Inconnue'),dict(priority='Urgent'),dict(request_key='short'),dict(attachments={}),dict(attachments=[self.file()]*4),dict(attachments=[self.file(b'<script>x</script>','x.png')]),dict(attachments=[{'name':'x.pdf','content':'!!!'}]),dict(attachments=[self.file(),self.file(b'bad','other.pdf')]),dict(attachments=[self.file(name='...')]),dict(attachments=[self.file(b'a'*1048577)])]
        for patch in bad:
            r=self.create(p,self.payload(**patch));self.assertEqual(r.status_code,400,(patch.keys(),r.json));self.assertEqual(self.count(),before)
    def test_idempotence_conflict_and_concurrent_submit(self):
        p=self.new_parcel();d=self.payload(attachments=[self.image()]);r=self.create(p,d);self.assertEqual(r.status_code,200);after=self.count();r2=self.create(p,d);self.assertEqual(r2.json['id'],r.json['id']);self.assertTrue(r2.json['already_created']);self.assertEqual(self.count(),after)
        self.assertEqual(self.create(p,{**d,'subject':'Sujet différent'}).status_code,409);self.assertEqual(self.count(),after)
        d=self.payload();url=f'/api/logistics/parcels/{p["id"]}/tickets';results=self.parallel([('post',url,d),('post',url,d)]);self.assertEqual([r.status_code for r in results],[200,200]);self.assertEqual(results[0].json['id'],results[1].json['id'])
    def test_locked_parcel_can_have_claim_without_unlocking(self):
        p=self.new_parcel();self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(status='Livré'),'patch');self.mutate(self.admin,'/api/invoices',dict(client_id=2));before=self.admin.get('/api/parcels/'+str(p['id'])).json;self.assertTrue(before['parcel']['invoice_id']);self.assertEqual(self.create(p).status_code,200);self.assertEqual(self.admin.get('/api/parcels/'+str(p['id'])).json,before)
    def test_legacy_linked_ticket_still_works(self):
        p=self.new_parcel();r=self.create(p,dict(subject='Ancien formulaire',body='Description',priority='Haute'));self.assertEqual(r.status_code,200);t=self.admin.get('/api/tickets/'+str(r.json['id'])).json;self.assertEqual(t['ticket']['category'],'Livraison');self.assertEqual(t['ticket']['priority'],'Haute');self.assertEqual(t['attachments'],[])

if __name__=='__main__':unittest.main()
