"""Code d'étiquette unique par société — sans jamais modifier le tracking du client.

Problème réel : deux sociétés peuvent légitimement saisir le **même** tracking
(`client_types.drop_global_tracking_unique`). Un scan qui lit seulement le code brut
ne sait plus quel colis est visé et pouvait choisir le mauvais (`ORDER BY id DESC`).

Solution retenue (« option A ») :

1. **Le tracking saisi par la société reste intact** (portail, API partenaire,
   import Excel, factures, réconciliation) — aucun code ORIENTAL24 ne le remplace.
2. Chaque société reçoit un **code court** `users.company_code` (2 à 6 caractères,
   unique, insensible à la casse), attribué automatiquement et modifiable par l'Admin.
3. L'**étiquette imprimée** (QR + code-barres) porte `CODE-TRACKING` : le code-barres
   est donc unique dans tout le réseau, même si deux sociétés utilisent « ABC123 ».
4. Le **scan accepte les deux formes** :
   * `CODE-TRACKING` → résolution directe, aucune ambiguïté ;
   * `TRACKING` brut → une seule correspondance : accepté ; plusieurs : refus 409
     avec la liste des sociétés et l'invitation à scanner l'étiquette complète.
     Le système ne devine **jamais** à la place de l'opérateur.
"""

import re

CODE_RX = re.compile(r'^[A-Z0-9]{2,6}$')
_SPLIT_RX = re.compile(r'^([A-Z0-9]{2,6})-(.+)$')
_MIN_LEN = 3


def normalize(value):
    """Forme de comparaison : sans espaces, en majuscules (la casse du stockage reste intacte)."""
    return re.sub(r'\s+', '', str(value or '')).upper()


def code_of(row):
    """`company_code` tolérant (ligne sqlite3.Row, dict ou partielle)."""
    if not row:
        return None
    try:
        value = row['company_code']
    except (KeyError, IndexError, TypeError):
        return None
    value = str(value or '').strip().upper()
    return value or None


def label_code(company_code, tracking):
    """Code imprimé sur l'étiquette : `SOCIETE-TRACKING` (ou le tracking seul)."""
    code = str(company_code or '').strip().upper()
    raw = str(tracking or '').strip()
    if not code or not raw:
        return raw
    return code + '-' + raw


def split(raw):
    """Sépare un code scanné : `('SOC7', 'ABC123')` ou `(None, 'ABC123')`."""
    value = str(raw or '').strip()
    match = _SPLIT_RX.match(value.upper())
    if not match:
        return None, value
    return match.group(1), value[match.end(1) + 1:]


def _has_company_code(c):
    """La colonne peut manquer sur une base de test construite à la main."""
    try:
        return 'company_code' in {r['name'] for r in c.execute('PRAGMA table_info(users)')}
    except Exception:
        return False


def split_known(c, raw):
    """Sépare `CODE-TRACKING` **seulement** si `CODE` est un code société existant.

    Indispensable : un tracking comme « SOC-000123 » contient un tiret ; sans ce
    contrôle on le prendrait à tort pour un préfixe + « 000123 ».
    """
    value = str(raw or '').strip()
    prefix, rest = split(value)
    if not prefix:
        return None, value
    try:
        known = c.execute('SELECT 1 FROM users WHERE upper(company_code)=?', (prefix,)).fetchone()
    except Exception:
        known = None
    if not known:
        return None, value
    return prefix, rest


def validate(value, Error):
    """Contrôle du code société saisi par l'Admin."""
    code = str(value or '').strip().upper()
    if not CODE_RX.match(code):
        raise Error('Code société : 2 à 6 caractères, lettres A–Z et chiffres uniquement (ex. SOC7).', 400)
    return code


def _free(c, code, uid=None):
    row = c.execute('SELECT id FROM users WHERE upper(company_code)=? AND id IS NOT ?',
                    (code, uid)).fetchone()
    return row is None


def unique_code(c, base, uid=None):
    """Code libre dérivé d'une base (nom de société), suffixé si déjà pris."""
    letters = re.sub(r'[^A-Z0-9]', '', normalize(base)) or 'SOC'
    stem = (letters + 'SOC')[:_MIN_LEN]
    candidate = stem
    n = 0
    while not _free(c, candidate, uid):
        n += 1
        suffix = str(n)
        candidate = stem[:max(2, 6 - len(suffix))] + suffix
        if n > 900:
            raise RuntimeError('Impossible d’attribuer un code société unique.')
    return candidate


