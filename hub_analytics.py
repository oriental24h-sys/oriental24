"""Hub-scoped raw operational metrics and event snapshots.

This module does not alter parcel financial calculations or settlements. Historical values are
used only where the system already recorded a physical receipt; no Hub is inferred from a city.
"""
from statistics import median


def _ensure_column(connection, table, name, definition):
    columns = {row['name'] for row in connection.execute(f'PRAGMA table_info({table})')}
    if name not in columns:
        connection.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')


def install_hub_analytics_schema(connection, created_at):
    """Install append-only physical-arrival events and Hub snapshots for future activity."""
    _ensure_column(connection, 'ops_assignments', 'hub_id', 'INTEGER REFERENCES ops_hubs(id)')
    _ensure_column(connection, 'ops_attempts', 'operational_hub_id', 'INTEGER REFERENCES ops_hubs(id)')
    connection.executescript('''
    CREATE TABLE IF NOT EXISTS ops_hub_arrivals(
        id INTEGER PRIMARY KEY,
        parcel_id INTEGER NOT NULL REFERENCES parcels(id),
        hub_id INTEGER NOT NULL REFERENCES ops_hubs(id),
        arrived_at TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        actor_id INTEGER REFERENCES users(id),
        created_at TEXT NOT NULL,
        UNIQUE(source_type,source_id)
    );
    CREATE INDEX IF NOT EXISTS idx_ops_hub_arrivals_hub_date
        ON ops_hub_arrivals(hub_id,arrived_at,id);
    CREATE INDEX IF NOT EXISTS idx_ops_hub_arrivals_parcel
        ON ops_hub_arrivals(parcel_id,hub_id,arrived_at,id);
    CREATE INDEX IF NOT EXISTS idx_ops_assignments_hub_date
        ON ops_assignments(hub_id,created_at,new_driver_id);
    CREATE INDEX IF NOT EXISTS idx_ops_attempts_operational_hub_date
        ON ops_attempts(operational_hub_id,created_at,outcome);
    CREATE TRIGGER IF NOT EXISTS ops_hub_arrivals_no_update
    BEFORE UPDATE ON ops_hub_arrivals BEGIN
        SELECT RAISE(ABORT,'ops_hub_arrivals is append-only');
    END;
    CREATE TRIGGER IF NOT EXISTS ops_hub_arrivals_no_delete
    BEFORE DELETE ON ops_hub_arrivals BEGIN
        SELECT RAISE(ABORT,'ops_hub_arrivals is append-only');
    END;
    CREATE TRIGGER IF NOT EXISTS ops_hub_arrival_on_document_receive
    AFTER UPDATE OF received_at ON ops_document_lines
    WHEN NEW.received_at IS NOT NULL AND OLD.received_at IS NULL
    BEGIN
        INSERT OR IGNORE INTO ops_hub_arrivals(
            parcel_id,hub_id,arrived_at,source_type,source_id,actor_id,created_at
        )
        SELECT NEW.parcel_id,d.destination_hub_id,NEW.received_at,'document_line',CAST(NEW.id AS TEXT),
               NEW.received_by,NEW.received_at
        FROM ops_documents d
        WHERE d.id=NEW.document_id AND d.destination_hub_id IS NOT NULL;
    END;
    CREATE TRIGGER IF NOT EXISTS ops_hub_arrival_on_parcel_insert
    AFTER INSERT ON parcels
    WHEN NEW.current_hub_id IS NOT NULL AND NEW.current_hub_id>0
    BEGIN
        INSERT OR IGNORE INTO ops_hub_arrivals(
            parcel_id,hub_id,arrived_at,source_type,source_id,actor_id,created_at
        ) VALUES(NEW.id,NEW.current_hub_id,COALESCE(NULLIF(NEW.created_at,''),CURRENT_TIMESTAMP),
                 'parcel_creation',CAST(NEW.id AS TEXT),NULL,
                 COALESCE(NULLIF(NEW.created_at,''),CURRENT_TIMESTAMP));
    END;
    ''')
    connection.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('hub_metrics_started_at',?)", (created_at,))
    # Backfill only explicit physical receipts that predate this rollout marker. This avoids
    # re-importing new trigger-captured receipts as duplicate legacy events on later restarts.
    connection.execute('''INSERT OR IGNORE INTO ops_hub_arrivals(
            parcel_id,hub_id,arrived_at,source_type,source_id,actor_id,created_at)
        SELECT l.parcel_id,d.destination_hub_id,l.received_at,'document_line_legacy',CAST(l.id AS TEXT),
               l.received_by,l.received_at
        FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
        JOIN ops_hubs h ON h.id=d.destination_hub_id
        WHERE l.received_at IS NOT NULL AND d.destination_hub_id IS NOT NULL
          AND datetime(l.received_at)<datetime((SELECT value FROM settings WHERE key='hub_metrics_started_at'))''')


