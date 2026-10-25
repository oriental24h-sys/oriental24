"""Fail-closed Hub Manager API policy.

Only routes reviewed for Hub scoping or own-account access are listed here. Extend this
allowlist only after verifying the route's server-side query and mutation scopes.
"""
import re
import sqlite3

HUB_MANAGER_SCOPED_ROUTES = (
    ('GET', r'/api/drivers-workspace/\d+'),
    ('POST', r'/api/drivers-workspace/\d+/scan-preview'),
    ('POST', r'/api/drivers-workspace/\d+/scan-batch'),
    ('GET', r'/api/driver-finance/terms'),
    ('PUT', r'/api/driver-finance/terms/\d+'),
    ('GET', r'/api/driver-finance/terms/\d+/history'),
    ('POST', r'/api/driver-finance/preview'),
    ('POST', r'/api/driver-finance/preview/[a-f0-9]{32}/confirm'),
    ('GET', r'/api/driver-finance/statements/\d+'),
    ('GET', r'/api/sidebar-counts'), ('GET', r'/api/bootstrap'), ('GET', r'/api/parcels/\d+'),
    ('PATCH', r'/api/parcels/\d+'),
    ('POST', r'/api/logout'), ('PATCH', r'/api/profile'),
    ('GET', r'/api/tickets'), ('POST', r'/api/tickets'),
    ('GET', r'/api/tickets/\d+'), ('POST', r'/api/tickets/\d+'),
    ('GET', r'/api/announcements'),
    ('GET', r'/api/security/sessions'), ('POST', r'/api/security/sessions/revoke-others'),
    ('DELETE', r'/api/security/sessions/\d+'),
    ('GET', r'/api/account-dossiers'), ('GET', r'/api/account-dossiers/\d+'),
    ('PATCH', r'/api/account-dossiers/\d+'), ('POST', r'/api/account-dossiers/\d+/submit'),
    ('POST', r'/api/account-dossiers/\d+/documents'),
    ('GET', r'/api/account-documents/\d+'), ('DELETE', r'/api/account-documents/\d+'),
    ('GET', r'/api/claim-attachments/\d+'),
    ('POST', r'/api/logistics/parcels/\d+/tickets'),
    ('GET', r'/api/logistics/config'),
    ('GET', r'/api/logistics/documents'), ('GET', r'/api/logistics/documents/\d+'),
    ('POST', r'/api/logistics/documents'),
    ('GET', r'/api/logistics/palettes'), ('GET', r'/api/logistics/palette-candidates'),
    ('GET', r'/api/logistics/hub-dashboard'),
    ('GET', r'/api/logistics/hub/drivers'), ('POST', r'/api/logistics/hub/drivers'),
    ('PATCH', r'/api/logistics/hub/drivers/\d+'),
    ('POST', r'/api/logistics/hub/drivers/\d+/access'),
    ('POST', r'/api/logistics/hub/assignments'), ('GET', r'/api/logistics/hub/invoices'),
    ('GET', r'/api/logistics/hub/driver-statements'),
    ('GET', r'/api/logistics/cod/hub'),
    ('POST', r'/api/logistics/cod/hub/handoffs'),
    ('POST', r'/api/logistics/documents/\d+/departure-scan'),
    ('POST', r'/api/logistics/documents/\d+/receive'),
    ('GET', r'/api/logistics/notifications'), ('PATCH', r'/api/logistics/notifications'),
    ('GET', r'/api/partner-palettes/config'), ('GET', r'/api/partner-palettes'),
    ('GET', r'/api/partner-palettes/\d+'), ('GET', r'/api/partner-palettes/\d+/csv'),
    ('POST', r'/api/partner-palettes/\d+/receive'),
    ('POST', r'/api/partner-palettes/\d+/receive-all'),
    ('GET', r'/api/partner-palettes/\d+/incidents'),
    ('GET', r'/api/partner-palette-incidents/\d+/photo'),
    ('POST', r'/api/partner-palettes/\d+/incidents'),
    ('POST', r'/api/partner-palettes/\d+/close-gaps'),
    ('POST', r'/api/partner-palettes/\d+/incidents/\d+/resolve'),
    ('GET', r'/api/alerts'),
    ('POST', r'/api/partner-palettes/fusion'), ('GET', r'/api/partner-palettes/fusion/\d+'),
    ('POST', r'/api/partner-palettes/fusion/\d+/scan'),
    ('POST', r'/api/partner-palettes/fusion/\d+/close'),
    ('GET', r'/api/control-tower'),
    ('GET', r'/api/control-tower/map-data'),
    ('POST', r'/api/control-tower/ramassage'),
    ('GET', r'/api/control-tower/ramassage/\d+/candidates'),
    ('POST', r'/api/control-tower/ramassage/\d+/assign'),
    ('GET', r'/api/control-tower/route-history/\d+'),
    ('GET', r'/api/return-palettes/config'), ('GET', r'/api/return-palettes/vendor-counts'),
    ('GET', r'/api/return-palettes/candidates'), ('GET', r'/api/return-palettes'),
    ('POST', r'/api/return-palettes'), ('GET', r'/api/return-palettes/\d+'),
    ('GET', r'/api/return-palettes/\d+/csv'),
    ('POST', r'/api/return-palettes/\d+/dispatch'),
    ('POST', r'/api/return-palettes/\d+/cancel'),
    ('POST', r'/api/return-palettes/\d+/receive'),
    ('GET', r'/api/return-palettes/scan-lookup'), ('POST', r'/api/return-palettes/scan-send'),
    ('POST', r'/api/return-palettes/\d+/refuse'),
    ('GET', r'/api/dispatch-collection/(transfer|return)/\d+'),
    ('GET', r'/api/dispatch-collection/(transfer|return)/\d+/check'),
    ('POST', r'/api/dispatch-collection/(transfer|return)/\d+'),
    ('GET', r'/api/reception-collection/(transfer|partner|return|fusion|recovered)/\d+'),
    ('POST', r'/api/reception-collection/(transfer|partner|return|fusion|recovered)/\d+'),
    ('GET', r'/api/ramassage-bons'),
    ('GET', r'/api/ramassage-bons/hub/queue'),
    ('GET', r'/api/ramassage-bons/hub/collected'),
    ('GET', r'/api/ramassage-bons/\d+'),
    ('POST', r'/api/ramassage-bons/\d+/receive'),
    ('POST', r'/api/ramassage-bons/\d+/receive-batch'),
)

