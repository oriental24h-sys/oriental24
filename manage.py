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


def reset_data(args):
    """Remise à zéro authentifiée par le mot de passe d'un administrateur."""
    import app as application
    import data_reset
    if args.reseed_demo and not application.app.config['DEMO_MODE']:
        raise ValueError('--reseed-demo est réservé au mode démonstration.')
    # Le script est la voie de secours quand l'écran admin est bloqué : il rappelle
    # donc où l'on écrit et ce que contient réellement la base visée.
    print('Mode : %s | base : %s' % ('production' if application.app.config['PRODUCTION_MODE'] else 'démonstration',
                                     application.app.config.get('DB_PATH', application.DB)))
    if application.app.config['PRODUCTION_MODE'] and not args.dry_run:
        print('Rappel : la double sécurité Railway (ORIENTAL24_ALLOW_DATA_RESET=1) ne concerne '
              'que l’écran web ; ce script local agit directement sur la base ci-dessus.')
    if application.app.config['DEMO_MODE'] and not args.reseed_demo:
        pass  # autorisé : la préversion peut rester vide
    with application.conn() as c:
        before = data_reset.counters(c)
        print('État actuel :')
        for table, info in before.items():
            print('  %-22s %6d  %s' % (table, info['rows'], info['label']))
        total = sum(v['rows'] for v in before.values())
        print('  %-22s %6d  %s' % ('TOTAL', total, 'lignes métier'))
        print('Tables à vider : %d' % len(data_reset.purge_targets(c)))
        print('Conservé : comptes%s, Hubs, villes, tarifs, motifs, paramètres.' %
              ('' if args.keep_accounts else ' (admin uniquement)'))
        if args.dry_run:
            print('Mode vérification : aucune suppression effectuée.')
            return
    email = (input('E-mail administrateur : ') if not args.yes else '').strip().lower()
    actor = None
    with application.conn() as c:
        if email:
            actor = c.execute("SELECT id,name,email FROM users WHERE lower(email)=? AND role='admin' AND active=1",
                              (email,)).fetchone()
            if not actor:
                raise ValueError('Administrateur introuvable ou inactif.')
            from werkzeug.security import check_password_hash
            pw = getpass.getpass('Mot de passe administrateur : ')
            if not check_password_hash(c.execute('SELECT password FROM users WHERE id=?', (actor['id'],)).fetchone()[0], pw[:129]):
                raise ValueError('Mot de passe incorrect.')
        else:
            # Mode --yes : prend le premier administrateur actif et vérifie le mot de passe
            # par variable d'environnement, jamais par argument de ligne de commande.
            actor = c.execute("SELECT id,name,email FROM users WHERE role='admin' AND active=1 ORDER BY id LIMIT 1").fetchone()
            if not actor:
                raise ValueError('Aucun administrateur actif.')
            from werkzeug.security import check_password_hash
            pw = os.environ.get('ORIENTAL24_RESET_PASSWORD', '')
            if not pw or not check_password_hash(c.execute('SELECT password FROM users WHERE id=?', (actor['id'],)).fetchone()[0], pw[:129]):
                raise ValueError('--yes exige ORIENTAL24_RESET_PASSWORD avec le mot de passe admin.')
    if not args.yes:
        typed = input('Tapez REMETTRE A ZERO pour confirmer : ').strip().upper()
        if typed != 'REMETTRE A ZERO':
            raise ValueError('Confirmation refusée : aucune donnée supprimée.')
    with application.conn() as c:
        report = data_reset.reset_operations(c, keep_accounts=args.keep_accounts,
                                             reseed_demo=args.reseed_demo,
                                             actor=dict(actor), now=datetime.now().isoformat(timespec='seconds'))
        leftover = data_reset.verify_empty(c)
    if leftover:
        raise ValueError('Remise à zéro incomplète : ' + ', '.join(sorted(leftover)))
    print('Remise à zéro terminée : %d tables vidées · empreinte SHA-256 %s' %
          (report['tables_purged'], report['fingerprint']))
    for table, info in report['after'].items():
        print('  %-22s %6d  %s' % (table, info['rows'], info['label']))
    if report['reseeded']:
        print('Jeu de démonstration réinjecté.')
    print('Recommandation : redémarrez le service (un seul worker gunicorn) pour repartir sur un cache propre.')


def main():
    parser=argparse.ArgumentParser(description='ORIENTAL24 — outils locaux d’exploitation')
    subs=parser.add_subparsers(dest='command',required=True)
    for name in ['backup','restore']:
        p=subs.add_parser(name);p.add_argument('--source',required=True);p.add_argument('--destination',required=True)
    p=subs.add_parser('verify');p.add_argument('--source',required=True)
    p=subs.add_parser('init-admin');p.add_argument('--email',required=True);p.add_argument('--name',required=True)
    p=subs.add_parser('reset-password');p.add_argument('--email',required=True)
    p=subs.add_parser('reset-data',help='Remise à zéro des données métier (commandes, bons, factures…)')
    p.add_argument('--keep-accounts',action='store_true',default=False,
                   help='Conserver tous les comptes (clients, livreurs, supports). Par défaut seul l’admin reste.')
    p.add_argument('--reseed-demo',action='store_true',default=False,
                   help='Réinjecter le jeu de démonstration après la purge (mode démo uniquement).')
    p.add_argument('--dry-run',action='store_true',default=False,
                   help='Afficher les compteurs sans rien supprimer.')
    p.add_argument('--yes',action='store_true',default=False,
                   help='Ne pas demander la confirmation interactive (usage scripté).')
    subs.add_parser('prune-security')
    args=parser.parse_args()
    try:
        if args.command in ['backup','restore']:
            snapshot(args.source,args.destination,args.command=='restore');return
        if args.command=='verify':check_database(args.source);print('Intégrité et références : OK');return
        if args.command=='reset-data':
            reset_data(args);return
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
    except (ValueError,RuntimeError,sqlite3.Error,OSError,EOFError) as e:
        parser.exit(1,'Erreur : '+str(e)+'\n')

if __name__=='__main__':main()
