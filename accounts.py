"""Private account dossiers and optional administrative review. Not identity verification."""
import io,base64,binascii,hashlib,json
from flask import request,jsonify,send_file
from werkzeug.utils import secure_filename
from PIL import Image,UnidentifiedImageError

def register_accounts(app,services):
    conn,auth,user,now,text,Error=(services[k] for k in ['conn','auth','user','now','text','APIError'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS account_dossiers(user_id INTEGER PRIMARY KEY REFERENCES users(id),legal_name TEXT NOT NULL DEFAULT '',billing_address TEXT NOT NULL DEFAULT '',legal_id TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'Brouillon',revision INTEGER NOT NULL DEFAULT 0,review_note TEXT NOT NULL DEFAULT '',submitted_at TEXT,reviewed_at TEXT,reviewed_by INTEGER REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS account_documents(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),kind TEXT NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,content BLOB,sha256 TEXT NOT NULL,size INTEGER NOT NULL,created_at TEXT NOT NULL,removed_at TEXT);
        CREATE TABLE IF NOT EXISTS account_audit(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),actor_id INTEGER NOT NULL REFERENCES users(id),action TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL);
        ''')
    def data():
        d=request.get_json()
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        return d
    def owner(c,uid,u):
        p=c.execute('SELECT id,name,company,email,role FROM users WHERE id=?',(uid,)).fetchone()
        if not p or (u['role']!='admin' and uid!=u['id']):raise Error('Dossier introuvable.',404)
        return dict(p)
    def ensure(c,uid):c.execute('INSERT OR IGNORE INTO account_dossiers(user_id) VALUES(?)',(uid,))
    def record(c,uid,u,action,details):c.execute('INSERT INTO account_audit(user_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(uid,u['id'],action,json.dumps(details,ensure_ascii=False),now()))
    def invalidate(c,uid):c.execute("UPDATE account_dossiers SET status='Brouillon',revision=revision+1,review_note='',reviewed_at=NULL,reviewed_by=NULL WHERE user_id=?",(uid,))
    def dossier(c,uid,u):
        p=owner(c,uid,u);d=c.execute('SELECT * FROM account_dossiers WHERE user_id=?',(uid,)).fetchone()
        d=dict(d) if d else dict(user_id=uid,legal_name=p['company'] or p['name'],billing_address='',legal_id='',status='Brouillon',revision=0,review_note='')
        d.update(account=p,documents=[dict(r) for r in c.execute('SELECT id,kind,name,mime,sha256,size,created_at FROM account_documents WHERE user_id=? AND removed_at IS NULL ORDER BY id DESC',(uid,))],audit=[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT a.*,u.name actor FROM account_audit a JOIN users u ON u.id=a.actor_id WHERE a.user_id=? ORDER BY a.id DESC LIMIT 200',(uid,))]);return d
    @app.get('/api/account-dossiers')
    @auth()
    def account_dossiers():
        u=user()
        with conn() as c:
            ids=[p['id'] for p in c.execute("SELECT id FROM users WHERE role IN ('client','livreur') ORDER BY id DESC LIMIT 500")] if u['role']=='admin' else [u['id']]
            return jsonify([dossier(c,uid,u) for uid in ids])
    @app.route('/api/account-dossiers/<int:uid>',methods=['GET','PATCH'])
    @auth()
    def account_dossier(uid):
        u=user()
        with conn() as c:
            if request.method=='PATCH':
                d=data();c.execute('BEGIN IMMEDIATE');owner(c,uid,u);ensure(c,uid)
                old=c.execute('SELECT * FROM account_dossiers WHERE user_id=?',(uid,)).fetchone()
                if d.get('revision')!=old['revision']:raise Error('Dossier modifié. Rechargez avant de continuer.',409)
                c.execute('UPDATE account_dossiers SET legal_name=?,billing_address=?,legal_id=? WHERE user_id=?',(text(d,'legal_name',maxlen=160),text(d,'billing_address',maxlen=600),text(d,'legal_id',False,100),uid));invalidate(c,uid);record(c,uid,u,'informations modifiées',{})
            return jsonify(dossier(c,uid,u))
    @app.post('/api/account-dossiers/<int:uid>/<action>')
    @auth()
    def account_submit_review(uid,action):
        d=data();u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');owner(c,uid,u);ensure(c,uid);o=dossier(c,uid,u)
            if d.get('revision')!=o['revision']:raise Error('Dossier modifié. Rechargez avant de continuer.',409)
            if action=='submit':
                if o['status'] not in ['Brouillon','À compléter']:raise Error('Dossier déjà soumis ou validé.',409)
                if not o['legal_name'] or not o['billing_address'] or not o['documents']:raise Error('Complétez le nom, l’adresse et ajoutez au moins un document.')
                c.execute("UPDATE account_dossiers SET status='À vérifier',revision=revision+1,submitted_at=? WHERE user_id=?",(now(),uid));record(c,uid,u,'dossier soumis',{})
            elif action=='review':
                if u['role']!='admin':raise Error('Revue réservée à l’administration.',403)
                if o['status']!='À vérifier':raise Error('Dossier non soumis ou déjà revu.',409)
                status=d.get('status');note=text(d,'note',status=='À compléter',600)
                if status not in ['Validé','À compléter']:raise Error('Décision invalide.')
                if status=='Validé' and d.get('checked') is not True:raise Error('Confirmez votre contrôle administratif.')
                c.execute('UPDATE account_dossiers SET status=?,revision=revision+1,review_note=?,reviewed_at=?,reviewed_by=? WHERE user_id=?',(status,note,now(),u['id'],uid));record(c,uid,u,'revue administrative',{'status':status,'note':note})
            else:raise Error('Action inconnue.',404)
            return jsonify(ok=True)
    @app.post('/api/account-dossiers/<int:uid>/documents')
    @auth()
    def account_upload(uid):
        d=data();u=user()
        # Scope is checked before decoding untrusted content.
        with conn() as c:owner(c,uid,u)
        kind=text(d,'kind',maxlen=40);name=secure_filename(text(d,'name',maxlen=180))
        if kind not in ['Contrat','RIB','Document entreprise','Autre']:raise Error('Type de document invalide.')
        if not name:raise Error('Nom de fichier invalide.')
        try:
            value=d.get('content')
            if not isinstance(value,str) or len(value)>1500000:raise ValueError()
            raw=base64.b64decode(value,validate=True)
            if not 1<=len(raw)<=1024*1024:raise ValueError()
        except (ValueError,binascii.Error):raise Error('Fichier invalide ou supérieur à 1 Mo.')
        if raw.startswith(b'%PDF-') and b'%%EOF' in raw[-2048:]:mime='application/pdf';name=name.rsplit('.',1)[0]+'.pdf'
        else:
            try:
                image=Image.open(io.BytesIO(raw))
                if image.format not in ['PNG','JPEG'] or image.width*image.height>8000000:raise ValueError()
                image.load();buf=io.BytesIO();image.convert('RGB').save(buf,format='JPEG',quality=88);raw=buf.getvalue();mime='image/jpeg';name=name.rsplit('.',1)[0]+'.jpg'
                if len(raw)>1024*1024:raise ValueError()
            except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):raise Error('Formats acceptés : PDF, JPG ou PNG, image maximum 8 mégapixels.')
        sha=hashlib.sha256(raw).hexdigest()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');owner(c,uid,u);ensure(c,uid)
            if c.execute('SELECT count(*) FROM account_documents WHERE user_id=? AND removed_at IS NULL',(uid,)).fetchone()[0]>=8:raise Error('Limite de 8 documents par compte.')
            if c.execute('SELECT 1 FROM account_documents WHERE user_id=? AND sha256=? AND removed_at IS NULL',(uid,sha)).fetchone():raise Error('Ce fichier est déjà présent.',409)
            fid=c.execute('INSERT INTO account_documents(user_id,kind,name,mime,content,sha256,size,created_at) VALUES(?,?,?,?,?,?,?,?)',(uid,kind,name,mime,raw,sha,len(raw),now())).lastrowid
            invalidate(c,uid);record(c,uid,u,'document ajouté',{'document_id':fid,'kind':kind,'sha256':sha});return jsonify(ok=True,id=fid)
    @app.route('/api/account-documents/<int:fid>',methods=['GET','DELETE'])
    @auth()
    def account_document(fid):
        u=user()
        with conn() as c:
            if request.method=='DELETE':c.execute('BEGIN IMMEDIATE')
            f=c.execute('SELECT * FROM account_documents WHERE id=? AND removed_at IS NULL',(fid,)).fetchone()
            if not f:raise Error('Document introuvable.',404)
            owner(c,f['user_id'],u)
            if request.method=='DELETE':
                reason=text(data(),'reason',maxlen=300);c.execute('UPDATE account_documents SET content=NULL,removed_at=? WHERE id=?',(now(),fid));invalidate(c,f['user_id']);record(c,f['user_id'],u,'document retiré',{'document_id':fid,'reason':reason});return jsonify(ok=True)
            response=send_file(io.BytesIO(f['content']),mimetype=f['mime'],as_attachment=True,download_name=f['name'],max_age=0)
            response.headers['Cache-Control']='private, no-store';response.headers['X-Content-Type-Options']='nosniff';return response
