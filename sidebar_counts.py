"""Actionable sidebar counters. Counts are server-scoped, never browser totals.
No counter is emitted for settings, archives, analytics or other non-task pages.
"""
from flask import jsonify


def sidebar_counts(c, u, scope):
    role, uid = u['role'], u['id']
    counts = {}
    def count(key, table, where='1=1', args=()):
        counts[key] = c.execute(f'SELECT count(*) FROM {table} WHERE {where}', args).fetchone()[0]
    # Never fall back to a global scope for a manager without an active Hub.
    if role == 'agent' and not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1', (u.get('agent_hub_id'),)).fetchone():
        return counts
    cond, args = scope(u, c=c)
    pending = "p.status NOT IN ('Livré','Retourné','Refusé','Annulé')"
    count('support-orders' if role == 'support' else 'parcels', 'parcels p', f'({cond}) AND {pending}', args)
    if role == 'support':
        return counts
    if role == 'livreur':
        counts['driver-app'] = counts['parcels']
    # Tickets match the exact ownership rule of GET /tickets.
    own, ownargs = ('1=1', []) if role == 'admin' else ('user_id=?', [uid])
    count('tickets', 'tickets', f"({own}) AND status NOT IN ('Fermé','Résolu','Clôturé')", ownargs)
    if role in ('admin', 'client'):
        for table, owner in [('requests','user_id'), ('recipient_change_requests','client_id')]:
            where, params = ('1=1', []) if role == 'admin' else (owner+'=?', [uid])
            counts['tickets'] += c.execute(f"SELECT count(*) FROM {table} WHERE ({where}) AND status='En attente'", params).fetchone()[0]
        where, params = ('1=1', []) if role == 'admin' else ('client_id=?', [uid])
        count('invoices', 'invoices', f"({where}) AND status IN ('À régler','Partiellement réglée')", params)
        count('stock', 'stock_requests', f"({where}) AND status='En attente'", params)
        count('fulfillment', 'fulfillment_orders', f"({where}) AND status='Réservé'", params)
        count('pickups', 'ramassage_bons', f"({where}) AND status IN ('Brouillon','Confirmé','En cours')", params)
    if role in ('admin', 'agent', 'client'):
        # Same destination/owner constraints as the palette list endpoints.
        where, params = ('1=1', []) if role == 'admin' else ('d.destination_hub_id=?', [u.get('agent_hub_id')]) if role == 'agent' else ('d.client_id=?', [uid])
        partner_states = "('Préparé','En transit','Partiellement reçu')" if role == 'client' else "('En transit','Partiellement reçu')"
        count('partner-palettes', 'ops_documents d', f"({where}) AND d.kind='partner_palette' AND d.status IN {partner_states}", params)
        count('return-palettes', 'ops_documents d', f"({where}) AND d.kind='return_palette' AND d.status IN ('Préparé','En transit','Partiellement remis')", params)
    if role in ('admin', 'agent'):
        where, params = ('1=1', []) if role == 'admin' else ('d.destination_hub_id=?', [u.get('agent_hub_id')])
        count('palette-hub', 'ops_documents d', f"({where}) AND d.kind='transfer' AND d.status IN ('Départ partiel','En transit','Partiellement reçu')", params)
        where, params = ('1=1', []) if role == 'admin' else ('hub_id=?', [u.get('agent_hub_id')])
        count('ramassage-reception', 'ramassage_bons', f"({where}) AND status IN ('Confirmé','En cours')", params)
    if role in ('admin', 'agent', 'client', 'livreur'):
        where, params = ('1=1', []) if role == 'admin' else ("kind='transfer' AND (source_hub_id=? OR destination_hub_id=?)", [u.get('agent_hub_id')]*2) if role == 'agent' else ("kind!='transfer' AND client_id=?", [uid]) if role == 'client' else ('driver_id=?', [uid])
        count('documents', 'ops_documents', f"({where}) AND status IN ('Préparé','Départ partiel','En transit','Partiellement reçu')", params)
    if role in ('admin', 'agent', 'livreur'):
        where, params = ('1=1', []) if role == 'admin' else ('s.hub_id=?', [u.get('agent_hub_id')]) if role == 'agent' else ('s.driver_id=?', [uid])
        count('hub-driver-statements' if role == 'agent' else 'driver-finance', 'driver_statements s',
              f"({where}) AND s.cancelled_at IS NULL AND (s.cash_due_cents > COALESCE((SELECT sum(t.amount_cents) FROM driver_transactions t WHERE t.statement_id=s.id AND t.kind='cash' AND t.voided_at IS NULL),0) OR s.commission_due_cents > COALESCE((SELECT sum(t.amount_cents) FROM driver_transactions t WHERE t.statement_id=s.id AND t.kind='commission' AND t.voided_at IS NULL),0))", params)
    count('notifications', 'ops_notifications', 'user_id=? AND read_at IS NULL', [uid])
    return counts


def register_sidebar_counts(app, services):
    @app.get('/api/sidebar-counts')
    @services['auth']()
    def get_sidebar_counts():
        u = services['user']()
        with services['conn']() as c:
            counts = sidebar_counts(c, u, services['scope'])
        if u['role'] in ('admin', 'agent') and counts:
            # Reuse the reviewed, Hub-scoped alert rules instead of duplicating thresholds.
            data = app.view_functions['alerts']().get_json()
            counts['alerts'] = sum(len(g['items']) for g in data['groups'])
            collected = app.view_functions['ramassage_collected']().get_json()['counts']
            counts['ramassage-collected'] = sum(collected.get(k, 0) for k in ('at_hub', 'prepared', 'review'))
        return jsonify(counts=counts)
