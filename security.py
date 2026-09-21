"""Revocable server-side sessions, bounded authentication attempts and private security history."""
import hashlib,hmac,secrets,time,ipaddress,re
from datetime import datetime,timezone
from flask import request,session,jsonify,g
from werkzeug.security import generate_password_hash,check_password_hash


def register_security(app,services):
    conn,auth,user,Error=(services[k] for k in ['conn','auth','user','APIError'])
    dummy_hash=generate_password_hash(secrets.token_hex(32))
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS auth_sessions(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),token_hash TEXT NOT NULL UNIQUE,created_at INTEGER NOT NULL,last_seen INTEGER NOT NULL,expires_at INTEGER NOT NULL,user_agent TEXT NOT NULL,network TEXT NOT NULL,revoked_at INTEGER,revoke_reason TEXT);
        CREATE INDEX IF NOT EXISTS auth_session_user ON auth_sessions(user_id,id);
        CREATE TABLE IF NOT EXISTS auth_limits(key TEXT PRIMARY KEY,hits INTEGER NOT NULL,expires_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS auth_limit_expiry ON auth_limits(expires_at);
        CREATE TABLE IF NOT EXISTS auth_events(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),actor_id INTEGER REFERENCES users(id),action TEXT NOT NULL,network TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS auth_events_user ON auth_events(user_id,id);
        ''')
    def clock():return int(time.time())
    def digest(s):return hashlib.sha256(s.encode()).hexdigest()
    def bucket(s):return hmac.new(app.secret_key.encode(),s.encode(),hashlib.sha256).hexdigest()
    def network():
        try:
            a=ipaddress.ip_address(request.remote_addr or '')
            return str(ipaddress.ip_network(f'{a}/{24 if a.version==4 else 64}',strict=False))
        except ValueError:return 'Réseau non identifié'
    def audit(c,uid,action,actor=None):
        c.execute('INSERT INTO auth_events(user_id,actor_id,action,network,created_at) VALUES(?,?,?,?,?)',(uid,actor,action,network(),clock()))
    def limits(specs):
        """Reserve slots before expensive password checks. Shared across application workers."""
        t=clock();keys=[(bucket(name),cap,seconds) for name,cap,seconds in specs];retry=0
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM auth_limits WHERE expires_at<?',(t-86400,))
            for key,cap,seconds in keys:
                r=c.execute('SELECT * FROM auth_limits WHERE key=?',(key,)).fetchone()
                if r and r['expires_at']>t and r['hits']>=cap:retry=max(retry,r['expires_at']-t)
            if not retry:
                for key,cap,seconds in keys:
                    c.execute('INSERT INTO auth_limits(key,hits,expires_at) VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET hits=CASE WHEN expires_at<=? THEN 1 ELSE hits+1 END,expires_at=CASE WHEN expires_at<=? THEN ? ELSE expires_at END',(key,t+seconds,t,t,t+seconds))
        if retry:
            response=jsonify(error='Trop de tentatives. Réessayez après le délai indiqué.',retry_after=retry)
            response.status_code=429;response.headers['Retry-After']=str(retry)
            return response
    def refund(names):
        with conn() as c:
            for name in names:c.execute('UPDATE auth_limits SET hits=MAX(0,hits-1) WHERE key=? AND expires_at>?',(bucket(name),clock()))
    def check_session(c,uid):
        token=session.get('sid');t=clock()
        row=c.execute('SELECT * FROM auth_sessions WHERE token_hash=? AND user_id=?',(digest(token),uid)).fetchone() if isinstance(token,str) else None
        if not row or row['revoked_at'] is not None or row['expires_at']<=t or row['last_seen']+app.config['AUTH_IDLE_SECONDS']<=t:
            session.clear();raise Error('Session expirée ou révoquée. Reconnectez-vous.',401)
        if t-row['last_seen']>=60 and not (request.method in ('GET','HEAD') and request.headers.get('X-Background-Poll')=='1'):c.execute('UPDATE auth_sessions SET last_seen=? WHERE id=? AND revoked_at IS NULL',(t,row['id']))
        return row
    def issue(c,uid,action='Connexion réussie'):
        old=session.get('sid')
        if isinstance(old,str):c.execute("UPDATE auth_sessions SET revoked_at=?,revoke_reason='Session remplacée' WHERE token_hash=? AND revoked_at IS NULL",(clock(),digest(old)))
        token=secrets.token_urlsafe(32);t=clock()
        agent=re.sub(r'[\x00-\x1f\x7f]',' ',request.headers.get('User-Agent','Navigateur non identifié'))[:240]
        c.execute('INSERT INTO auth_sessions(user_id,token_hash,created_at,last_seen,expires_at,user_agent,network) VALUES(?,?,?,?,?,?,?)',(uid,digest(token),t,t,t+app.config['AUTH_ABSOLUTE_SECONDS'],agent,network()))
        # At most ten simultaneously active sessions; the oldest are explicitly revoked.
        older=c.execute('SELECT id FROM auth_sessions WHERE user_id=? AND revoked_at IS NULL AND expires_at>? AND last_seen>? ORDER BY id DESC LIMIT -1 OFFSET 10',(uid,t,t-app.config['AUTH_IDLE_SECONDS'])).fetchall()
        for r in older:c.execute("UPDATE auth_sessions SET revoked_at=?,revoke_reason='Limite de 10 sessions' WHERE id=?",(t,r['id']))
        session.clear();session.permanent=True;session['uid']=uid;session['sid']=token;session['csrf']=secrets.token_hex(24)
        audit(c,uid,action,uid)
    def revoke_user(c,uid,reason,actor):
        c.execute('UPDATE auth_sessions SET revoked_at=?,revoke_reason=? WHERE user_id=? AND revoked_at IS NULL',(clock(),reason,uid))
        audit(c,uid,reason,actor)
    def password_changed(c,uid):
        revoke_user(c,uid,'Mot de passe modifié : anciennes sessions révoquées',uid)
        issue(c,uid,'Session renouvelée après changement de mot de passe')
    def login_failed(uid):
        with conn() as c:audit(c,uid,'Échec de connexion')
    services.update(security_check_session=check_session,security_issue=issue,security_revoke_user=revoke_user,
                    security_password_changed=password_changed,security_login_failed=login_failed,security_dummy_hash=dummy_hash)

    @app.before_request
    def auth_request_guard():
        if app.config['PRODUCTION_MODE'] and not request.is_secure:
            return jsonify(error='HTTPS obligatoire. Vérifiez le proxy de confiance.'),400
        if request.path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('Origin')
            allowed_origins={request.host_url.rstrip('/')}
            # Arena HTTPS preview terminates TLS upstream; trust only this exact host,
            # and only in the explicit demo/partitioned-cookie preview mode.
            if not app.config['PRODUCTION_MODE'] and app.config.get('SESSION_COOKIE_PARTITIONED'):
                allowed_origins.add('https://'+request.host)
            if origin and origin.rstrip('/') not in allowed_origins:
                return jsonify(error='Origine de requête refusée.'),403
        if request.method=='POST' and request.path in ('/api/login','/api/register'):
            if len(request.get_data(cache=True))>16384:return jsonify(error='Requête d’authentification trop volumineuse.'),413
            d=request.get_json(silent=True)
            if not isinstance(d,dict):return jsonify(error='Objet JSON requis.'),400
            email=str(d.get('email','')).strip().lower()[:300];ip=request.remote_addr or 'unknown'
            if request.path=='/api/register':
                if not app.config['PUBLIC_REGISTRATION']:return jsonify(error='Inscription publique fermée. Contactez l’administration.'),403
                return limits([(f'register:{ip}',5,3600)])
            if len(str(d.get('password','')))>128:return jsonify(error='Identifiants invalides.'),400
            pair=f'login-pair:{ip}:{email}';account=f'login-account:{email}'
            response=limits([(f'login-ip:{ip}',60,900),(pair,5,900),(account,20,900)])
            if response is not None:return response
            g.auth_refund=[pair,account]
        if request.method=='PATCH' and request.path=='/api/profile':
            d=request.get_json(silent=True)
            if isinstance(d,dict) and d.get('password'):
                u=user();name=f'password:{u["id"]}'
                response=limits([(name,5,900)])
                if response is not None:return response
                g.auth_refund=[name]
    @app.after_request
    def security_response(response):
        if getattr(g,'auth_refund',None) and response.status_code<400:refund(g.auth_refund)
        if app.config['PRODUCTION_MODE'] and request.is_secure:
            response.headers['Strict-Transport-Security']='max-age=31536000'
            response.headers['X-Frame-Options']='DENY'
            # Inline handlers in the current SPA prevent a strict script-src policy yet.
            response.headers['Content-Security-Policy']="frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'"
        response.headers['Permissions-Policy']='geolocation=(), microphone=(), camera=(self)'
        return response
    @app.get('/api/security/sessions')
    @auth()
    def sessions_list():
        u=user();t=clock()
        with conn() as c:
            current=check_session(c,u['id'])
            rows=[]
            for r in c.execute('SELECT id,created_at,last_seen,expires_at,user_agent,network,revoked_at,revoke_reason FROM auth_sessions WHERE user_id=? ORDER BY id DESC LIMIT 50',(u['id'],)):
                d=dict(r);d['current']=r['id']==current['id'];d['active']=r['revoked_at'] is None and r['expires_at']>t and r['last_seen']+app.config['AUTH_IDLE_SECONDS']>t
                d['idle_expires_at']=r['last_seen']+app.config['AUTH_IDLE_SECONDS'];rows.append(d)
            events=[dict(r) for r in c.execute('SELECT action,network,created_at FROM auth_events WHERE user_id=? ORDER BY id DESC LIMIT 100',(u['id'],))]
            return jsonify(sessions=rows,events=events,idle_seconds=app.config['AUTH_IDLE_SECONDS'],absolute_seconds=app.config['AUTH_ABSOLUTE_SECONDS'])
    @app.post('/api/security/sessions/revoke-others')
    @auth()
    def revoke_others():
        u=user();d=request.get_json(silent=True)
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        name=f'reauth:{u["id"]}';response=limits([(name,5,900)])
        if response is not None:return response
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');current=check_session(c,u['id'])
            pw=c.execute('SELECT password FROM users WHERE id=?',(u['id'],)).fetchone()[0]
            if not check_password_hash(pw,str(d.get('current_password',''))[:129]):raise Error('Mot de passe actuel incorrect.',400)
            c.execute("UPDATE auth_sessions SET revoked_at=?,revoke_reason='Autres sessions fermées par le titulaire' WHERE user_id=? AND id!=? AND revoked_at IS NULL",(clock(),u['id'],current['id']))
            audit(c,u['id'],'Autres sessions fermées',u['id'])
        refund([name]);return jsonify(ok=True)
    @app.delete('/api/security/sessions/<int:sid>')
    @auth()
    def revoke_one(sid):
        u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');current=check_session(c,u['id'])
            target=c.execute('SELECT * FROM auth_sessions WHERE id=? AND user_id=?',(sid,u['id'])).fetchone()
            if not target:raise Error('Session introuvable.',404)
            already=target['revoked_at'] is not None
            if not already:
                c.execute("UPDATE auth_sessions SET revoked_at=?,revoke_reason='Fermée par le titulaire' WHERE id=?",(clock(),sid))
                audit(c,u['id'],'Session fermée',u['id'])
            is_current=current['id']==sid
        if is_current:session.clear()
        return jsonify(ok=True,current=is_current,already_revoked=already)
    def logout(c,uid):
        token=session.get('sid')
        if isinstance(token,str):c.execute("UPDATE auth_sessions SET revoked_at=?,revoke_reason='Déconnexion' WHERE token_hash=? AND user_id=? AND revoked_at IS NULL",(clock(),digest(token),uid))
        audit(c,uid,'Déconnexion',uid);session.clear()
    services['security_logout']=logout
    @app.get('/api/security/deployment')
    @auth('admin')
    def deployment():
        return jsonify(mode='production' if app.config['PRODUCTION_MODE'] else 'demo',demo_accounts=app.config['DEMO_MODE'],
            public_registration=app.config['PUBLIC_REGISTRATION'],secure_cookie=app.config['SESSION_COOKIE_SECURE'],
            server_sessions=True,rate_limits=True,https_required=app.config['PRODUCTION_MODE'],
            idle_minutes=app.config['AUTH_IDLE_SECONDS']//60,session_hours=app.config['AUTH_ABSOLUTE_SECONDS']//3600,
            external_integrations='Non connectées',independent_security_audit=False)
