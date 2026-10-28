"""Additive database migrations for the single-Hub-per-city model."""


def _table_exists(connection, name):
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(connection, table):
    return {row[1] for row in connection.execute(f'PRAGMA table_info({table})')}


def migrate_city_hub_id(connection):
    """Add ``cities.hub_id`` and backfill only unambiguous legacy primary mappings.

    A NULL city hub deliberately remains NULL: routing can then use the Admin-selected
    Central Hub fallback. Secondary many-to-many coverage is never promoted to primary,
    and no Hub is selected based on insertion order.
    """
    if not _table_exists(connection, 'cities') or not _table_exists(connection, 'ops_hubs'):
        raise RuntimeError('cities and ops_hubs must exist before the Hub migration')

    if 'hub_id' not in _columns(connection, 'cities'):
        connection.execute('ALTER TABLE cities ADD COLUMN hub_id INTEGER REFERENCES ops_hubs(id)')
    connection.execute('CREATE INDEX IF NOT EXISTS idx_cities_hub_id ON cities(hub_id)')

    if not _table_exists(connection, 'hub_cities'):
        return 0
    legacy_columns = _columns(connection, 'hub_cities')
    if not {'city_id', 'hub_id', 'active', 'is_primary'}.issubset(legacy_columns):
        return 0

    # Migrate only a single, active, explicitly primary assignment. If legacy data is
    # ambiguous or points to an inactive Hub, preserve it for review and leave hub_id NULL.
    candidates = connection.execute('''
        SELECT c.id AS city_id, MIN(hc.hub_id) AS hub_id
        FROM cities c
        JOIN hub_cities hc ON hc.city_id=c.id AND hc.active=1 AND hc.is_primary=1
        JOIN ops_hubs h ON h.id=hc.hub_id AND h.active=1
        WHERE c.hub_id IS NULL
        GROUP BY c.id
        HAVING COUNT(DISTINCT hc.hub_id)=1
    ''').fetchall()
    changed = 0
    for row in candidates:
        cursor = connection.execute(
            'UPDATE cities SET hub_id=? WHERE id=? AND hub_id IS NULL',
            (row[1], row[0]),
        )
        changed += cursor.rowcount
    return changed


