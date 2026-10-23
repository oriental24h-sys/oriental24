import os,subprocess,sys,tempfile,unittest
from pathlib import Path
class ParcelStatusOrderTests(unittest.TestCase):
 def test_status_order_and_trigger(self):
  code=r'''
import app
with app.conn() as c:
 admin=dict(c.execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone())
 ids=[r['id'] for r in c.execute('SELECT id FROM parcels ORDER BY id LIMIT 3')];assert len(ids)==3
 a,b,d=ids
 c.execute("UPDATE parcels SET created_at='2020-01-01T10:00:00',status_updated_at=NULL")
 c.execute("UPDATE parcels SET created_at='2025-01-01T10:00:00',status_updated_at='2025-01-03T10:00:00' WHERE id=?",(a,))
 c.execute("UPDATE parcels SET created_at='2025-01-02T10:00:00',status_updated_at='2025-01-02T10:00:00' WHERE id=?",(b,))
 rows=app.list_parcels(c,admin);assert rows[0]['id']==a and rows[1]['id']==b
 c.execute("UPDATE parcels SET note='note only',updated_at='2099-01-01T00:00:00' WHERE id=?",(b,))
 assert app.list_parcels(c,admin)[0]['id']==a
 c.execute("UPDATE parcels SET status='Sort-test-state',updated_at='2025-01-04T10:00:00' WHERE id=?",(d,))
 assert app.list_parcels(c,admin)[0]['id']==d
 assert c.execute('SELECT status_updated_at FROM parcels WHERE id=?',(d,)).fetchone()[0]=='2025-01-04T10:00:00'
 c.execute("UPDATE parcels SET status='Sort-test-state',updated_at='2025-01-09T10:00:00' WHERE id=?",(d,))
 assert c.execute('SELECT status_updated_at FROM parcels WHERE id=?',(d,)).fetchone()[0]=='2025-01-04T10:00:00'
 c.execute("UPDATE parcels SET status='Other-test-state' WHERE id=?",(d,))
 assert c.execute('SELECT status_updated_at FROM parcels WHERE id=?',(d,)).fetchone()[0]!='2025-01-09T10:00:00'
 for role in ['admin','client','livreur','support','hub_manager']:
  actor=c.execute('SELECT * FROM users WHERE role=? LIMIT 1',(role,)).fetchone()
  if not actor:continue
  rows=app.list_parcels(c,dict(actor));ordered=[(r['status_updated_at'] or r['created_at'] or '',r['id']) for r in rows]
  assert ordered==sorted(ordered,reverse=True),role
'''
  with tempfile.TemporaryDirectory() as tmp:
   r=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],env={**os.environ,'DB_PATH':tmp+'/test.sqlite','SECRET_KEY':'test-order-key-not-production','APP_ENV':'development'},capture_output=True,text=True,timeout=90)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
