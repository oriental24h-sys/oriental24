import base64
import io
import sqlite3
import unittest
from PIL import Image
from company_profile import ensure_schema, own_profile, save_profile, normalize_image

class Error(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

class CompanyProfileTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY)')
        self.c.executemany('INSERT INTO users VALUES(?)',[(1,),(2,)])
        ensure_schema(self.c)
        self.user={'id':1,'role':'client','client_type':'societe_livraison'}
    def tearDown(self): self.c.close()
    def save(self, data, user=None):
        save_profile(self.c,user or self.user,data,lambda:'2026-10-18T10:00:00',Error)
    @staticmethod
    def image():
        b=io.BytesIO();Image.new('RGB',(600,400),'orange').save(b,format='JPEG')
        return 'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()
    def test_bank_rib_normalization_and_ownership(self):
        self.save({'bank_name':' Test Bank ','bank_rib':'001 234-567890123456789012'})
        self.assertEqual(own_profile(self.c,1)['bank_rib'],'001234567890123456789012')
        self.assertEqual(own_profile(self.c,1)['bank_name'],'Test Bank')
        self.assertEqual(own_profile(self.c,2)['bank_rib'],'')
    def test_rib_validation(self):
        for v in ['123','a'*24,'١'*24,None,123, '0'*25]:
            with self.subTest(value=v),self.assertRaises(Error):self.save({'bank_rib':v})
    def test_other_roles_and_client_types_cannot_write(self):
        for role,kind in [('admin','vendeur'),('agent','vendeur'),('livreur','vendeur')]:
            with self.subTest(role=role),self.assertRaises(Error) as ctx:
                self.save({'bank_name':'Test'},dict(id=1,role=role,client_type=kind))
            self.assertEqual(ctx.exception.status,403)
    def test_image_normalization_preservation_and_removal(self):
        self.save({'profile_image':self.image()})
        saved=own_profile(self.c,1)['profile_image'];self.assertTrue(saved.startswith('data:image/png;base64,'))
        im=Image.open(io.BytesIO(base64.b64decode(saved.split(',')[1])))
        self.assertLessEqual(max(im.size),512);self.assertNotIn('exif',im.info)
        self.save({'bank_name':'Test'});self.assertEqual(own_profile(self.c,1)['profile_image'],saved)
        self.save({'profile_image':''});self.assertEqual(own_profile(self.c,1)['profile_image'],'')
    def test_reject_active_or_invalid_image_payloads(self):
        for v in ['https://example.com/photo.png','data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,bm90LWltYWdl', None, 'x'*1500000]:
            with self.subTest(value=str(v)[:40]),self.assertRaises(Error):normalize_image(v,Error)
    def test_optional_fields_clear(self):
        self.save({'bank_name':'Bank','bank_rib':'0'*24})
        self.save({'bank_name':'','bank_rib':''})
        self.assertEqual(own_profile(self.c,1)['bank_rib'],'')
    def test_schema_is_idempotent(self):
        self.save({'bank_name':'Bank'});ensure_schema(self.c)
        self.assertEqual(own_profile(self.c,1)['bank_name'],'Bank')
