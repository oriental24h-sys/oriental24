"""Database-level immutability guards for operational audit rows."""

_AUDIT_TABLES = ('ops_audit', 'driver_workspace_audit')


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
