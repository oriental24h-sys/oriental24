"""Stock-order history derives from the recorded reservation and preparation.

Reconstruct legacy missing entries at read time: never rewrite a parcel's live
status, its existing events, inventory movements, or notifications.
"""


def initial_stock_events(order):
    reference = 'PREP-' + str(order['id'])
    return [
        dict(status='Créé', actor_id=order['created_by'], created_at=order['created_at'],
             note='Commande créée depuis le stock · produits réservés · ' + reference,
             timeline_order=-2),
        dict(status='Confirmé', actor_id=order['processed_by'], created_at=order['processed_at'],
             note='Commande confirmée au Hub Central · contrôle des produits et quantités validé · ' + reference,
             timeline_order=-1),
    ]


def record_stock_initial_events(c, order):
    """Called inside the successful preparation transaction, before Ramassé.

    Créé uses the original reservation timestamp/author, not the preparation
    operator. Confirmé records the explicit physical-check validation.
    """
    for event in initial_stock_events(order):
        c.execute('INSERT INTO events(parcel_id,actor_id,status,note,created_at) VALUES(?,?,?,?,?)',
                  (order['parcel_id'], event['actor_id'], event['status'], event['note'], event['created_at']))


def complete_stock_timeline(c, parcel_id, events):
    order = c.execute('SELECT * FROM fulfillment_orders WHERE parcel_id=?', (parcel_id,)).fetchone()
    if not order:
        return events
    # Do not invent a confirmation for an unprepared/incomplete legacy record.
    if not order['processed_at'] or not order['processed_by']:
        return events
    collected = next((e for e in events if e['status'] == 'Ramassé'
                      and 'Préparation physique validée' in (e.get('note') or '')), None)
    if not collected:
        return events
    result = [dict(e) for e in events]
    for expected in initial_stock_events(order):
        existing = next((e for e in result if e['status'] == expected['status']), None)
        if existing is not None:
            # At equal timestamps, initial stock stages precede the pickup scan.
            existing['timeline_order'] = expected['timeline_order']
            continue
        actor = c.execute('SELECT name FROM users WHERE id=?', (expected['actor_id'],)).fetchone()
        result.append(dict(expected, id=None, parcel_id=parcel_id,
                           actor=actor['name'] if actor else 'Acteur non renseigné',
                           history_reconstructed=True,
                           note=expected['note'] + ' · Historique reconstitué depuis la préparation enregistrée'))
    return sorted(result, key=lambda e: (e.get('created_at') or '', e.get('timeline_order', 0), e.get('id') or 0), reverse=True)