def install_driver_receipt_arrival_trigger(connection):
    """Capture physical driver-to-Hub returns without depending on a client-side payload."""
    connection.executescript('''
    CREATE TRIGGER IF NOT EXISTS ops_hub_arrival_on_driver_receipt_insert
    AFTER INSERT ON driver_receipts
    WHEN NEW.hub_id IS NOT NULL AND NEW.hub_id>0
    BEGIN
        INSERT OR IGNORE INTO ops_hub_arrivals(
            parcel_id,hub_id,arrived_at,source_type,source_id,actor_id,created_at
        ) VALUES(NEW.parcel_id,NEW.hub_id,NEW.received_at,'driver_receipt',
                 CAST(NEW.parcel_id AS TEXT)||':'||NEW.received_at,NULL,NEW.received_at);
    END;
    CREATE TRIGGER IF NOT EXISTS ops_hub_arrival_on_driver_receipt_update
    AFTER UPDATE OF received_at,hub_id ON driver_receipts
    WHEN NEW.hub_id IS NOT NULL AND NEW.hub_id>0
         AND (NEW.received_at IS NOT OLD.received_at OR NEW.hub_id IS NOT OLD.hub_id)
    BEGIN
        INSERT OR IGNORE INTO ops_hub_arrivals(
            parcel_id,hub_id,arrived_at,source_type,source_id,actor_id,created_at
        ) VALUES(NEW.parcel_id,NEW.hub_id,NEW.received_at,'driver_receipt',
                 CAST(NEW.parcel_id AS TEXT)||':'||NEW.received_at,NULL,NEW.received_at);
    END;
    ''')
    connection.execute('''INSERT OR IGNORE INTO ops_hub_arrivals(
            parcel_id,hub_id,arrived_at,source_type,source_id,actor_id,created_at)
        SELECT r.parcel_id,r.hub_id,r.received_at,'driver_receipt_legacy',
               CAST(r.parcel_id AS TEXT)||':'||r.received_at,NULL,r.received_at
        FROM driver_receipts r JOIN ops_hubs h ON h.id=r.hub_id
        WHERE r.hub_id IS NOT NULL AND r.received_at IS NOT NULL
          AND datetime(r.received_at)<datetime((SELECT value FROM settings WHERE key='hub_metrics_started_at'))''')


