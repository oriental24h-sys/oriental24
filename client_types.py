"""Client classification and tracking policy; no financial rules live here."""
import re
import secrets
import sqlite3

TYPES = ('vendeur', 'societe_livraison')
TRACKING_PATTERN = r'[A-Za-z0-9][A-Za-z0-9._/\-]{0,79}'


def migrate(c):
    if 'client_type' not in {r[1] for r in c.execute('PRAGMA table_info(users)')}:
        c.execute("ALTER TABLE users ADD COLUMN client_type TEXT NOT NULL DEFAULT 'vendeur' CHECK(client_type IN ('vendeur','societe_livraison'))")
    drop_global_tracking_unique(c)
    # Fast case-insensitive search; uniqueness is enforced in code, per company.
    c.execute('DROP INDEX IF EXISTS idx_tracking_nocase')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tracking_search ON parcels(tracking COLLATE NOCASE)')
    c.execute('''CREATE TABLE IF NOT EXISTS client_type_audit(
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
        actor_id INTEGER NOT NULL REFERENCES users(id), old_type TEXT,
        new_type TEXT NOT NULL, action TEXT NOT NULL, created_at TEXT NOT NULL)''')


def drop_global_tracking_unique(c):
    """Two sociétés may share a tracking. Legacy DBs carried a global UNIQUE constraint:
    rebuild parcels once, preserving every row, column and foreign key."""
    indexes = c.execute('PRAGMA index_list(parcels)').fetchall()
    legacy = next((r for r in indexes if r[4] == 'u'), None)
    if not legacy:
        return
    ddl = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='parcels'").fetchone()[0]
    if 'tracking TEXT UNIQUE' not in ddl:
        raise RuntimeError('Schéma parcels inattendu : migration interrompue sans modification.')
    cols = ', '.join('"%s"' % r[1] for r in c.execute('PRAGMA table_info(parcels)'))
    path = next(r[2] for r in c.execute('PRAGMA database_list') if r[1] == 'main')
    raw = sqlite3.connect(path, timeout=30)
    raw.isolation_level = None
    try:
        raw.execute('PRAGMA foreign_keys=OFF')
        raw.execute('PRAGMA legacy_alter_table=ON')
        raw.execute('BEGIN')
        raw.execute('ALTER TABLE parcels RENAME TO parcels_legacy')
        raw.execute(ddl.replace('tracking TEXT UNIQUE', 'tracking TEXT', 1))
        raw.execute('INSERT INTO parcels(' + cols + ') SELECT ' + cols + ' FROM parcels_legacy')
        raw.execute('DROP TABLE parcels_legacy')
        raw.execute('COMMIT')
        problems = raw.execute('PRAGMA foreign_key_check').fetchall()
        if problems:
            raise RuntimeError('Références cassées après migration des trackings : ' + repr(problems[:3]))
        raw.execute('PRAGMA legacy_alter_table=OFF')
        raw.execute('PRAGMA foreign_keys=ON')
    except BaseException:
        raw.execute('ROLLBACK')
        raise
    finally:
        raw.close()


def parse_type(value, role, Error):
    if not isinstance(value, str) or value not in TYPES:
        raise Error('Choisissez Vendeur ou Société de livraison.')
    if role != 'client' and value != 'vendeur':
        raise Error('Le type Société de livraison est réservé aux comptes client.')
    return value


def audit(c, uid, actor, old, new, action, now):
    c.execute('INSERT INTO client_type_audit(user_id,actor_id,old_type,new_type,action,created_at) VALUES(?,?,?,?,?,?)',
              (uid, actor, old, new, action, now()))


def change_type(c, account, value, actor, Error, now):
    new = parse_type(value, account['role'], Error)
    if new != account['client_type']:
        if c.execute('SELECT 1 FROM parcels WHERE client_id=? LIMIT 1', (account['id'],)).fetchone() or c.execute('SELECT 1 FROM fulfillment_orders WHERE client_id=? LIMIT 1', (account['id'],)).fetchone():
            raise Error('Type verrouillé : ce client possède déjà des colis ou des préparations. Les suivis existants doivent être conservés.', 409)
        c.execute('UPDATE users SET client_type=? WHERE id=?', (new, account['id']))
        audit(c, account['id'], actor, account['client_type'], new, 'Type modifié avant premières commandes', now)
    return new


def tracking_text(value, Error):
    if not isinstance(value, str):
        raise Error('Le tracking doit être du texte pour conserver ses zéros initiaux.')
    value = value.strip()
    if not re.fullmatch(TRACKING_PATTERN, value):
        raise Error('Tracking obligatoire : 1 à 80 caractères, lettres A–Z, chiffres, point, tiret, underscore ou / ; commencez par une lettre ou un chiffre.')
    return value


def check_available(c, value, Error, client_id=None, ignore_order=None):
    scope = ' AND client_id=?' if client_id is not None else ''
    args = (value, client_id) if client_id is not None else (value,)
    if c.execute('SELECT 1 FROM parcels WHERE tracking=? COLLATE NOCASE' + scope, args).fetchone():
        raise Error('Ce tracking est déjà utilisé pour cette société. Aucun colis ajouté.' if client_id is not None else 'Ce tracking est déjà utilisé. Aucun colis ajouté.', 409)
    # A preparation reserves a company code before creating its parcel.
    prep = ' AND client_id=?' if client_id is not None else ''
    pargs = (ignore_order or -1, value, client_id) if client_id is not None else (ignore_order or -1, value)
    if c.execute("SELECT 1 FROM fulfillment_orders WHERE status='Réservé' AND id<>? AND json_extract(shipping,'$.tracking')=? COLLATE NOCASE" + prep, pargs).fetchone():
        raise Error('Ce tracking est déjà réservé par une préparation de cette société. Aucun colis ajouté.' if client_id is not None else 'Ce tracking est déjà réservé par une préparation. Aucun colis ajouté.', 409)


def tracking_for(c, cid, value, Error, generate=True, ignore_order=None):
    client = c.execute("SELECT client_type FROM users WHERE id=? AND role='client' AND active=1", (cid,)).fetchone()
    if not client:
        raise Error('Client actif requis.')
    if client['client_type'] == 'societe_livraison':
        tracking = tracking_text(value, Error)
        # Two different sociétés may legitimately share a code; never twice for one société.
        check_available(c, tracking, Error, client_id=cid, ignore_order=ignore_order)
        return tracking
    if value not in (None, ''):
        raise Error('Vendeur : le tracking est généré automatiquement par ORIENTAL24.')
    if not generate:
        return None
    for _ in range(32):
        tracking = 'O24-' + secrets.token_hex(5).upper()
        try:
            # ORIENTAL24-generated codes stay unique across the whole platform.
            check_available(c, tracking, Error, client_id=None)
            return tracking
        except Error as e:
            if e.code != 409:
                raise
    raise Error('Génération de tracking indisponible. Réessayez.', 409)