HUB_OPERATIONAL_PREFIXES = (
    '/api/drivers-workspace', '/api/driver-finance',
    '/api/parcels/', '/api/logistics/parcels/', '/api/logistics/config', '/api/logistics/documents', '/api/logistics/hub-dashboard', '/api/logistics/hub/', '/api/logistics/hub/drivers', '/api/logistics/cod/', '/api/logistics/notifications', '/api/partner-palettes',
    '/api/partner-palette-incidents', '/api/return-palettes', '/api/alerts',
    '/api/control-tower', '/api/logistics/palettes', '/api/logistics/palette-candidates',
    '/api/sidebar-counts', '/api/ramassage-bons', '/api/reception-collection', '/api/dispatch-collection',
)


def hub_manager_route_allowed(method, path):
    """Whether a route/method is explicitly enabled for the transitional Hub Manager role."""
    method = 'GET' if method == 'HEAD' else method
    return any(method == allowed and re.fullmatch(pattern, path) for allowed, pattern in HUB_MANAGER_SCOPED_ROUTES)


def hub_manager_requires_active_hub(path):
    """Operational endpoints require the manager's assigned Hub to still be active."""
    return path.startswith(HUB_OPERATIONAL_PREFIXES)


def hub_received_lines(lines, hub_id):
    """Expose only manifest lines physically scanned into the manager's active Hub."""
    if isinstance(hub_id, bool) or not isinstance(hub_id, int) or hub_id <= 0:
        return []
    return [line for line in lines if line.get('received_at') and line.get('current_hub_id') == hub_id]


