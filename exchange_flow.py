"""Commande avec échange : reprise automatique, réception au Hub puis retour vendeur.

Règle métier :
- une commande marquée « échange » qui passe à **Livré** génère une commande jumelle
  (mêmes informations) dont le tracking devient **EC + tracking livré** ;
- cette reprise est immédiatement comptée sur le livreur qui vient de livrer : il doit
  récupérer l'ancien article chez le destinataire (alerte sonore « Récupère échange ») ;
- le responsable de Hub la réceptionne ensuite (`Échange Réceptionné`) : elle quitte
  le livreur et devient un colis du Hub, disponible pour une palette retour vers le
  vendeur, exactement comme un retour classique.

Aucun COD n'est encaissé sur la reprise : elle n'est jamais « Livré ».
"""
import re

from parcel_statuses import EXCHANGE_TO_RECOVER, EXCHANGE_RECEIVED, EXCHANGE_STATUSES

MAX_TRACKING = 72


def migrate(c):
    """Additive migration: reprise link and reception timestamp."""
    cols = {r['name'] for r in c.execute('PRAGMA table_info(parcels)')}
    if 'exchange_of_id' not in cols:
        c.execute('ALTER TABLE parcels ADD COLUMN exchange_of_id INTEGER REFERENCES parcels(id)')
    if 'exchange_received_at' not in cols:
        c.execute('ALTER TABLE parcels ADD COLUMN exchange_received_at TEXT')
    c.execute('CREATE INDEX IF NOT EXISTS idx_parcels_exchange_of ON parcels(exchange_of_id,id)')


def exchange_tracking(c, source_tracking):
    """EC + tracking d'origine, rendu unique sans jamais réutiliser un tracking existant."""
    raw = re.sub(r'\s+', '', str(source_tracking or ''))
    base = ('EC' + raw).upper()[:MAX_TRACKING] or 'EC'
    candidate, n = base, 1
    while c.execute('SELECT 1 FROM parcels WHERE upper(tracking)=?', (candidate,)).fetchone():
        n += 1
        candidate = ('%s-%d' % (base, n))[:MAX_TRACKING]
        if n > 99:
            raise ValueError('Impossible de générer un tracking échange unique.')
    return candidate


def existing(c, source_id):
    return c.execute('SELECT * FROM parcels WHERE exchange_of_id=? ORDER BY id LIMIT 1', (source_id,)).fetchone()


def summary(c, row):
    city = c.execute('SELECT name FROM cities WHERE id=?', (row['city_id'],)).fetchone() if row['city_id'] else None
    return dict(id=row['id'], tracking=row['tracking'], status=row['status'],
                recipient=row['recipient'] or '', phone=row['phone'] or '',
                city=city['name'] if city else '', amount=row['amount'],
                created_at=row['created_at'])


def _driver_hub(c, driver_id):
    if not driver_id:
        return None
    row = c.execute("SELECT driver_hub_id FROM users WHERE id=? AND role='livreur' AND active=1", (driver_id,)).fetchone()
    if row and type(row['driver_hub_id']) is int and row['driver_hub_id'] > 0:
        if c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1', (row['driver_hub_id'],)).fetchone():
            return row['driver_hub_id']
    return None


def create_for_delivery(c, pid, actor, event, now, audit=None):
    """Create the automatic exchange recovery order for a parcel just set to Livré.

    Idempotent: a second call returns the existing recovery order without duplicating
    it (replay of a delivery request, retry after a network error, etc.).
    """
    p = c.execute('SELECT * FROM parcels WHERE id=?', (pid,)).fetchone()
    if not p:
        return None
    if p['status'] != 'Livré':
        return None
    if not p['is_exchange']:
        return None
    if p['exchange_of_id']:
        # A recovery order is never the source of another recovery order.
        return None
    prior = existing(c, pid)
    if prior:
        return summary(c, prior)
    driver_id = actor['id'] if actor and actor.get('role') == 'livreur' else p['driver_id']
    hub_id = _driver_hub(c, driver_id) or p['current_hub_id']
    if hub_id and not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1', (hub_id,)).fetchone():
        hub_id = None
    t = now()
    tracking = exchange_tracking(c, p['tracking'])
    eid = c.execute('''INSERT INTO parcels(tracking,client_id,driver_id,recipient,phone,address,city_id,amount,
        fee,return_fee,status,product,note,created_at,updated_at,current_hub_id,open_allowed,is_exchange,exchange_of_id)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (tracking, p['client_id'], driver_id, p['recipient'], p['phone'], p['address'], p['city_id'],
         p['amount'], p['fee'], p['return_fee'], EXCHANGE_TO_RECOVER, p['product'], p['note'],
         t, t, hub_id, p['open_allowed'] if 'open_allowed' in p.keys() else 1, 1, pid)).lastrowid
    event(c, eid, EXCHANGE_TO_RECOVER,
          'Reprise échange créée après la livraison de ' + str(p['tracking']) +
          ' · à récupérer chez le destinataire puis à réceptionner au Hub.', actor)
    event(c, pid, 'Livré',
          'Échange : commande de reprise ' + tracking + ' créée et comptée sur le livreur.', actor)
    if audit:
        try:
            audit(c, actor_id=actor['id'], actor_name=actor['name'], action='exchange_parcel_created',
                  entity_type='parcel', entity_id=str(eid),
                  old_value={'source_parcel_id': pid},
                  new_value={'tracking': tracking, 'driver_id': driver_id, 'hub_id': hub_id},
                  metadata={'source_tracking': p['tracking']}, created_at=t)
        except Exception:
            pass
    row = c.execute('SELECT * FROM parcels WHERE id=?', (eid,)).fetchone()
    return summary(c, row)


def mark_received(c, pid, actor, event, now):
    """Hub reception of the recovery order: it leaves the courier's custody."""
    p = c.execute('SELECT * FROM parcels WHERE id=?', (pid,)).fetchone()
    if not p or not p['exchange_of_id']:
        return None
    if p['status'] != EXCHANGE_RECEIVED:
        return None
    t = now()
    hub_id = p['current_hub_id']
    if actor and actor.get('role') == 'agent' and actor.get('agent_hub_id'):
        hub_id = actor['agent_hub_id']
    c.execute('UPDATE parcels SET driver_id=NULL,current_hub_id=?,exchange_received_at=?,updated_at=? WHERE id=?',
              (hub_id, t, t, pid))
    event(c, pid, EXCHANGE_RECEIVED,
          'Reprise échange réceptionnée au Hub · retirée du livreur · prête pour une palette retour vers le vendeur.',
          actor)
    return dict(id=pid, tracking=p['tracking'], hub_id=hub_id)


def is_exchange_parcel(p):
    return bool(p and p.get('exchange_of_id'))
