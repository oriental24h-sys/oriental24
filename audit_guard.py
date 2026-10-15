"""Database-level immutability guards for operational audit rows."""

_AUDIT_TABLES = (
    'ops_audit','driver_workspace_audit','audit_log',
    'hub_cod_handoffs','hub_cod_handoff_lines','hub_cod_admin_receipts',
    'hub_cod_admin_receipt_lines','hub_cod_adjustments','hub_cod_settlement_links',
    'hub_invoice_lines','hub_invoice_settlement_links','hub_invoice_adjustments',
)


def _install_append_only_guards(connection, table):
    if table not in _AUDIT_TABLES:
        raise ValueError('Unsupported audit table')
    connection.executescript(f'''
    CREATE TRIGGER IF NOT EXISTS {table}_no_update
    BEFORE UPDATE ON {table}
    BEGIN
        SELECT RAISE(ABORT, '{table} is append-only');
    END;

    CREATE TRIGGER IF NOT EXISTS {table}_no_delete
    BEFORE DELETE ON {table}
    BEGIN
        SELECT RAISE(ABORT, '{table} is append-only');
    END;
    ''')


def install_ops_audit_guards(connection):
    """Permit ops-audit inserts while rejecting edits/removals."""
    _install_append_only_guards(connection, 'ops_audit')


def install_driver_workspace_audit_guards(connection):
    """Permit driver-workspace audit inserts while rejecting edits/removals."""
    _install_append_only_guards(connection, 'driver_workspace_audit')


def install_audit_log_guards(connection):
    """Keep universal audit events append-only at the database layer."""
    _install_append_only_guards(connection, 'audit_log')


def install_hub_cod_audit_guards(connection):
    """Keep COD custody receipts, allocations and corrections append-only."""
    for table in ('hub_cod_handoffs','hub_cod_handoff_lines','hub_cod_admin_receipts',
                  'hub_cod_admin_receipt_lines','hub_cod_adjustments','hub_cod_settlement_links'):
        _install_append_only_guards(connection, table)


def install_hub_invoice_audit_guards(connection):
    """Keep Hub invoice contents and settlement allocations append-only."""
    for table in ('hub_invoice_lines','hub_invoice_settlement_links','hub_invoice_adjustments'):
        _install_append_only_guards(connection, table)


def install_departure_reconciliation_guard(connection):
    """Allow a reconciliation marker to be set once, then keep its actor, time and reason immutable."""
    connection.executescript('''
    CREATE TRIGGER IF NOT EXISTS ops_departure_reconciliation_immutable
    BEFORE UPDATE OF departure_reconciled_at,departure_reconciled_by,departure_reconciliation_reason
    ON ops_document_lines
    WHEN OLD.departure_reconciled_at IS NOT NULL
    BEGIN
        SELECT RAISE(ABORT, 'departure reconciliation is immutable');
    END;
    ''')
