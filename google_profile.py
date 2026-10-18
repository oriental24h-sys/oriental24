"""Google OAuth association/login and read-only Sheets preview. No automatic import."""
import os,re,json,time,secrets,hashlib,base64,csv,io
from urllib.parse import urlencode,urlsplit,quote
from flask import request,session,jsonify,redirect
from werkzeug.security import check_password_hash

SCOPE='openid email https://www.googleapis.com/auth/spreadsheets.readonly'

def configuration():
    client=os.getenv('GOOGLE_CLIENT_ID','').strip();secret=os.getenv('GOOGLE_CLIENT_SECRET','').strip();uri=os.getenv('GOOGLE_REDIRECT_URI','').strip()
    parsed=urlsplit(uri)
    valid=parsed.scheme=='https' and bool(parsed.hostname) and parsed.path=='/google/callback' and not parsed.query and not parsed.fragment and not parsed.username
    return dict(client_id=client,client_secret=secret,redirect_uri=uri,configured=bool(client and secret and valid))

def sheet_reference(value):
    if not isinstance(value,str):raise ValueError('ID Google Sheet invalide.')
    value=value.strip()
    if value.startswith('https://'):
        u=urlsplit(value)
        if u.hostname!='docs.google.com':raise ValueError('Utilisez une URL docs.google.com ou un ID Google Sheet.')
        m=re.match(r'^/spreadsheets/d/([A-Za-z0-9_-]+)(?:/|$)',u.path)
        value=m[1] if m else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,150}',value):raise ValueError('ID Google Sheet invalide.')
    return value

