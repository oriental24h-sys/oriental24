"""Hub d'origine automatique d'une CMD créée.

Règle métier : toute nouvelle CMD reçoit **immédiatement** un Hub d'origine, sans saisie
manuelle et sans attendre sa première arrivée physique.

Ordre de décision :
1. le Hub demandé explicitement (Admin), s'il est actif ;
2. le Hub du responsable qui crée la CMD ;
3. le **Hub Central** actif (point d'entrée du réseau) ;
4. s'il n'existe qu'un seul Hub actif, celui-ci ;
5. sinon : aucune origine (la CMD reste « origine à vérifier », jamais devinée).
"""


def _active(c, hub_id):
    if type(hub_id) is not int or hub_id <= 0:
        return None
    row = c.execute('SELECT * FROM ops_hubs WHERE id=? AND active=1', (hub_id,)).fetchone()
    return dict(row) if row else None


def central_hub(c):
    try:
        row = c.execute("SELECT value FROM settings WHERE key='central_hub_id'").fetchone()
    except Exception:
        return None
    raw = row['value'] if row is not None else None
    if raw is None or not str(raw).strip().isdigit():
        return None
    return _active(c, int(str(raw).strip()))


def resolve(c, requested=None, actor=None):
    """Retourne l'id du Hub d'origine à enregistrer, ou None."""
    if type(requested) is int and requested > 0:
        hub = _active(c, requested)
        if hub:
            return hub['id']
    if actor:
        hub = _active(c, actor.get('agent_hub_id'))
        if hub:
            return hub['id']
    hub = central_hub(c)
    if hub:
        return hub['id']
    rows = [dict(r) for r in c.execute('SELECT id FROM ops_hubs WHERE active=1 ORDER BY id')]
    if len(rows) == 1:
        return rows[0]['id']
    return None


def resolve_or_keep(c, requested=None, actor=None):
    """Comme resolve(), sans jamais lever d'exception (création de colis jamais bloquée)."""
    try:
        return resolve(c, requested=requested, actor=actor)
    except Exception:
        return None


def _first_documented_hub(c, parcel_id):
    """Premier Hub physiquement documenté pour un colis (jamais son Hub courant).

    Preuves acceptées : réception d'une palette, scan de départ d'une palette,
    réception par un livreur. En cas d'égalité entre plusieurs Hubs, aucune
    origine n'est devinée.
    """
    events = []

    def _collect(sql, args):
        try:
            for row in c.execute(sql, args).fetchall():
                hub_id, event_at = row['hub_id'], row['event_at']
                if type(hub_id) is int and hub_id > 0 and event_at:
                    events.append((str(event_at), hub_id))
        except Exception:
            pass

    _collect('''SELECT d.destination_hub_id hub_id,l.received_at event_at
                FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                WHERE l.parcel_id=? AND l.received_at IS NOT NULL AND d.destination_hub_id IS NOT NULL''', (parcel_id,))
    _collect('''SELECT d.source_hub_id hub_id,l.departure_scanned_at event_at
                FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                WHERE l.parcel_id=? AND l.departure_scanned_at IS NOT NULL AND d.source_hub_id IS NOT NULL''', (parcel_id,))
    _collect('''SELECT hub_id,received_at event_at FROM driver_receipts
                WHERE parcel_id=? AND hub_id IS NOT NULL AND received_at IS NOT NULL''', (parcel_id,))
    if not events:
        return None
    first = min(stamp for stamp, _ in events)
    hubs = {hub for stamp, hub in events if stamp == first}
    return next(iter(hubs)) if len(hubs) == 1 else None


def ensure_parcel_origin(c, parcel_id):
    """Garantit qu'un colis existant possède son vrai Hub d'origine.

    Utilisé avant de créer une reprise `EC…` : l'origine de la reprise doit être
    celle de la CMD livrée, jamais le Hub du scan de livraison.
    """
    row = c.execute('SELECT * FROM parcels WHERE id=?', (parcel_id,)).fetchone()
    if not row:
        return None
    columns = {r['name'] for r in c.execute('PRAGMA table_info(parcels)')}
    if 'origin_hub_id' not in columns:
        return None
    current = row['origin_hub_id']
    if _active(c, current):
        return current
    hub_id = _first_documented_hub(c, parcel_id)
    if hub_id and not _active(c, hub_id):
        hub_id = None
    if not hub_id:
        hub_id = resolve_or_keep(c, None, None)
    if hub_id:
        try:
            c.execute('UPDATE parcels SET origin_hub_id=? WHERE id=? AND origin_hub_id IS NULL', (hub_id, parcel_id))
        except Exception:
            pass
    return hub_id
