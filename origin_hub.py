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