def resolve_routing_hub(primary_hub_id, central_hub_id, central_hub_active):
    """Prefer an active city primary; otherwise use only the Admin-designated active Central Hub."""
    valid_primary=type(primary_hub_id) is int and primary_hub_id>0
    valid_central=type(central_hub_id) is int and central_hub_id>0 and central_hub_active is True
    if valid_primary:return primary_hub_id,'city_primary'
    if valid_central:return central_hub_id,'central'
    return None,None


def central_hub_transfer_allowed(source_hub_id, destination_hub_id, central_hub_id, central_hub_active):
    """Allow only directed star-topology transfers with the active Central Hub as one endpoint."""
    ids=(source_hub_id,destination_hub_id,central_hub_id)
    if any(type(hub_id) is not int or hub_id<=0 for hub_id in ids):
        return False
    if central_hub_active is not True or source_hub_id==destination_hub_id:
        return False
    return (source_hub_id==central_hub_id) != (destination_hub_id==central_hub_id)


def parcel_physically_at_hub(current_hub_id, hub_id):
    """Require an explicit current-location record before treating a parcel as a Hub's stock."""
    return type(current_hub_id) is int and current_hub_id>0 and type(hub_id) is int and hub_id>0 and current_hub_id==hub_id


def driver_dispatch_allowed(connection, current_hub_id, driver_hub_id):
    """Allow a new handoff only at the courier's explicitly assigned active Hub."""
    if not parcel_physically_at_hub(current_hub_id,driver_hub_id):
        return False
    try:
        return bool(connection.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(driver_hub_id,)).fetchone())
    except sqlite3.Error:
        return False


def driver_team_member_ids(connection, lead_id):
    """Return active team members only when lead and members share one active Hub."""
    if type(lead_id) is not int or lead_id<=0:
        return []
    try:
        lead=connection.execute('''SELECT u.driver_hub_id FROM users u JOIN ops_hubs h
            ON h.id=u.driver_hub_id AND h.active=1
            WHERE u.id=? AND u.role='livreur' AND u.active=1''',(lead_id,)).fetchone()
        if not lead or type(lead[0]) is not int or lead[0]<=0:
            return []
        return [row[0] for row in connection.execute('''SELECT u.id FROM users u JOIN ops_hubs h
            ON h.id=u.driver_hub_id AND h.active=1
            WHERE u.team_lead_id=? AND u.role='livreur' AND u.active=1 AND u.driver_hub_id=? ORDER BY u.id''',
            (lead_id,lead[0]))]
    except sqlite3.Error:
        return []


def hub_document_lines_at_hub(lines, hub_id):
    """Expose document line details only while each parcel is physically at this Hub."""
    if isinstance(hub_id, bool) or not isinstance(hub_id, int) or hub_id<=0:
        return []
    return [line for line in lines if type(line.get('current_hub_id')) is int and line.get('current_hub_id')==hub_id]


def hub_manager_transfer_scope(document, hub_id, direction):
    """Check that a manager is scanning at the transfer's assigned source or destination Hub."""
    field={'departure':'source_hub_id','arrival':'destination_hub_id'}.get(direction)
    if field is None or not hasattr(document,'get'):
        return False
    document_hub_id=document.get(field)
    return (document.get('kind')=='transfer' and type(hub_id) is int and hub_id>0
            and type(document_hub_id) is int and document_hub_id==hub_id)


def ops_manifest_counts(lines):
    """Count only unreconciled lines as live manifest contents; retain the original count for audit views."""
    rows=list(lines or [])
    active=[line for line in rows if not line.get('departure_reconciled_at')]
    return {
        'count':len(active),
        'original_count':len(rows),
        'departure_reconciled_count':len(rows)-len(active),
        'received':sum(bool(line.get('received_at')) for line in active),
        'departure_scanned':sum(bool(line.get('departure_scanned_at')) for line in active),
    }


def manifest_status_from_counts(count, departure_scanned, received):
    """Derive transfer state from live manifest counts after departure reconciliation."""
    values=(count,departure_scanned,received)
    if any(type(value) is not int or value<0 for value in values):
        raise ValueError('manifest counts must be non-negative integers')
    if count<1 or departure_scanned>count or received>count:
        raise ValueError('manifest counts are inconsistent')
    if departure_scanned<count:
        return 'Départ partiel'
    if received==count:
        return 'Reçu'
    if received:
        return 'Partiellement reçu'
    return 'En transit'


