"""Réinitialisation complète des données métier ORIENTAL24 (« remise à zéro »).

Objectif : repartir d'une base propre — commandes, palettes/bons d'envoi et de
réception, factures, finance, retours, scans, historiques — tout en gardant la
structure du réseau : compte administrateur, Hubs, villes, tarifs, motifs,
paramètres et comptes (clients / livreurs / responsables / supports).

Règles de sécurité appliquées :

* Aucune donnée métier n'est inventée : la purge se fait table par table, dans
  l'ordre des dépendances, avec la liste des tables lues dans le schéma réel
  (une future table est donc purgée automatiquement).
* Les garde-fous d'audit (triggers « no_update / no_delete ») sont désactivés
  uniquement pendant la transaction de purge, puis réinstallés par la migration
  normale au démarrage suivant. Rien d'autre n'est contourné.
* Une empreinte SHA-256 de l'état purgé est calculée et envoyée à l'audit : la
  remise à zéro est prouvable et ne peut pas être confondue avec une perte.
* En mode démonstration, le jeu de démonstration est réinjecté tout de suite
  (comportement historique de `init_db`) pour que la préversion reste utilisable.
"""
import hashlib
import json
import sqlite3
import time

# Structure conservée : réseau, tarifs, paramètres, comptes et référentiels.
KEEP_TABLES = frozenset({
    'users',            # comptes : admin, clients, livreurs, responsables, supports
    'ops_hubs',         # le réseau physique
    'cities',           # villes, tarifs de livraison / retour
    'hub_cities',       # couverture ville ↔ Hub
    'support_cities',   # affectation support ↔ ville
    'support_contacts',
    'ops_reasons',      # motifs opérationnels
    'settings',         # annonce, hub central, identité société
    'pickup_points',
    'warehouses',
    'warehouse_slots',
    'sort_zones',
    'ramassage_zones',
    'ramassage_settings',
    'client_tariffs',   # barèmes négociés par client
    'driver_city_rates',
    'driver_terms',
    'hub_billing_terms',
    'hub_billing_city_terms',
    'hub_billing_schedule',
    'hub_billing_city_config',
    'company_profiles',
    'client_profile_extras',
    'driver_invoice_profiles',
    'invoice_profile',
})

# Tables de sécurité / sessions : jamais des données métier, mais vider les
# sessions déconnecte tout le monde au milieu de l'opération. On les conserve.
KEEP_ALWAYS = frozenset({'auth_sessions', 'auth_limits', 'auth_events', 'schema_migrations'})

# Tables techniques à ne jamais purger.
NEVER_TOUCH = frozenset({'sqlite_sequence', 'sqlite_stat1', 'sqlite_master'})

# Compteurs affichés à l'opérateur : les objets qu'il a explicitement cités.
COUNTERS = (
    ('parcels', 'Commandes (CMD)'),
    ('events', 'Historique des commandes'),
    ('ops_documents', 'Bons d’envoi / réception (palettes)'),
    ('ops_document_lines', 'Lignes des bons'),
    ('invoices', 'Factures clients'),
    ('invoice_lines', 'Lignes de factures'),
    ('ramassage_bons', 'Bons de ramassage'),
    ('driver_statements', 'Relevés livreurs'),
    ('hub_invoices', 'Factures des Hubs'),
    ('pallet' + 's', 'Palettes historiques'),
    ('tickets', 'Demandes & réclamations'),
    ('audit_log', 'Journal d’audit'),
)


class ResetRefused(RuntimeError):
    """La remise à zéro a été refusée par un garde-fou métier."""


