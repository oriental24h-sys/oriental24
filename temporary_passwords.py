"""Admin-generated credentials: hash-only storage, one response, no read-back endpoint."""
import secrets
from flask import request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash


def generate_temporary_password():
    return 'O24!'+secrets.token_urlsafe(18)


def credential_response(uid,email,password):
    response=jsonify(ok=True,id=uid,email=email,temporary_password=password)
    response.headers['Cache-Control']='no-store, private, max-age=0'
    response.headers['Pragma']='no-cache'
    return response


def register_temporary_passwords(app,s):
    conn,auth,user,Error=s['conn'],s['auth'],s['user'],s['APIError']
    @app.post('/api/users/<int:uid>/reset-password')
    @auth('admin')
    def admin_temporary_password(uid):
        actor=user();d=request.get_json(silent=True)
        if not isinstance(d,dict) or d.get('confirmed') is not True:raise Error('Confirmez la réinitialisation.')
        password=d.get('current_password')
        if not isinstance(password,str) or len(password)>128:raise Error('Votre mot de passe Admin est requis.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            admin=c.execute("SELECT password FROM users WHERE id=? AND role='admin' AND active=1",(actor['id'],)).fetchone()
            if not admin or not check_password_hash(admin['password'],password):raise Error('Votre mot de passe Admin est incorrect.',403)
            target=c.execute('SELECT id,email,role FROM users WHERE id=?',(uid,)).fetchone()
            if not target or target['role']=='admin':raise Error('Ce compte ne peut pas être réinitialisé ici.',403)
            temporary=generate_temporary_password()
            c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(temporary),uid))
            s['security_revoke_user'](c,uid,'Mot de passe réinitialisé par Admin : anciennes sessions révoquées',actor['id'])
        return credential_response(uid,target['email'],temporary)
