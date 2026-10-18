"""Private client profile extras; shared dossier fields are not duplicated."""
import json,re
from urllib.parse import urlsplit
from flask import request,jsonify


def ensure_schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS client_profile_extras(user_id INTEGER PRIMARY KEY REFERENCES users(id),
        city TEXT NOT NULL DEFAULT '',cin TEXT NOT NULL DEFAULT '',website TEXT NOT NULL DEFAULT '',
        language TEXT NOT NULL DEFAULT '',preferences TEXT NOT NULL DEFAULT '{}',revision INTEGER NOT NULL DEFAULT 0)''')


def notification_enabled(c,uid,key):
    row=c.execute('SELECT preferences FROM client_profile_extras WHERE user_id=?',(uid,)).fetchone()
    return json.loads(row['preferences']).get(key,True) if row else True


def register_client_profile_extras(app,s):
    conn,auth,user,Error,now=(s[k] for k in ('conn','auth','user','APIError','now'))
    with conn() as c:ensure_schema(c)
    keys=['payment']+['status:'+v for v in s['STATUSES']]
    def load(c,u):
        row=c.execute('SELECT * FROM client_profile_extras WHERE user_id=?',(u['id'],)).fetchone()
        data=dict(row) if row else dict(city='',cin='',website='',language='',preferences='{}',revision=0)
        prefs=json.loads(data.pop('preferences'));data['preferences']={k:prefs.get(k,True) for k in keys}
        dossier=c.execute('SELECT billing_address,legal_id,revision FROM account_dossiers WHERE user_id=?',(u['id'],)).fetchone()
        data.update(address=dossier['billing_address'] if dossier else '',legal_id=dossier['legal_id'] if dossier else '',dossier_revision=dossier['revision'] if dossier else 0)
        summary=dict(cod=0,fees=0,net=0,remaining=0,owed=0,paid=0)
        for row in c.execute("SELECT * FROM invoices WHERE client_id=? AND status!='Annulé'",(u['id'],)).fetchall():
            i=s['client_invoice_info'](c,row)
            summary['cod']+=round(i['cod']*100);summary['fees']+=round(i['fees']*100);summary['net']+=i['total_cents']
            if i['total_cents']>=0:summary['remaining']+=i['remaining_cents'];summary['paid']+=i['paid_cents']
            else:summary['owed']+=i['remaining_cents']
        data['billing']={k:v/100 for k,v in summary.items()}
        data['statuses']=s['STATUSES']
        data['contacts']={r['key']:r['value'] for r in c.execute("SELECT key,value FROM settings WHERE key IN ('public_phone','public_whatsapp','public_email','public_address','public_hours')")}
        return data
    @app.route('/api/client-profile',methods=['GET','PATCH'])
    @auth('client')
    def extra_profile():
        u=user()
        with conn() as c:
            if request.method=='PATCH':
                d=request.get_json(silent=True)
                required={'city','cin','website','language','preferences','address','legal_id','revision','dossier_revision'}
                if not isinstance(d,dict) or set(d)!=required:raise Error('Champs de profil invalides.')
                c.execute('BEGIN IMMEDIATE')
                old=load(c,u)
                if type(d['revision']) is not int or type(d['dossier_revision']) is not int or d['revision']!=old['revision'] or d['dossier_revision']!=old['dossier_revision']:raise Error('Profil modifié. Rechargez avant de continuer.',409)
                values={}
                for k,limit in [('city',120),('cin',30),('website',300),('address',600),('legal_id',100)]:
                    v=d[k]
                    if not isinstance(v,str) or len(v.strip())>limit or any(ord(ch)<32 and ch not in '\n\r' for ch in v):raise Error('Champ invalide : '+k)
                    values[k]=v.strip()
                if values['cin'] and not re.fullmatch(r'[A-Za-z0-9 -]{2,30}',values['cin']):raise Error('CIN invalide.')
                if values['website']:
                    url=urlsplit(values['website'])
                    if url.scheme not in ('https','http') or not url.hostname or url.username or url.password:raise Error('Site web : URL http:// ou https:// requise.')
                if d['language'] not in ('','fr','en','ar'):raise Error('Langue invalide.')
                if not isinstance(d['preferences'],dict) or set(d['preferences'])!=set(keys) or any(type(v) is not bool for v in d['preferences'].values()):raise Error('Préférences de notification invalides.')
                c.execute('''INSERT INTO client_profile_extras(user_id,city,cin,website,language,preferences,revision) VALUES(?,?,?,?,?,?,1)
                    ON CONFLICT(user_id) DO UPDATE SET city=excluded.city,cin=excluded.cin,website=excluded.website,language=excluded.language,preferences=excluded.preferences,revision=client_profile_extras.revision+1''',
                    (u['id'],values['city'],values['cin'],values['website'],d['language'],json.dumps(d['preferences'])))
                if values['address']!=old['address'] or values['legal_id']!=old['legal_id']:
                    c.execute('INSERT OR IGNORE INTO account_dossiers(user_id,legal_name) VALUES(?,?)',(u['id'],u['company'] or u['name']))
                    c.execute("UPDATE account_dossiers SET billing_address=?,legal_id=?,status='Brouillon',revision=revision+1,review_note='',reviewed_at=NULL,reviewed_by=NULL WHERE user_id=?",(values['address'],values['legal_id'],u['id']))
                    c.execute('INSERT INTO account_audit(user_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(u['id'],u['id'],'informations modifiées depuis Mon profil','{}',now()))
            return jsonify(load(c,u))
