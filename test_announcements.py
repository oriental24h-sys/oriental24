import unittest
import test_app as f
import test_driver_finance as finance

class AnnouncementTests(unittest.TestCase):
    setUp=f.PlatformTests.setUp
    data=f.PlatformTests.data
    mutate=f.PlatformTests.mutate
    parallel=finance.DriverFinanceTests.parallel
    def payload(self,**kw):
        d=dict(title='Information de test',body='Message fictif',kind='info',audience=['admin','client','livreur'],active=True,position=10,link_kind='none',link_label='',link_url='');d.update(kw);return d
    def create(self,**kw):return self.mutate(self.admin,'/api/announcements/manage',self.payload(**kw))
    def test_scope_and_drafts_not_sent_to_other_roles(self):
        self.create(title='Client seulement',audience=['client']);self.create(title='Admin seulement',audience=['admin']);self.create(title='Brouillon privé',active=False);self.create(title='Livreur seulement',audience=['livreur'])
        for client,title in [(self.admin,'Admin seulement'),(self.client,'Client seulement'),(self.driver,'Livreur seulement')]:
            data=client.get('/api/announcements').json;self.assertEqual([n['title'] for n in data],[title]);self.assertNotIn('updated_by',data[0]);self.assertNotIn('audience',data[0])
        self.assertEqual(len(self.admin.get('/api/announcements/manage').json),4)
    def test_authentication_admin_csrf(self):
        self.assertEqual(f.system.app.test_client().get('/api/announcements').status_code,401)
        self.assertEqual(self.admin.post('/api/announcements/manage',json=self.payload()).status_code,403)
        for client in [self.client,self.driver]:
            self.assertEqual(client.get('/api/announcements/manage').status_code,403);self.assertEqual(self.mutate(client,'/api/announcements/manage',self.payload()).status_code,403);self.assertEqual(self.mutate(client,'/api/announcements/1',self.payload(revision=1),'patch').status_code,403)
    def test_revision_noop_audit_and_deactivation(self):
        r=self.create();aid=r.json['id'];url='/api/announcements/'+str(aid);r=self.mutate(self.admin,url,self.payload(revision=1),'patch');self.assertFalse(r.json['changed'])
        r=self.mutate(self.admin,url,self.payload(revision=1,active=False),'patch');self.assertEqual(r.json['revision'],2);self.assertEqual(self.client.get('/api/announcements').json,[])
        self.assertEqual(self.mutate(self.admin,url,self.payload(revision=1),'patch').status_code,409)
        with f.system.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM announcement_audit').fetchone()[0],2)
    def test_links_only_safe_https_or_authorized_template(self):
        for url in ['javascript:alert(1)','//example.test','http://example.test','https://u:p@example.test','https://example.test/\nfoo','https://example.test\\evil','https://example.test:bad']:
            self.assertEqual(self.create(link_kind='url',link_label='Lien',link_url=url).status_code,400,url)
        r=self.create(link_kind='url',link_label='Documentation',link_url='https://example.test/info?x=1&y=2');self.assertEqual(r.status_code,200)
        self.assertEqual(self.create(link_kind='template',link_label='Modèle').status_code,400)
        self.assertEqual(self.create(link_kind='template',link_label='Modèle',audience=['admin','client']).status_code,200);self.assertEqual(self.driver.get('/api/imports/template.xlsx').status_code,403)
    def test_payload_types_and_size_limits(self):
        bad=[dict(title=''),dict(body=None),dict(title='a'*121),dict(body='a'*901),dict(audience=[]),dict(audience=['admin','admin']),dict(audience=['guest']),dict(position=True),dict(position=100),dict(active=1),dict(kind='html'),dict(link_kind='url',link_label='',link_url='https://example.test')]
        for kw in bad:self.assertEqual(self.create(**kw).status_code,400,kw)
        for d in [None,[],{},self.payload(extra='x')]:self.assertEqual(self.mutate(self.admin,'/api/announcements/manage',d).status_code,400)
        self.assertEqual(self.admin.get('/api/announcements/manage').json,[])
    def test_order_cap_and_concurrent_corrections(self):
        aid=self.create(title='Second',position=20).json['id'];self.create(title='Premier',position=1)
        self.assertEqual([n['title'] for n in self.client.get('/api/announcements').json],['Premier','Second'])
        rows=self.parallel([('patch','/api/announcements/'+str(aid),self.payload(revision=1,title=t)) for t in ['A','B']]);self.assertEqual(sorted(r.status_code for r in rows),[200,409])
        for _ in range(8):self.assertEqual(self.create().status_code,200)
        self.assertEqual(self.create().status_code,400);self.assertEqual(self.create(active=False).status_code,200)
    def test_no_mutation_of_operational_tables(self):
        tables=['parcels','events','cities','invoices','tickets','messages','ops_documents','users']
        with f.system.conn() as c:before={t:[tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY 1')] for t in tables}
        self.create(kind='banner',title='إعلان تجريبي',body='<script>not executable as text</script>')
        with f.system.conn() as c:
            for t in tables:self.assertEqual(before[t],[tuple(r) for r in c.execute('SELECT * FROM '+t+' ORDER BY 1')])

if __name__=='__main__':unittest.main()
