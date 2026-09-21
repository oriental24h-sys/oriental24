import unittest,base64,io
from PIL import Image
import test_app as f
class AccountTests(unittest.TestCase):
    setUp=f.PlatformTests.setUp
    data=f.PlatformTests.data
    mutate=f.PlatformTests.mutate
    def dossier(self):return self.client.get('/api/account-dossiers/2').json
    def upload(self,raw=None,name='fictif.png',kind='Contrat'):
        if raw is None:
            b=io.BytesIO();Image.new('RGB',(20,20),'orange').save(b,format='PNG');raw=b.getvalue()
        return self.mutate(self.client,'/api/account-dossiers/2/documents',dict(name=name,kind=kind,content=base64.b64encode(raw).decode()))
    def fill(self):
        d=self.dossier();return self.mutate(self.client,'/api/account-dossiers/2',dict(revision=d['revision'],legal_name='Boutique fictive',billing_address='Adresse fictive',legal_id='TEST-ONLY'),'patch')
    def submit(self):return self.mutate(self.client,'/api/account-dossiers/2/submit',dict(revision=self.dossier()['revision']))
    def test_private_list_and_cross_account_scope(self):
        self.assertEqual([d['user_id'] for d in self.client.get('/api/account-dossiers').json],[2])
        self.assertEqual(self.driver.get('/api/account-dossiers/2').status_code,404)
        self.assertEqual(self.admin.get('/api/account-dossiers/2').status_code,200)
    def test_information_stale_update_and_required_fields(self):
        self.assertEqual(self.fill().status_code,200)
        self.assertEqual(self.mutate(self.client,'/api/account-dossiers/2',dict(revision=0,legal_name='Test',billing_address='Test'),'patch').status_code,409)
        self.assertEqual(self.submit().status_code,400)
    def test_image_upload_reencoded_and_download_scoped(self):
        r=self.upload();self.assertEqual(r.status_code,200,r.json);fid=r.json['id'];res=self.client.get('/api/account-documents/'+str(fid))
        self.assertEqual(res.status_code,200);self.assertTrue(res.data.startswith(b'\xff\xd8'));self.assertIn('attachment',res.headers['Content-Disposition']);self.assertEqual(res.headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(self.driver.get('/api/account-documents/'+str(fid)).status_code,404)
        self.assertEqual(self.upload().status_code,409)
    def test_unsafe_types_and_limit(self):
        for raw,name in [(b'<svg onload="alert(1)"></svg>','fake.svg'),(b'<script>alert(1)</script>','fake.pdf'),(b'x'*1048577,'large.pdf')]:self.assertEqual(self.upload(raw,name).status_code,400)
    def test_pdf_download_not_inline(self):
        r=self.upload(b'%PDF-1.4\n%FICTITIOUS TEST\n%%EOF','fictif.pdf');self.assertEqual(r.status_code,200)
        res=self.admin.get('/api/account-documents/'+str(r.json['id']));self.assertIn('attachment',res.headers['Content-Disposition']);self.assertEqual(res.mimetype,'application/pdf')
    def test_submit_review_changes_invalidate_approval(self):
        self.fill();self.upload();self.assertEqual(self.submit().status_code,200);d=self.dossier();body=dict(revision=d['revision'],status='Validé',checked=True,note='Contrôle fictif')
        self.assertEqual(self.mutate(self.client,'/api/account-dossiers/2/review',body).status_code,403)
        self.assertEqual(self.mutate(self.admin,'/api/account-dossiers/2/review',body).status_code,200)
        self.assertEqual(self.dossier()['status'],'Validé');self.fill();self.assertEqual(self.dossier()['status'],'Brouillon')
    def test_withdrawal_erases_binary_preserves_audit(self):
        fid=self.upload().json['id'];self.assertEqual(self.mutate(self.client,'/api/account-documents/'+str(fid),dict(reason='Fichier de test retiré'),'delete').status_code,200)
        self.assertEqual(self.client.get('/api/account-documents/'+str(fid)).status_code,404)
        with f.system.conn() as c:self.assertIsNone(c.execute('SELECT content FROM account_documents WHERE id=?',(fid,)).fetchone()[0])
        self.assertEqual(self.dossier()['audit'][0]['action'],'document retiré')
    def test_review_requires_confirmation_and_return_reason(self):
        self.fill();self.upload();self.submit();d=self.dossier()
        for status in ['Validé','À compléter']:
            self.assertEqual(self.mutate(self.admin,'/api/account-dossiers/2/review',dict(revision=d['revision'],status=status)).status_code,400)
        self.assertEqual(self.mutate(self.admin,'/api/account-dossiers/2/review',dict(revision=d['revision'],status='À compléter',note='Document manquant')).status_code,200)
        self.assertEqual(self.dossier()['status'],'À compléter')
if __name__=='__main__':unittest.main()
