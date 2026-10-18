import unittest
from unittest.mock import patch
from google_profile import sheet_reference,configuration

class GoogleProfileTests(unittest.TestCase):
    def test_sheet_reference_blocks_other_hosts_and_path_injection(self):
        self.assertEqual(sheet_reference('a'*30),'a'*30)
        self.assertEqual(sheet_reference('https://docs.google.com/spreadsheets/d/'+'a'*30+'/edit#gid=0'),'a'*30)
        for bad in ['http://localhost/x','https://evil.test/spreadsheets/d/'+'a'*30,'../../token','https://docs.google.com.evil.test/spreadsheets/d/'+'a'*30,'file:///etc/passwd',None]:
            with self.assertRaises(ValueError):sheet_reference(bad)
    def test_configuration_requires_fixed_https_callback(self):
        with patch.dict('os.environ',{'GOOGLE_CLIENT_ID':'test','GOOGLE_CLIENT_SECRET':'test','GOOGLE_REDIRECT_URI':'http://example.test/google/callback'}):self.assertFalse(configuration()['configured'])
        with patch.dict('os.environ',{'GOOGLE_CLIENT_ID':'test','GOOGLE_CLIENT_SECRET':'test','GOOGLE_REDIRECT_URI':'https://example.test/google/callback'}):self.assertTrue(configuration()['configured'])