def register_google_profile(app,s):
    conn,auth,user,Error,now=(s[k] for k in ('conn','auth','user','APIError','now'))
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS google_accounts(user_id INTEGER PRIMARY KEY REFERENCES users(id),
            subject TEXT UNIQUE NOT NULL,email TEXT NOT NULL,tokens TEXT NOT NULL,linked_at TEXT NOT NULL)''')
    def cipher():
        from cryptography.fernet import Fernet
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('google-tokens-v1:'+app.secret_key).encode()).digest()))
    def pack(data):return cipher().encrypt(json.dumps(data).encode()).decode()
    def unpack(value):
        try:return json.loads(cipher().decrypt(value.encode()))
        except Exception:raise Error('Connexion Google à renouveler.',409)
    def require_config():
        cfg=configuration()
        if not cfg['configured']:raise Error('Google non configuré : contactez l’administration.',503)
        return cfg
    def begin(mode,uid=None):
        cfg=require_config();state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48);nonce=secrets.token_urlsafe(24)
        session['google_flow']=dict(state=state,verifier=verifier,nonce=nonce,at=int(time.time()),mode=mode,uid=uid,sid=session.get('sid') if uid else None)
        params=dict(client_id=cfg['client_id'],redirect_uri=cfg['redirect_uri'],response_type='code',scope=SCOPE,state=state,nonce=nonce,access_type='offline',prompt='consent',code_challenge_method='S256',code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='))
        return 'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(params)
    @app.get('/api/google/status')
    @auth('client')
    def google_status():
        u=user()
        with conn() as c:r=c.execute('SELECT email FROM google_accounts WHERE user_id=?',(u['id'],)).fetchone()
        return jsonify(configured=configuration()['configured'],linked=bool(r),email=r['email'] if r else '')
    @app.post('/api/google/link')
    @auth('client')
    def google_link():
        u=user();d=request.get_json(silent=True) or {}
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        password=d.get('current_password','')
        if not isinstance(password,str) or len(password)>128:raise Error('Mot de passe invalide.')
        with conn() as c:p=c.execute('SELECT password FROM users WHERE id=?',(u['id'],)).fetchone()
        if not check_password_hash(p['password'],password):raise Error('Mot de passe actuel incorrect.',403)
        return jsonify(url=begin('link',u['id']))
    @app.get('/google/login')
    def google_login():return redirect(begin('login'))
    @app.get('/google/callback')
    def google_callback():
        cfg=require_config();flow=session.pop('google_flow',None)
        if not flow or not secrets.compare_digest(str(request.args.get('state','')),flow['state']) or not 0<=time.time()-flow['at']<=600:raise Error('Validation Google expirée ou invalide. Recommencez.',400)
        if request.args.get('error'):return redirect('/app?google=cancelled' if flow['mode']=='link' else '/login')
        code=request.args.get('code','')
        if not code or len(code)>4096:raise Error('Code Google invalide.')
        if flow['mode']=='link':
            u=user()
            if u['role']!='client' or u['id']!=flow['uid'] or session.get('sid')!=flow['sid']:raise Error('Session modifiée. Recommencez.',403)
        import requests
        from google.oauth2 import id_token
        from google.auth.transport.requests import Request
        try:
            response=requests.post('https://oauth2.googleapis.com/token',data=dict(code=code,client_id=cfg['client_id'],client_secret=cfg['client_secret'],redirect_uri=cfg['redirect_uri'],grant_type='authorization_code',code_verifier=flow['verifier']),timeout=15)
            response.raise_for_status();tokens=response.json()
            claims=id_token.verify_oauth2_token(tokens['id_token'],Request(),cfg['client_id'])
            if claims.get('nonce')!=flow['nonce'] or claims.get('email_verified') is not True or not claims.get('sub'):raise ValueError()
        except Exception:raise Error('Google n’a pas pu être vérifié. Recommencez la connexion.',400)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            linked=c.execute('SELECT * FROM google_accounts WHERE subject=?',(claims['sub'],)).fetchone()
            if flow['mode']=='login':
                account=c.execute("SELECT * FROM users WHERE id=? AND active=1 AND role='client'",(linked['user_id'],)).fetchone() if linked else None
                if not account:raise Error('Ce compte Google n’est pas associé. Connectez-vous par mot de passe puis associez Google depuis Mon profil.',403)
                s['security_issue'](c,account['id'],'Connexion Google réussie')
            else:
                # Recheck after the network exchange: revoked sessions cannot bind identities.
                s['security_check_session'](c,u['id'])
                if linked and linked['user_id']!=u['id']:raise Error('Compte Google déjà associé à un autre compte.',409)
                tokens.pop('id_token',None);tokens['expires_at']=int(time.time())+int(tokens.get('expires_in',3600))
                c.execute('''INSERT INTO google_accounts VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET subject=excluded.subject,email=excluded.email,tokens=excluded.tokens,linked_at=excluded.linked_at''',(u['id'],claims['sub'],claims.get('email',''),pack(tokens),now()))
        return redirect('/app?google=linked' if flow['mode']=='link' else '/app')
    @app.delete('/api/google/link')
    @auth('client')
    def unlink_google():
        u=user()
        with conn() as c:c.execute('DELETE FROM google_accounts WHERE user_id=?',(u['id'],))
        session.pop('google_flow',None)
        return jsonify(ok=True)
    @app.post('/api/google/sheets/preview')
    @auth('client')
    def google_sheet_preview():
        cfg=require_config();u=user();d=request.get_json(silent=True)
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        try:sheet=sheet_reference(d.get('sheet_id'))
        except ValueError as e:raise Error(str(e))
        tab=d.get('sheet_name')
        if not isinstance(tab,str) or not 1<=len(tab.strip())<=100 or any(ord(x)<32 for x in tab):raise Error('Nom de feuille invalide.')
        with conn() as c:r=c.execute('SELECT * FROM google_accounts WHERE user_id=?',(u['id'],)).fetchone()
        if not r:raise Error('Associez votre compte Google avant l’import.',409)
        old=dict(r);tokens=unpack(r['tokens'])
        import requests
        try:
            if tokens.get('expires_at',0)<=time.time()+60:
                if not tokens.get('refresh_token'):raise Error('Autorisation Google expirée. Associez à nouveau votre compte.',409)
                res=requests.post('https://oauth2.googleapis.com/token',data=dict(client_id=cfg['client_id'],client_secret=cfg['client_secret'],refresh_token=tokens['refresh_token'],grant_type='refresh_token'),timeout=15)
                res.raise_for_status();tokens.update(res.json());tokens['expires_at']=int(time.time())+int(tokens.get('expires_in',3600))
            # Ask for one excess row: existing importer enforces the 500-row cap.
            area="'"+tab.strip().replace("'","''")+"'!A1:Z502"
            url='https://sheets.googleapis.com/v4/spreadsheets/'+sheet+'/values/'+quote(area,safe='')
            with requests.get(url,params={'valueRenderOption':'FORMATTED_VALUE'},headers={'Authorization':'Bearer '+tokens['access_token']},timeout=20,stream=True,allow_redirects=False) as res:
                res.raise_for_status();raw=bytearray()
                for chunk in res.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw)>2*1024*1024:raise Error('Feuille trop volumineuse (2 Mo maximum).')
                values=json.loads(raw)['values']
        except Error:raise
        except Exception:raise Error('Lecture Google Sheets impossible : vérifiez le partage, le nom de feuille et l’autorisation Google.',400)
        if not values or len(values)<2:raise Error('La feuille doit contenir un en-tête et au moins une commande.')
        csv_data=io.StringIO();writer=csv.writer(csv_data,delimiter=';');writer.writerows(values)
        # A disconnect/relink during Google access must not restore old tokens or import data.
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');s['security_check_session'](c,u['id'])
            current=c.execute('SELECT tokens FROM google_accounts WHERE user_id=? AND subject=?',(u['id'],old['subject'])).fetchone()
            if not current or current['tokens']!=old['tokens']:raise Error('Connexion Google modifiée. Réessayez.',409)
            c.execute('UPDATE google_accounts SET tokens=? WHERE user_id=?',(pack(tokens),u['id']))
        result=s['preview_client_import'](csv_data.getvalue().encode('utf-8'),'Google-Sheets.csv',u,{})
        return jsonify(result)