def migrate(c):
    """Colonne + index unique + attribution automatique (idempotent, à chaque démarrage)."""
    columns = {r['name'] for r in c.execute('PRAGMA table_info(users)')}
    if 'company_code' not in columns:
        c.execute('ALTER TABLE users ADD COLUMN company_code TEXT')
    try:
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_company_code_unique '
                  'ON users(upper(company_code)) WHERE company_code IS NOT NULL')
    except Exception:
        # Index d'expression indisponible : unicité garantie en code.
        pass
    backfill(c)


def backfill(c):
    """Attribue un code à chaque société cliente qui n'en a pas encore.

    Seules les sociétés de livraison en ont besoin (elles saisissent leur tracking),
    mais toutes les recevront : l'étiquette imprimée en profite aussi pour les vendeurs.
    """
    rows = c.execute("""SELECT id,company,name FROM users
                        WHERE role='client' AND (company_code IS NULL OR trim(company_code)='')
                        ORDER BY id""").fetchall()
    for row in rows:
        base = row['company'] or row['name'] or ('CL' + str(row['id']))
        code = unique_code(c, base, row['id'])
        c.execute('UPDATE users SET company_code=? WHERE id=?', (code, row['id']))


def set_code(c, uid, value, Error):
    """Attribution/mise à jour par l'Admin (unicité garantie)."""
    code = validate(value, Error)
    if not c.execute("SELECT 1 FROM users WHERE id=? AND role='client'", (uid,)).fetchone():
        raise Error('Code société réservé aux comptes client.', 400)
    if not _free(c, code, uid):
        raise Error('Ce code société est déjà utilisé par un autre compte.', 409)
    c.execute('UPDATE users SET company_code=? WHERE id=?', (code, uid))
    return code


SEARCH_SQL = ("(upper(p.tracking)=? OR (COALESCE(cl.company_code,'')<>'' "
              "AND upper(cl.company_code || '-' || p.tracking)=?))")


def lookup(c, raw, where='1=1', args=()):
    """Colis correspondant à un code scanné (étiquette `CODE-TRACKING` ou tracking brut).

    Quand l'opérateur scanne l'étiquette complète (`CODE-TRACKING`), la société est
    désignée : la recherche du tracking brut est alors bornée à cette société, donc
    aucune ambiguïté même si le même code existe ailleurs.
    """
    value = normalize(raw)
    if not value:
        return []
    has_code = _has_company_code(c)
    code_expr = "cl.company_code" if has_code else "NULL"
    base = ('SELECT p.*,cl.company company,' + code_expr + ' company_code,cl.id client_id '
            'FROM parcels p LEFT JOIN users cl ON cl.id=p.client_id WHERE ' + where + ' AND ')
    if has_code:
        # 1) l'étiquette ORIENTAL24 (`CODE-TRACKING`) d'abord : désignation explicite de la société.
        rows = c.execute(base + "upper(COALESCE(cl.company_code,'') || '-' || p.tracking)=? ORDER BY p.id DESC",
                         list(args) + [value]).fetchall()
        if rows:
            return [dict(r) for r in rows]
    # 2) sinon le tracking brut. Un tiret dans le tracking n'est donc jamais pris pour un préfixe.
    rows = c.execute(base + 'upper(p.tracking)=? ORDER BY p.id DESC', list(args) + [value]).fetchall()
    return [dict(r) for r in rows]


def describe(row):
    """Libellé court pour les messages d'ambiguïté."""
    code = code_of(row) or '—'
    company = str(row.get('company') or '—').strip()
    return code + ' (' + company + ')'


def ambiguous_message(raw, rows):
    """Message d'erreur quand un code brut existe chez plusieurs sociétés."""
    shown = ', '.join(describe(r) for r in rows[:6])
    examples = ' / '.join(label_code(code_of(r), r.get('tracking')) for r in rows[:3])
    return ('Référence « ' + str(raw).strip() + ' » utilisée par ' + str(len(rows)) +
            ' sociétés : ' + shown + '. Scannez l’étiquette ORIENTAL24 complète (' + examples +
            ') pour choisir la bonne société.')


def lookup_one(c, raw, Error, where='1=1', args=(), not_found='Aucun colis avec ce numéro de suivi.'):
    """Un seul colis attendu : 404 si absent, 409 (liste des sociétés) si ambigu."""
    rows = lookup(c, raw, where, args)
    if not rows:
        raise Error(not_found, 404)
    if len({r.get('client_id') for r in rows}) > 1:
        raise Error(ambiguous_message(raw, rows), 409)
    return rows[0]