def hub_parcel_scope(conn, alias, hub_id):
    """Return a fail-closed SQL scope for parcels currently held at an active Hub."""
    if (not isinstance(alias, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', alias)
            or isinstance(hub_id, bool) or not isinstance(hub_id, int) or hub_id <= 0):
        return '1=0', []
    try:
        active = conn.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1', (hub_id,)).fetchone()
    except sqlite3.Error:
        return '1=0', []
    if not active:
        return '1=0', []
    return f'{alias}.current_hub_id=?', [hub_id]


def hub_tracking_parcel_scope(conn, alias, hub_id):
    """Read-only visibility: physical stock plus tours handed off by this Hub.
    Mutations must continue using hub_parcel_scope (physical custody only).
    Never infer ownership from the courier's current Hub or the recipient city.
    """
    physical, args = hub_parcel_scope(conn, alias, hub_id)
    if not args:
        return '1=0', []
    return f"""({physical} OR ({alias}.current_hub_id IS NULL
        AND {alias}.driver_id IS NOT NULL AND {alias}.status NOT IN ('Transit','Vers Hub Central')
        AND EXISTS(SELECT 1 FROM ops_assignments a
            WHERE a.parcel_id={alias}.id AND a.new_driver_id={alias}.driver_id AND a.hub_id=?
              AND a.id=(SELECT max(latest.id) FROM ops_assignments latest WHERE latest.parcel_id={alias}.id))))""", [hub_id, hub_id]


def parcel_by_tracking_at_hub(conn, tracking, hub_id):
    """Fetch a parcel only when it is physically recorded at the selected Hub."""
    if isinstance(hub_id, bool) or not isinstance(hub_id, int) or hub_id <= 0:
        return None
    return conn.execute(
        'SELECT * FROM parcels WHERE upper(tracking)=upper(?) AND current_hub_id=? ORDER BY id DESC LIMIT 1',
        (tracking, hub_id),
    ).fetchone()


def parcel_by_manifest_at_hub(conn, reference, hub_id):
    """Resolve a manifest reference without crossing its destination Hub boundary."""
    if isinstance(hub_id, bool) or not isinstance(hub_id, int) or hub_id <= 0:
        return None
    return conn.execute('''SELECT p.* FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
        JOIN parcels p ON p.id=l.parcel_id WHERE d.reference=? AND d.destination_hub_id=?
        AND l.active=1 AND p.current_hub_id=? ORDER BY l.id LIMIT 1''',
        (reference, hub_id, hub_id),
    ).fetchone()


def local_driver_parcel_scope(alias='p'):
    """Custody at this Hub, or a courier tour dispatched from this Hub.

    Parameters: local Hub twice. Never infer historical custody from today's
    courier mapping alone. Latest assignment wins, including a NULL snapshot.
    """
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', alias):
        raise ValueError('Invalid SQL alias')
    return f"""({alias}.current_hub_id=? OR ({alias}.current_hub_id IS NULL AND
        (SELECT a.hub_id FROM ops_assignments a WHERE a.parcel_id={alias}.id
         AND a.new_driver_id={alias}.driver_id ORDER BY a.id DESC LIMIT 1)=?))"""


def driver_financial_hub_sql(alias='p'):
    """Prefer the recorded closing attempt; otherwise the latest assignment.
    Legacy rows with no evidence remain Admin-only.
    """
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', alias):
        raise ValueError('Invalid SQL alias')
    return f"""COALESCE(
        (SELECT a.operational_hub_id FROM ops_attempts a WHERE a.parcel_id={alias}.id
         AND a.driver_id={alias}.driver_id AND a.outcome={alias}.status ORDER BY a.id DESC LIMIT 1),
        (SELECT a.hub_id FROM ops_assignments a WHERE a.parcel_id={alias}.id
         AND a.new_driver_id={alias}.driver_id ORDER BY a.id DESC LIMIT 1))"""
