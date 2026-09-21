import unittest
import test_app as f
class ParcelStateTests(unittest.TestCase):
    setUp=f.PlatformTests.setUp
    data=f.PlatformTests.data
    mutate=f.PlatformTests.mutate
    new_parcel=f.PlatformTests.new_parcel
    def note(self,p,code='no_answer',revision=0,client=None):return self.mutate(client or self.admin,f'/api/parcels/{p["id"]}/reason',dict(reason_code=code,revision=revision),'patch')
    def detail(self,p):return self.admin.get('/api/parcels/'+str(p['id'])).json
    def test_reason_only_preserves_state_money_notes_and_dates(self):
        p=self.new_parcel(note='Consigne destinataire');before=self.detail(p)['parcel'];self.assertEqual(self.note(p).status_code,200)
        after=self.detail(p)['parcel']
        for k in ['status','note','amount','fee','return_fee','updated_at','driver_id','next_attempt_at']:self.assertEqual(before[k],after[k],k)
        self.assertEqual(after['reason_label'],'Pas de réponse');self.assertEqual(after['ops_revision'],1)
        self.assertIn('Pas de réponse',self.detail(p)['events'][0]['note']);self.assertEqual(self.detail(p)['events'][0]['actor'],'Administrateur')
        self.assertEqual(next(x for x in self.data(self.client)['parcels'] if x['id']==p['id'])['reason_label'],'Pas de réponse')
    def test_permissions_and_assignment_scope(self):
        p=self.new_parcel();self.assertEqual(self.note(p,client=self.client).status_code,403);self.assertEqual(self.note(p,client=self.driver).status_code,404)
        self.mutate(self.admin,'/api/parcels/'+str(p['id']),{'driver_id':3},'patch');self.assertEqual(self.note(p,revision=1,client=self.driver).status_code,200)
        self.mutate(self.admin,'/api/parcels/'+str(p['id']),{'driver_id':5},'patch');self.assertEqual(self.note(p,revision=3,client=self.driver).status_code,404)
    def test_revision_noop_clear_and_validation(self):
        p=self.new_parcel();self.assertEqual(self.note(p).status_code,200);n=len(self.detail(p)['events']);self.assertEqual(self.note(p,'wrong_number',0).status_code,409)
        r=self.note(p,revision=1);self.assertFalse(r.json['changed']);self.assertEqual(len(self.detail(p)['events']),n)
        self.assertEqual(self.note(p,None,1).status_code,200);self.assertIsNone(self.detail(p)['parcel']['reason_code'])
        for code in ['',False,1,[],{},'javascript:alert(1)','unknown_code']:
            self.assertEqual(self.note(p,code,2).status_code,400)
        for rev in [None,True,'2',1]:self.assertEqual(self.note(p,revision=rev).status_code,409)
    def test_inactive_and_custom_label_history(self):
        p=self.new_parcel();self.mutate(self.admin,'/api/logistics/reasons',dict(code='custom_note',label='<Équipe> motif',active=True));self.assertEqual(self.note(p,'custom_note').status_code,200)
        self.mutate(self.admin,'/api/logistics/reasons',dict(code='custom_note',label='Libellé modifié',active=False));self.assertEqual(self.note(self.new_parcel(),'custom_note').status_code,400)
        self.assertEqual(self.detail(p)['parcel']['reason_label'],'Libellé modifié');self.assertIn('<Équipe> motif',self.detail(p)['events'][0]['note'])
        self.assertEqual(self.note(p,None,1).status_code,200)
    def test_scheduling_remains_explicit(self):
        p=self.new_parcel();self.assertEqual(self.note(p,'postponed').status_code,200);self.assertEqual(self.detail(p)['parcel']['status'],'Créé');self.assertIsNone(self.detail(p)['parcel']['next_attempt_at'])
        with f.system.conn() as c:c.execute("UPDATE parcels SET status='Programmé',next_attempt_at='2099-01-01T12:00+01:00' WHERE id=?",(p['id'],))
        self.assertEqual(self.note(p,None,1).status_code,400);self.assertEqual(self.note(p,'no_answer',1).status_code,200)
        self.assertEqual(self.detail(p)['parcel']['next_attempt_at'],'2099-01-01T12:00+01:00')
    def test_invoice_document_and_driver_finance_locks(self):
        p=self.new_parcel();self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(status='Livré'),'patch');self.mutate(self.admin,'/api/invoices',dict(client_id=2));self.assertEqual(self.note(p,revision=1).status_code,409)
        # Guard queries remain the same as all operational mutations.
        p=self.new_parcel()
        with f.system.conn() as c:
            c.execute('PRAGMA foreign_keys=OFF')
            c.execute("INSERT INTO ops_documents(id,reference,kind,status,note,created_by,created_at) VALUES(999,'NOTE-TEST','pickup','Préparé','',1,'2026-09-20')")
            c.execute("INSERT INTO ops_document_lines(document_id,parcel_id,tracking,recipient,city,initial_status) VALUES(999,?,'TEST','Test','Oujda','Créé')",(p['id'],))
        self.assertEqual(self.note(p).status_code,409)
        p=self.new_parcel()
        with f.system.conn() as c:
            c.execute('PRAGMA foreign_keys=OFF')
            # Use the existing finance schema's required frozen fields.
            columns=c.execute('PRAGMA table_info(driver_statement_lines)').fetchall()
            values={r['name']:(p['id'] if r['name']=='parcel_id' else 1 if r['name']=='active' else 999 if r['name']=='statement_id' else 0 if r['type']=='INTEGER' else 'test') for r in columns if r['name']!='id' and (r['notnull'] or r['name'] in ['parcel_id','statement_id','active'])}
            c.execute('INSERT INTO driver_statement_lines('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',list(values.values()))
        self.assertEqual(self.note(p).status_code,409)
    def test_closed_driver_and_csrf_payload(self):
        p=self.new_parcel()
        with f.system.conn() as c:c.execute("UPDATE parcels SET driver_id=3,status='Livré' WHERE id=?",(p['id'],))
        self.assertEqual(self.note(p,client=self.driver).status_code,409);self.assertEqual(self.note(p).status_code,200)
        url=f'/api/parcels/{p["id"]}/reason';self.assertEqual(self.admin.patch(url,json={'reason_code':None,'revision':1}).status_code,403)
        for body in [[],None,{},dict(reason_code='no_answer',revision=1,status='Livré')]:self.assertEqual(self.mutate(self.admin,url,body,'patch').status_code,400)
    def test_catalogue_contains_reference_motifs(self):
        labels=[r['label'] for r in self.admin.get('/api/logistics/config').json['reasons']]
        for label in ['Pas de réponse','Reporté','Numéro incorrect','Commande doublée','Demande échange/remboursement','Hors zone de livraison']:self.assertIn(label,labels)
if __name__=='__main__':unittest.main()
