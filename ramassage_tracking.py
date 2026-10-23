"""Durable completion of seller pickups on physical Central-Hub receipt only."""

def central_id(c):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'").fetchone():
        return None
    row = c.execute("SELECT value FROM settings WHERE key='central_hub_id'").fetchone()
    try:
        value = int(row['value']) if row else 0
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def sync_central_receipts(c, hub_id=None, parcel_id=None):
    """Called inside the caller's transaction; also backfills existing receipts.

    Preserve the destination at receipt time so later Central-Hub configuration
    changes do not resurrect completed pickups. Never infer receipt from status.
    """
    hub_id = hub_id or central_id(c)
    if not hub_id:
        return
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'ramassage_central_receipts', 'ops_documents', 'ops_document_lines'} <= tables:
        return
    parcel_clause = ' AND rl.parcel_id=?' if parcel_id is not None else ''
    args = [hub_id]+([parcel_id] if parcel_id is not None else [])
    c.execute('''INSERT OR IGNORE INTO ramassage_central_receipts
        (ramassage_line_id, document_line_id, central_hub_id, received_at)
        SELECT rl.id, dl.id, d.destination_hub_id, dl.received_at
        FROM ramassage_bon_lines rl
        JOIN ramassage_bons b ON b.id=rl.bon_id
        JOIN ops_document_lines dl ON dl.parcel_id=rl.parcel_id
        JOIN ops_documents d ON d.id=dl.document_id
        WHERE rl.received_at IS NOT NULL AND dl.received_at IS NOT NULL
          AND d.kind='transfer' AND d.status!='Annulé'
          AND d.source_hub_id=b.hub_id AND d.destination_hub_id=?
          AND d.source_hub_id!=d.destination_hub_id
          AND dl.departure_reconciled_at IS NULL
          AND dl.received_at>=rl.received_at AND d.created_at>=rl.received_at
        '''+parcel_clause+' ORDER BY dl.received_at,dl.id', args)