def hub_operational_metrics(connection, hub_id, date_from, date_to):
    """Return auditable raw counts/rates; no composite score or Hub ranking is calculated."""
    first_rows = connection.execute('''
        SELECT outcome FROM (
            SELECT a.parcel_id,a.outcome,a.created_at,a.operational_hub_id,a.id,
                   ROW_NUMBER() OVER(PARTITION BY a.parcel_id ORDER BY a.created_at,a.id) first_no
            FROM ops_attempts a
        ) ranked
        WHERE first_no=1 AND operational_hub_id=?
          AND substr(created_at,1,10) BETWEEN ? AND ?
    ''', (hub_id, date_from, date_to)).fetchall()
    first_attempts = len(first_rows)
    first_delivered = sum(row['outcome'] == 'Livré' for row in first_rows)

    attempt = connection.execute('''SELECT count(*) attempts,
            count(DISTINCT parcel_id) parcels,
            COALESCE(sum(outcome='Livré'),0) delivered_attempts,
            count(DISTINCT CASE WHEN outcome='Retourné' THEN parcel_id END) returned_parcels,
            COALESCE(sum(outcome='Retourné'),0) return_attempts
        FROM ops_attempts
        WHERE operational_hub_id=? AND substr(created_at,1,10) BETWEEN ? AND ?''',
        (hub_id, date_from, date_to)).fetchone()

    processing_rows = connection.execute('''
        WITH matched AS (
            SELECT h.id arrival_id,h.arrived_at,a.created_at assigned_at,a.id assignment_id,
                   ROW_NUMBER() OVER(PARTITION BY h.id ORDER BY a.created_at,a.id) match_no
            FROM ops_hub_arrivals h
            JOIN ops_assignments a ON a.parcel_id=h.parcel_id AND a.hub_id=h.hub_id
                AND a.new_driver_id IS NOT NULL AND a.created_at>=h.arrived_at
            WHERE h.hub_id=? AND h.source_type NOT LIKE '%_legacy'
              AND substr(h.arrived_at,1,10) BETWEEN ? AND ?
              AND NOT EXISTS(
                  SELECT 1 FROM ops_hub_arrivals later
                  WHERE later.parcel_id=h.parcel_id AND later.hub_id=h.hub_id
                    AND (later.arrived_at>h.arrived_at OR (later.arrived_at=h.arrived_at AND later.id>h.id))
                    AND later.arrived_at<=a.created_at
              )
        )
        SELECT (julianday(assigned_at)-julianday(arrived_at))*1440.0 minutes
        FROM matched WHERE match_no=1
    ''', (hub_id, date_from, date_to)).fetchall()
    durations = [float(row['minutes']) for row in processing_rows
                 if row['minutes'] is not None and float(row['minutes']) >= 0]

    attempt_parcels = int(attempt['parcels'] or 0)
    returned = int(attempt['returned_parcels'] or 0)
    return {
        'first_attempts': first_attempts,
        'first_attempt_delivered': first_delivered,
        'first_attempt_rate_pct': round(first_delivered * 100 / first_attempts, 1) if first_attempts else None,
        'attempts': int(attempt['attempts'] or 0),
        'attempt_parcels': attempt_parcels,
        'delivered_attempts': int(attempt['delivered_attempts'] or 0),
        'returned_parcels': returned,
        'return_attempts': int(attempt['return_attempts'] or 0),
        'return_rate_pct': round(returned * 100 / attempt_parcels, 1) if attempt_parcels else None,
        'processing_sample_size': len(durations),
        'processing_average_minutes': round(sum(durations) / len(durations), 1) if durations else None,
        'processing_median_minutes': round(median(durations), 1) if durations else None,
    }


def hub_daily_metrics(connection, hub_id, date_from, date_to, base_rows=None):
    """Merge operation counts into one daily series for charting."""
    by_day = {row['day']: dict(row) for row in (base_rows or [])}

    def row_for(day):
        if day not in by_day:
            by_day[day] = {'day': day, 'departures': 0, 'receipts': 0}
        return by_day[day]

    for row in connection.execute('''SELECT substr(created_at,1,10) day,count(*) assignments
        FROM ops_assignments WHERE hub_id=? AND new_driver_id IS NOT NULL
          AND substr(created_at,1,10) BETWEEN ? AND ? GROUP BY day''',
        (hub_id, date_from, date_to)):
        row_for(row['day'])['assignments'] = row['assignments']

    for row in connection.execute('''SELECT substr(created_at,1,10) day,count(*) attempts,
            COALESCE(sum(outcome='Livré'),0) delivered_attempts,
            COALESCE(sum(outcome='Retourné'),0) returns
        FROM ops_attempts WHERE operational_hub_id=?
          AND substr(created_at,1,10) BETWEEN ? AND ? GROUP BY day''',
        (hub_id, date_from, date_to)):
        row_for(row['day']).update({key: row[key] for key in ('attempts','delivered_attempts','returns')})

    for row in connection.execute('''SELECT substr(arrived_at,1,10) day,count(*) arrivals
        FROM ops_hub_arrivals WHERE hub_id=? AND substr(arrived_at,1,10) BETWEEN ? AND ? GROUP BY day''',
        (hub_id, date_from, date_to)):
        row_for(row['day'])['arrivals'] = row['arrivals']

    return [by_day[day] for day in sorted(by_day)]