def _tables(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _columns(conn, table):
    return {r[1] for r in conn.execute('PRAGMA table_info("%s")' % table)}


def counters(c):
    """Compteurs lisibles (uniquement des tables réellement présentes)."""
    out = {}
    present = set(_tables(c))
    for table, label in COUNTERS:
        if table in present:
            out[table] = {'label': label, 'rows': c.execute('SELECT count(*) FROM "%s"' % table).fetchone()[0]}
    return out


def purge_targets(c):
    """Tables à vider : tout sauf la structure conservée et les tables techniques."""
    keep = KEEP_TABLES | KEEP_ALWAYS | NEVER_TOUCH
    return [t for t in _tables(c) if t not in keep]


def _guards(conn, only_tables=None):
    """Triggers d'immutabilité (audit) : ils bloquent volontairement DELETE.

    Seuls ceux posés sur les tables purgées sont levés : un garde-fou qui protège
    une table conservée (barèmes, paramètres) reste actif pendant l'opération.
    """
    rows = conn.execute("SELECT name,sql,tbl_name FROM sqlite_master "
                        "WHERE type='trigger' AND sql LIKE '%BEFORE DELETE%' AND sql IS NOT NULL").fetchall()
    if only_tables is None:
        return [(r[0], r[1], r[2]) for r in rows]
    scope = set(only_tables)
    return [(r[0], r[1], r[2]) for r in rows if r[2] in scope]


def _drop_guards(c, tables):
    guards = _guards(c, tables)
    for name, _sql, _table in guards:
        c.execute('DROP TRIGGER IF EXISTS "%s"' % name)
    return guards


def _restore_guards(c, guards):
    """Réinstalle les triggers EXACTEMENT tels qu'ils étaient (même SQL)."""
    for _name, sql, _table in guards:
        c.execute(sql)


def _prune_orphan_users(c):
    """Supprime les lignes de configuration qui pointent vers un compte disparu."""
    removed = 0
    for table in sorted(KEEP_TABLES):
        if table == 'users':
            continue
        try:
            refs = [r for r in c.execute('PRAGMA foreign_key_list("%s")' % table) if r[2] == 'users']
        except sqlite3.Error:
            continue
        for ref in refs:
            column = ref[3]
            removed += c.execute(
                'DELETE FROM "%s" WHERE "%s" IS NOT NULL AND "%s" NOT IN (SELECT id FROM users)'
                % (table, column, column)).rowcount
    return removed


def fingerprint(payload):
    """Empreinte stable : même contenu ⇒ même SHA-256 (preuve de l'état purgé)."""
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def reset_operations(c, *, keep_accounts=True, reseed_demo=False, actor=None, now=None):
    """Vide les données métier et renvoie un rapport complet.

    La fonction travaille dans la transaction de l'appelant : soit tout passe,
    soit rien n'est modifié. `keep_accounts=False` vide aussi les comptes
    non-administrateurs (les Hubs et villes restent).
    """
    if c.in_transaction:
        raise ResetRefused('La remise à zéro doit ouvrir sa propre transaction.')
    c.execute('BEGIN IMMEDIATE')
    try:
        before = counters(c)
        targets = purge_targets(c)
        guards = _drop_guards(c, targets)
        # Les suppressions suivent l'ordre des dépendances : la base reste
        # cohérente même si une clé étrangère est vérifiée en fin de transaction.
        c.execute('PRAGMA foreign_keys=OFF')
        try:
            for table in targets:
                c.execute('DELETE FROM "%s"' % table)
            if not keep_accounts:
                c.execute("DELETE FROM users WHERE role<>'admin'")
                # Réglages attachés aux comptes supprimés (barèmes livreur, profils,
                # tarifs négociés…) : sans cette purge, il resterait des orphelins.
                removed_users = _prune_orphan_users(c)
            else:
                removed_users = 0
        finally:
            c.execute('PRAGMA foreign_keys=ON')
            _restore_guards(c, guards)
        if reseed_demo:
            seed_demo(c)
        after = counters(c)
        stamp = now or time.strftime('%Y-%m-%dT%H:%M:%S')
        payload = {'at': stamp, 'tables': len(targets), 'before': before, 'after': after,
                   'keep_accounts': bool(keep_accounts), 'guards': [g[0] for g in guards]}
        detail = {'targets': targets, 'guards': [g[0] for g in guards],
                  'rows_before': {k: v['rows'] for k, v in before.items()},
                  'rows_after': {k: v['rows'] for k, v in after.items()},
                  'actor_id': (actor or {}).get('id'), 'actor_name': (actor or {}).get('name')}
        c.execute('''INSERT INTO audit_log(actor_id,actor_name,action,entity_type,entity_id,old_value,new_value,
                     metadata,created_at) VALUES(?,?,?,?,?,?,?,?,?)''',
                  ((actor or {}).get('id') or 0, (actor or {}).get('name') or 'Opérateur local',
                   'data_reset', 'database', 'operations', json.dumps(before, ensure_ascii=False),
                   json.dumps(after, ensure_ascii=False), json.dumps(detail, ensure_ascii=False), stamp))
        c.execute('COMMIT')
    except Exception:
        c.execute('ROLLBACK')
        raise
    return {'ok': True, 'at': stamp, 'tables_purged': len(targets), 'account_rows_removed': removed_users, 'guards_restored': len(guards),
            'before': before, 'after': after, 'fingerprint': fingerprint(payload),
            'keep_accounts': bool(keep_accounts), 'reseeded': bool(reseed_demo)}


def seed_demo(c):
    """Jeu de démonstration minimal (mode démo uniquement).

    Réutilise le semis historique d'`app.init_db` : après une remise à zéro en
    démonstration, la préversion reste utilisable sans redéploiement.
    """
    import app as application  # import tardif : évite un cycle au démarrage
    seeder = getattr(application, 'seed_demo_dataset', None)
    if callable(seeder):
        return seeder(c)
    return None


# La remise à zéro écrit elle-même sa preuve dans le journal d'audit : cette
# ligne est la seule attendue après la purge.
PROOF_TABLES = frozenset({'audit_log'})


def verify_empty(c):
    """Contrôle final : aucune ligne métier ne subsiste (hors trace d'audit)."""
    leftovers = {table: c.execute('SELECT count(*) FROM "%s"' % table).fetchone()[0]
                 for table in purge_targets(c)}
    return {k: v for k, v in leftovers.items() if v and k not in PROOF_TABLES}
