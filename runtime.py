"""Explicit deployment configuration. Does not silently turn a demo database into production."""
import os, re, sqlite3
from pathlib import Path
from contextlib import closing
from datetime import timedelta
from werkzeug.middleware.proxy_fix import ProxyFix

DEMO_EMAILS = ('admin@oriental24.ma','client@oriental24.ma','livreur@oriental24.ma','sara@example.test','youssef@example.test')

def configure(app, base):
    mode = os.getenv('ORIENTAL24_MODE', 'demo')
    if mode not in ('demo', 'production'):
        raise RuntimeError('ORIENTAL24_MODE doit être demo ou production.')
    production = mode == 'production'
    key = os.getenv('SECRET_KEY', '')
    db = os.getenv('DB_PATH', str(Path(base) / 'oriental24.sqlite'))
    if production:
        if len(key) < 32:
            raise RuntimeError('Production : SECRET_KEY explicite, aléatoire et de 32 caractères minimum requis.')
        if not os.getenv('DB_PATH') or not Path(db).is_absolute() or Path(db).resolve() == (Path(base)/'oriental24.sqlite').resolve():
            raise RuntimeError('Production : DB_PATH absolu, séparé de la base de démonstration, requis.')
        parent=Path(db).resolve().parent
        if not parent.is_dir() or parent.stat().st_mode & 0o077:
            raise RuntimeError('Production : le dossier de DB_PATH doit exister et être privé (permissions 0700).')
        hosts = [h.strip() for h in os.getenv('ORIENTAL24_TRUSTED_HOSTS','').split(',') if h.strip()]
        if not hosts or any(not re.fullmatch(r'\.?[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}', h) for h in hosts):
            raise RuntimeError('Production : ORIENTAL24_TRUSTED_HOSTS doit contenir les noms de domaine autorisés, sans URL ni joker.')
        app.config['TRUSTED_HOSTS'] = hosts
        if Path(db).exists():
            with closing(sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro', uri=True)) as c:
                tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                demo = 'settings' in tables and c.execute("SELECT 1 FROM settings WHERE key='dataset_kind' AND value='demo'").fetchone()
                known = 'users' in tables and c.execute('SELECT 1 FROM users WHERE lower(email) IN (?,?,?,?,?)', DEMO_EMAILS).fetchone()
                if demo or known:
                    raise RuntimeError('Base de démonstration refusée en production. Créez une base séparée ; aucune donnée n’a été supprimée.')
    else:
        if Path(db).exists():
            with closing(sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True)) as c:
                exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='settings'").fetchone()
                if exists and c.execute("SELECT 1 FROM settings WHERE key='dataset_kind' AND value='production'").fetchone():
                    raise RuntimeError('Base production refusée en mode demo. Vérifiez ORIENTAL24_MODE.')
        keyfile=Path(base)/'.session-key'
        if not keyfile.exists():
            import secrets
            import tempfile
            fd,temporary=tempfile.mkstemp(prefix='.session-key-',dir=base)
            try:
                with os.fdopen(fd,'w') as f:f.write(secrets.token_hex(32))
                try:os.link(temporary,keyfile)
                except FileExistsError:pass
            finally:os.unlink(temporary)
        key=key or keyfile.read_text()
    try:
        hops=int(os.getenv('ORIENTAL24_PROXY_HOPS','0'))
        hours=int(os.getenv('ORIENTAL24_SESSION_HOURS','12'))
        idle=int(os.getenv('ORIENTAL24_IDLE_MINUTES','30'))
        if not 0<=hops<=3 or not 1<=hours<=24 or not 5<=idle<=120:raise ValueError()
    except ValueError:
        raise RuntimeError('Configuration invalide : proxy 0–3, session 1–24 h, inactivité 5–120 min.')
    if hops:
        # Only use behind exactly this many trusted proxies; network-isolate the backend.
        app.wsgi_app=ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=0, x_port=0, x_prefix=0)
    registration=os.getenv('ORIENTAL24_PUBLIC_REGISTRATION', '0' if production else '1')
    if registration not in ('0','1'):raise RuntimeError('ORIENTAL24_PUBLIC_REGISTRATION doit être 0 ou 1.')
    app.secret_key=key
    app.config.update(PRODUCTION_MODE=production,DEMO_MODE=not production,PUBLIC_REGISTRATION=registration=='1',
        SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=production,
        SESSION_COOKIE_NAME='__Host-o24_session' if production else 'session',
        SESSION_COOKIE_PATH='/',SESSION_COOKIE_DOMAIN=None,SESSION_REFRESH_EACH_REQUEST=False,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=hours),MAX_CONTENT_LENGTH=2*1024*1024,
        AUTH_ABSOLUTE_SECONDS=hours*3600,AUTH_IDLE_SECONDS=idle*60)
    if not production and os.getenv('PREVIEW_COOKIES')=='1':
        app.config.update(SESSION_COOKIE_SECURE=True,SESSION_COOKIE_SAMESITE='None',SESSION_COOKIE_PARTITIONED=True)
    return db