def migrate_driver_hub_id(connection, *, created_at, append_audit):
    """Add a single local Hub to each courier and infer only unambiguous active assignments.

    Existing parcel assignments are never changed. A legacy driver is attached only when
    every non-closed assigned parcel resolves to the same active Hub (physical current_hub_id
    first, otherwise the parcel city's direct hub_id). Missing or conflicting evidence stays
    NULL for Admin review; the Central Hub fallback is deliberately not inferred here.
    """
    if not all(_table_exists(connection, table) for table in ('users','cities','ops_hubs','parcels','settings')):
        raise RuntimeError('users, cities, ops_hubs, parcels and settings are required for the courier-Hub migration')
    if 'driver_hub_id' not in _columns(connection, 'users'):
        connection.execute('ALTER TABLE users ADD COLUMN driver_hub_id INTEGER REFERENCES ops_hubs(id)')
    connection.execute('CREATE INDEX IF NOT EXISTS idx_users_driver_hub ON users(driver_hub_id,role,active)')
    connection.executescript('''
    CREATE TRIGGER IF NOT EXISTS users_driver_hub_role_insert
    BEFORE INSERT ON users WHEN NEW.driver_hub_id IS NOT NULL AND NEW.role<>'livreur'
    BEGIN SELECT RAISE(ABORT,'Only couriers may be assigned to a driver Hub'); END;
    CREATE TRIGGER IF NOT EXISTS users_driver_hub_role_update
    BEFORE UPDATE OF driver_hub_id,role ON users
    WHEN NEW.driver_hub_id IS NOT NULL AND NEW.role<>'livreur'
    BEGIN SELECT RAISE(ABORT,'Only couriers may be assigned to a driver Hub'); END;
    ''')
    marker='driver_hub_mapping_migrated_v1'
    if connection.execute('SELECT 1 FROM settings WHERE key=?',(marker,)).fetchone():
        return {'inferred':0,'unmapped':0,'already_migrated':True}
    inferred=0;unmapped=0
    drivers=connection.execute("SELECT id,name FROM users WHERE role='livreur' AND driver_hub_id IS NULL ORDER BY id").fetchall()
    terminal=('Livré','Retourné','Refusé','Annulé')
    for driver in drivers:
        driver_id=driver[0]
        assignments=connection.execute('''SELECT p.id,p.current_hub_id,ci.hub_id city_hub_id,
                current_hub.active current_hub_active,city_hub.active city_hub_active
            FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id
            LEFT JOIN ops_hubs current_hub ON current_hub.id=p.current_hub_id
            LEFT JOIN ops_hubs city_hub ON city_hub.id=ci.hub_id
            WHERE p.driver_id=? AND COALESCE(p.status,'') NOT IN (?,?,?,?) ORDER BY p.id''',
            (driver_id,*terminal)).fetchall()
        candidates=[];valid=True
        for parcel in assignments:
            if parcel[1] is not None:
                hub_id=parcel[1]
                if parcel[3]!=1:valid=False;break
            else:
                hub_id=parcel[2]
                if hub_id is None or parcel[4]!=1:valid=False;break
            candidates.append(hub_id)
        unique=set(candidates)
        if assignments and valid and len(unique)==1:
            hub_id=next(iter(unique))
            connection.execute('UPDATE users SET driver_hub_id=? WHERE id=? AND driver_hub_id IS NULL',(hub_id,driver_id))
            append_audit(connection,actor_id=None,actor_name='Migration système',
                action='driver_hub_inferred',entity_type='driver_hub_assignment',entity_id=driver_id,
                old_value=None,new_value={'driver_hub_id':hub_id,'basis':'single active Hub across current assigned parcels',
                    'parcel_count':len(assignments)},metadata={'migration':marker},created_at=created_at)
            inferred+=1
        else:
            unmapped+=1
    connection.execute('INSERT INTO settings(key,value) VALUES(?,?)',(marker,'complete'))
    return {'inferred':inferred,'unmapped':unmapped,'already_migrated':False}


def assign_cities_to_hub(connection, hub_id, city_ids, actor_id, created_at):
    """Set one Hub per selected city; empty assignments fall back to Central at runtime.

    The legacy hub_cities table is kept synchronized for rollback compatibility. A selected
    city is explicitly transferred from its previous Hub; removed cities become unassigned.
    This function does not change delivery/pickup activation flags.
    """
    if not isinstance(city_ids, list) or any(type(city_id) is not int or city_id <= 0 for city_id in city_ids):
        raise ValueError('city_ids must be a list of positive integer IDs')
    if len(city_ids) != len(set(city_ids)):
        raise ValueError('city_ids must not contain duplicates')
    if not _table_exists(connection, 'hub_cities'):
        raise RuntimeError('hub_cities must exist during the compatibility rollout')

    if city_ids:
        marks = ','.join('?' for _ in city_ids)
        found = {row[0] for row in connection.execute(
            f'SELECT id FROM cities WHERE id IN ({marks})', city_ids
        )}
        if found != set(city_ids):
            raise ValueError('one or more city IDs do not exist')
        connection.execute(
            f'UPDATE cities SET hub_id=NULL WHERE hub_id=? AND id NOT IN ({marks})',
            [hub_id, *city_ids],
        )
    else:
        connection.execute('UPDATE cities SET hub_id=NULL WHERE hub_id=?', (hub_id,))

    # Cities removed from this Hub remain in legacy history but are no longer active coverage.
    connection.execute(
        'UPDATE hub_cities SET active=0,is_primary=0 WHERE hub_id=? AND city_id NOT IN '
        + (f'({",".join("?" for _ in city_ids)})' if city_ids else '(SELECT id FROM cities WHERE 1=0)'),
        [hub_id, *city_ids],
    )

    for city_id in city_ids:
        connection.execute('UPDATE cities SET hub_id=? WHERE id=?', (hub_id, city_id))
        # There must be exactly one legacy primary during rollback: drop other coverage rows,
        # clear any stale primary, then upsert the single owner.
        connection.execute('DELETE FROM hub_cities WHERE city_id=? AND hub_id<>?', (city_id, hub_id))
        connection.execute('UPDATE hub_cities SET is_primary=0 WHERE city_id=?', (city_id,))
        connection.execute('''
            INSERT INTO hub_cities(hub_id,city_id,active,is_primary,created_by,created_at)
            VALUES(?,?,1,1,?,?)
            ON CONFLICT(hub_id,city_id) DO UPDATE SET
                active=1,is_primary=1,created_by=excluded.created_by,created_at=excluded.created_at
        ''', (hub_id, city_id, actor_id, created_at))
    return True


