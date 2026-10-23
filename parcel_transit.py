"""Read-only transit display derived from a departed, not-yet-received transfer line."""

def annotate_parcel_transit(c,rows):
    if not rows:return rows
    for p in rows:
        p['transit_direction']=None
        p['transit_destination']=None
    ids=[p['id'] for p in rows if p.get('current_hub_id') is None and p.get('status') in ('Transit','Vers Hub Central','Retourné','Refusé')]
    if not ids:return rows
    tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'ops_documents','ops_document_lines','ops_hubs','settings'}<=tables:return rows
    setting=c.execute("SELECT value FROM settings WHERE key='central_hub_id'").fetchone()
    try:central=int(setting['value']) if setting else None
    except (ValueError,TypeError):central=None
    mapped={p['id']:p for p in rows}
    for offset in range(0,len(ids),800):
        chunk=ids[offset:offset+800]
        query='''SELECT l.parcel_id,d.source_hub_id,d.destination_hub_id,d.palette_purpose,h.name destination
            FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
            LEFT JOIN ops_hubs h ON h.id=d.destination_hub_id
            WHERE l.parcel_id IN ('''+','.join('?' for _ in chunk)+''')
              AND d.kind='transfer' AND l.active=1 AND l.received_at IS NULL
              AND l.departure_reconciled_at IS NULL
              AND d.status IN ('Départ partiel','En transit','Partiellement reçu')
              AND ((d.departure_scan_required=1 AND l.departure_scanned_at IS NOT NULL)
                   OR (d.departure_scan_required=0 AND d.dispatched_at IS NOT NULL))
            ORDER BY l.id DESC'''
        for r in c.execute(query,chunk):
            p=mapped[r['parcel_id']]
            if p['transit_direction']:continue
            if p['status'] in ('Refusé','Retourné') and r['palette_purpose']!='return_to_origin':continue
            direction='central' if central and r['destination_hub_id']==central else 'destination' if central and r['source_hub_id']==central else 'inter_hub'
            p['transit_direction']=direction;p['transit_destination']=r['destination']
    return rows
