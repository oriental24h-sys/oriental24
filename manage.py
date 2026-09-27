"""Local operator tools. Passwords are read interactively, never from command-line arguments."""
import argparse,getpass,hashlib,os,re,sqlite3,tempfile,time
from pathlib import Path
from contextlib import closing
from datetime import datetime

def check_database(path):
    path=Path(path).resolve()
    if not path.is_file():raise ValueError('Base source introuvable.')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as c:
        if c.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise ValueError('Échec du contrôle d’intégrité SQLite.')
        if c.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Références étrangères incohérentes.')
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone():raise ValueError('Base ORIENTAL24 non reconnue.')
    return path

def snapshot(source,destination,restore=False):
    source=check_database(source);destination=Path(destination).resolve()
    if source==destination or destination.exists():raise ValueError('La destination doit être un NOUVEAU fichier. Aucune base existante ne sera écrasée.')
    if not destination.parent.is_dir():raise ValueError('Créez d’abord le dossier de destination privé.')
    # Snapshot API includes committed WAL content; no unsafe raw copy of an active SQLite file.
    with tempfile.TemporaryDirectory(prefix='.o24-copy-',dir=destination.parent) as td:
        temp=Path(td)/'snapshot.sqlite'
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(temp)) as b:
            a.backup(b)
            if restore and b.execute("SELECT 1 FROM sqlite_master WHERE name='auth_sessions'").fetchone():
                b.execute("UPDATE auth_sessions SET revoked_at=?,revoke_reason='Restauration : reconnexion obligatoire' WHERE revoked_at IS NULL",(int(time.time()),))
                b.commit()
        check_database(temp);os.chmod(temp,0o600)
        os.link(temp,destination)  # Atomic, no overwrite even if another process creates the path.
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    print(('Restauration vers nouveau fichier' if restore else 'Sauvegarde cohérente')+' : '+str(destination))
    print('Intégrité OK · permissions 0600 · SHA256 '+digest)
    if restore:print('Sessions révoquées. Vérifiez comptes/droits/mots de passe restaurés avant de relancer le service.')
    return destination

def password():
    first=getpass.getpass('Nouveau mot de passe (14–128 caractères) : ')
    second=getpass.getpass('Confirmer le mot de passe : ')
    if first!=second or not 14<=len(first)<=128:raise ValueError('Confirmation différente ou longueur invalide.')
    return first

def main():
    parser=argparse.ArgumentParser(description='ORIENTAL24 — outils locaux d’exploitation')
    subs=parser.add_subparsers(dest='command',required=True)
    for name in ['backup','restore']:
        p=subs.add_parser(name);p.add_argument('--source',required=True);p.add_argument('--destination',required=True)
    p=subs.add_parser('verify');p.add_argument('--source',required=True)
    p=subs.add_parser('init-admin');p.add_argument('--email',required=True);p.add_argument('--name',required=True)
    p=subs.add_parser('reset-password');p.add_argument('--email',required=True)
    subs.add_parser('prune-security')
    args=parser.parse_args()
    try:
        if args.command in ['backup','restore']:
            snapshot(args.source,args.destination,args.command=='restore');return
        if args.command=='verify':check_database(args.source);print('Intégrité et références : OK');return
        import app
        from werkzeug.security import generate_password_hash
        if args.command=='prune-security':
            cutoff=int(time.time())-90*86400
            with app.conn() as c:
                c.execute('DELETE FROM auth_limits WHERE expires_at<?',(int(time.time()),))
                c.execute('DELETE FROM auth_events WHERE created_at<?',(cutoff,))
                c.execute('DELETE FROM auth_sessions WHERE expires_at<? OR revoked_at<?',(cutoff,cutoff))
            print('Traces de sécurité de plus de 90 jours purgées ; sessions actives et données métier conservées.');return
        email=args.email.strip().lower()
        if len(email)>254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):raise ValueError('E-mail invalide.')
        if args.command=='init-admin':
            if not app.app.config['PRODUCTION_MODE']:raise ValueError('init-admin est réservé au mode production, sur une base distincte de la démo.')
            if not args.name.strip() or len(args.name.strip())>160:raise ValueError('Nom invalide.')
        pw_hash=generate_password_hash(password())
        with app.conn() as c:
            c.execute('BEGIN IMMEDIATE')
            if args.command=='init-admin':
                if c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():raise ValueError('Un administrateur existe déjà. Aucun remplacement automatique.')
                c.execute("INSERT INTO users(name,email,password,role,company,created_at) VALUES(?,?,?,'admin','ORIENTAL24',?)",(args.name.strip(),email,pw_hash,datetime.now().isoformat(timespec='seconds')))
            else:
                u=c.execute('SELECT id FROM users WHERE lower(email)=?',(email,)).fetchone()
                if not u:raise ValueError('Compte introuvable.')
                c.execute('UPDATE users SET password=? WHERE id=?',(pw_hash,u['id']))
                c.execute("UPDATE auth_sessions SET revoked_at=?,revoke_reason='Mot de passe réinitialisé par opérateur local' WHERE user_id=? AND revoked_at IS NULL",(int(time.time()),u['id']))
                c.execute("INSERT INTO auth_events(user_id,action,network,created_at) VALUES(?,'Mot de passe réinitialisé par opérateur local','Opérateur local',?)",(u['id'],int(time.time())))
        print('Administrateur initial créé.' if args.command=='init-admin' else 'Mot de passe modifié, toutes les sessions révoquées. Activation du compte inchangée.')
    except (ValueError,RuntimeError,sqlite3.Error,OSError) as e:
        parser.exit(1,'Erreur : '+str(e)+'\n')

if __name__=='__main__':main()