def ensure_hub_manager_can_leave(connection, user_id, hub_id):
    """Keep an active Hub from becoming managerless through a single-account edit.

    An atomic manager-replacement flow may deactivate the old account and create its
    replacement in one transaction; ordinary account edits must leave another active
    manager behind first.
    """
    if type(user_id) is not int or user_id <= 0 or type(hub_id) is not int or hub_id <= 0:
        return True
    hub = connection.execute('SELECT active FROM ops_hubs WHERE id=?', (hub_id,)).fetchone()
    if not hub or not hub[0]:
        return True
    replacement = connection.execute("""SELECT 1 FROM users
        WHERE agent_hub_id=? AND active=1 AND role IN ('hub_manager','agent') AND id<>? LIMIT 1""",
        (hub_id, user_id)).fetchone()
    if not replacement:
        raise ValueError('Un Hub actif doit conserver un responsable actif. Utilisez le remplacement atomique du responsable.')
    return True


def install_one_active_hub_manager_guards(connection):
    """Prevent assigning two active Hub Manager accounts to the same Hub.

    Pre-existing duplicates are preserved so an Admin can resolve them explicitly.
    The update guard makes a narrow exception for a pure legacy-role conversion
    (agent -> hub_manager); otherwise that migration would be blocked by the
    duplicate guard meant to protect new assignments.
    """
    required = {'id', 'role', 'active', 'agent_hub_id'}
    if not required.issubset(_columns(connection, 'users')):
        raise RuntimeError('users must have role, active and agent_hub_id before manager guards are installed')

    connection.execute("""
        CREATE TRIGGER IF NOT EXISTS users_one_active_hub_manager_insert
        BEFORE INSERT ON users
        WHEN NEW.role IN ('hub_manager','agent')
          AND COALESCE(NEW.active,0)=1
          AND NEW.agent_hub_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM users u
            WHERE u.agent_hub_id=NEW.agent_hub_id
              AND u.active=1
              AND u.role IN ('hub_manager','agent')
          )
        BEGIN
          SELECT RAISE(ABORT, 'Hub already has an active manager');
        END
    """)

    # Upgrade the older trigger definition in-place exactly once. IF NOT EXISTS
    # alone would keep the previous trigger forever and continue to block migration.
    current = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='users_one_active_hub_manager_update'"
    ).fetchone()
    if not current or 'legacy_role_migration_v1' not in (current[0] or ''):
        connection.execute('DROP TRIGGER IF EXISTS users_one_active_hub_manager_update')
    connection.execute("""
        CREATE TRIGGER IF NOT EXISTS users_one_active_hub_manager_update
        BEFORE UPDATE OF role,active,agent_hub_id ON users
        WHEN NEW.role IN ('hub_manager','agent')
          AND COALESCE(NEW.active,0)=1
          AND NEW.agent_hub_id IS NOT NULL
          AND NOT ( /* legacy_role_migration_v1 */
            OLD.role='agent'
            AND NEW.role='hub_manager'
            AND OLD.active IS NEW.active
            AND OLD.agent_hub_id IS NEW.agent_hub_id
          )
          AND EXISTS (
            SELECT 1 FROM users u
            WHERE u.agent_hub_id=NEW.agent_hub_id
              AND u.active=1
              AND u.role IN ('hub_manager','agent')
              AND u.id IS NOT NEW.id
          )
        BEGIN
          SELECT RAISE(ABORT, 'Hub already has an active manager');
        END
    """)
