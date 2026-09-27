"""Optional issuer identity and frozen print metadata. Not a fiscal invoicing engine."""
import json
import re
from flask import jsonify, request

FIELDS = {'legal_name':120, 'address':300, 'city':100, 'phone':40, 'email':120,
          'ice':30, 'rc':30, 'if_number':30, 'tp':30, 'cnss':30, 'payment_terms':240}
KEY = 'driver_invoice_profile'

def profile(c):
    row=c.execute('SELECT value FROM settings WHERE key=?',(KEY,)).fetchone()
    return json.loads(row['value']) if row else dict(revision=0,**{k:'' for k in FIELDS})

def print_snapshot(c, did, rows):
    dr=c.execute('SELECT u.phone,u.driver_address,ci.name city FROM users u LEFT JOIN cities ci ON ci.id=u.driver_city_id WHERE u.id=?',(did,)).fetchone()
    return {'version':1, 'issuer':profile(c), 'driver':dict(dr),
            'parcels':[{ 'parcel_id':r['id'], 'phone':r['phone'], 'amount':str(r['amount']) } for r in rows]}

def register_invoice_profile(app, services):
    conn,auth,user,now,Error=(services[k] for k in ('conn','auth','user','now','APIError'))
    with conn() as c:
        if 'print_snapshot' not in {r['name'] for r in c.execute('PRAGMA table_info(driver_statements)')}:
            c.execute('ALTER TABLE driver_statements ADD COLUMN print_snapshot TEXT')
        c.execute('''CREATE TABLE IF NOT EXISTS driver_invoice_profile_audit (
            id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL REFERENCES users(id),
            before_json TEXT NOT NULL, after_json TEXT NOT NULL, created_at TEXT NOT NULL)''')

    @app.get('/api/driver-finance/invoice-profile')
    @auth('admin')
    def driver_invoice_profile_get():
        with conn() as c:return jsonify(profile(c))

    @app.put('/api/driver-finance/invoice-profile')
    @auth('admin')
    def driver_invoice_profile_save():
        d=request.get_json()
        if not isinstance(d,dict) or set(d)!=set(FIELDS)|{'revision'}:
            raise Error('Champs des coordonnées invalides.')
        if type(d['revision']) is not int or d['revision']<0:raise Error('Version invalide.')
        clean={}
        for k,limit in FIELDS.items():
            v=d[k]
            if not isinstance(v,str) or len(v.strip())>limit or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',v):
                raise Error('Valeur invalide : '+k)
            clean[k]=v.strip()
        if clean['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',clean['email']):raise Error('E-mail invalide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');old=profile(c)
            if d['revision']!=old['revision']:raise Error('Coordonnées modifiées. Fermez et rechargez le formulaire.',409)
            clean['revision']=old['revision']+1
            c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(KEY,json.dumps(clean,ensure_ascii=False)))
            c.execute('INSERT INTO driver_invoice_profile_audit(actor_id,before_json,after_json,created_at) VALUES(?,?,?,?)',
                      (user()['id'],json.dumps(old,ensure_ascii=False),json.dumps(clean,ensure_ascii=False),now()))
        return jsonify(ok=True,revision=clean['revision'])
