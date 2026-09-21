"""Role-scoped application notices. Plain text only; no external service integration."""
import json
from urllib.parse import urlsplit
from flask import request,jsonify

ROLES=['admin','client','livreur']
FIELDS={'title','body','kind','audience','active','position','link_kind','link_label','link_url'}

def validate_notice(d,Error,updating=False):
    if not isinstance(d,dict) or set(d)!=FIELDS|({'revision'} if updating else set()):raise Error('Champs de l’annonce invalides.')
    def text(key,limit,required=False):
        value=d.get(key)
        if not isinstance(value,str) or len(value.strip())>limit or (required and not value.strip()):raise Error('Champ invalide : '+key)
        return value.strip()
    title=text('title',120,True);body=text('body',900,True)
    if d['kind'] not in ['info','warning','important','banner']:raise Error('Style invalide.')
    roles=d['audience']
    if not isinstance(roles,list) or not roles or any(r not in ROLES for r in roles) or len(roles)!=len(set(roles)):raise Error('Choisissez les espaces destinataires.')
    if type(d['active']) is not bool or type(d['position']) is not int or not 0<=d['position']<=99:raise Error('Publication ou ordre invalide.')
    if updating and (type(d['revision']) is not int or d['revision']<1):raise Error('Version invalide.',409)
    kind=d['link_kind'];label=text('link_label',90);url=text('link_url',1000)
    if kind not in ['none','url','template']:raise Error('Type de lien invalide.')
    if kind=='none':label=url=''
    else:
        if not label:raise Error('Libellé du lien obligatoire.')
        if kind=='template':
            if 'livreur' in roles:raise Error('Le modèle Excel est réservé aux espaces Admin et Client.')
            url=''
        else:
            try:
                p=urlsplit(url)
                valid=p.scheme=='https' and bool(p.hostname) and not p.username and not p.password and not any(ord(ch)<33 or ch=='\\' for ch in url)
                p.port
            except ValueError:valid=False
            if not valid:raise Error('Lien HTTPS complet requis, sans identifiants ni caractères de contrôle.')
    return dict(title=title,body=body,kind=d['kind'],audience=[r for r in ROLES if r in roles],active=d['active'],position=d['position'],link_kind=kind,link_label=label,link_url=url)

def row_notice(r):
    d=dict(r);d['audience']=json.loads(d['audience']);d['active']=bool(d['active']);return d

def register_announcements(app,services):
    conn,auth,user,Error,now=(services[k] for k in ['conn','auth','user','APIError','now'])
    with conn() as c:c.executescript('''
        CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,kind TEXT NOT NULL,audience TEXT NOT NULL,active INTEGER NOT NULL,position INTEGER NOT NULL,link_kind TEXT NOT NULL,link_label TEXT NOT NULL,link_url TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,updated_by INTEGER NOT NULL REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS announcement_audit(id INTEGER PRIMARY KEY,announcement_id INTEGER NOT NULL REFERENCES announcements(id),actor_id INTEGER NOT NULL REFERENCES users(id),action TEXT NOT NULL,before_json TEXT,after_json TEXT NOT NULL,created_at TEXT NOT NULL);
    ''')
    @app.get('/api/announcements')
    @auth()
    def active_announcements():
        u=user()
        with conn() as c:
            rows=[row_notice(r) for r in c.execute('SELECT * FROM announcements WHERE active=1 ORDER BY position,id')]
            return jsonify([{k:d[k] for k in ['id','title','body','kind','link_kind','link_label','link_url']} for d in rows if u['role'] in d['audience']])
    @app.route('/api/announcements/manage',methods=['GET','POST'])
    @auth('admin')
    def manage_announcements():
        if request.method=='GET':
            with conn() as c:return jsonify([row_notice(r) for r in c.execute('SELECT * FROM announcements ORDER BY position,id')])
        d=validate_notice(request.get_json(silent=True),Error);u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT count(*) FROM announcements').fetchone()[0]>=50:raise Error('Limite de 50 annonces : réutilisez une annonce inactive.')
            if d['active'] and c.execute('SELECT count(*) FROM announcements WHERE active=1').fetchone()[0]>=10:raise Error('Dix annonces actives maximum.')
            keys=list(d);stamp=now();aid=c.execute('INSERT INTO announcements('+','.join(keys)+',created_at,updated_at,updated_by) VALUES('+','.join('?' for _ in range(len(keys)+3))+')',[json.dumps(d[k],ensure_ascii=False) if k=='audience' else d[k] for k in keys]+[stamp,stamp,u['id']]).lastrowid
            c.execute('INSERT INTO announcement_audit(announcement_id,actor_id,action,after_json,created_at) VALUES(?,?,?,?,?)',(aid,u['id'],'création',json.dumps(d,ensure_ascii=False),stamp))
            return jsonify(ok=True,id=aid,revision=1)
    @app.patch('/api/announcements/<int:aid>')
    @auth('admin')
    def update_announcement(aid):
        raw=request.get_json(silent=True);d=validate_notice(raw,Error,True);u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');old=c.execute('SELECT * FROM announcements WHERE id=?',(aid,)).fetchone()
            if not old:raise Error('Annonce introuvable.',404)
            old=row_notice(old)
            if old['revision']!=raw['revision']:raise Error('Annonce modifiée. Fermez et actualisez avant de réessayer.',409)
            if all(old[k]==d[k] for k in d):return jsonify(ok=True,changed=False,revision=old['revision'])
            if d['active'] and not old['active'] and c.execute('SELECT count(*) FROM announcements WHERE active=1').fetchone()[0]>=10:raise Error('Dix annonces actives maximum.')
            stamp=now();keys=list(d);c.execute('UPDATE announcements SET '+','.join(k+'=?' for k in keys)+',revision=revision+1,updated_at=?,updated_by=? WHERE id=?',[json.dumps(d[k],ensure_ascii=False) if k=='audience' else d[k] for k in keys]+[stamp,u['id'],aid])
            c.execute('INSERT INTO announcement_audit(announcement_id,actor_id,action,before_json,after_json,created_at) VALUES(?,?,?,?,?,?)',(aid,u['id'],'modification',json.dumps(old,ensure_ascii=False),json.dumps(d,ensure_ascii=False),stamp))
            return jsonify(ok=True,changed=True,revision=old['revision']+1)
