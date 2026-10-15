"""Safe append helper for immutable, actor-attributed audit records."""
import json


_REDACTED = '[REDACTED]'
_SENSITIVE_KEYS = {
    'password', 'password_hash', 'token', 'access_token', 'refresh_token',
    'secret', 'client_secret', 'authorization', 'cookie', 'session',
}


def _safe_value(value):
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            normalized = str(key).strip().lower().replace('-', '_')
            if normalized in _SENSITIVE_KEYS or 'password' in normalized or normalized.endswith('_token'):
                safe[str(key)] = _REDACTED
            else:
                safe[str(key)] = _safe_value(item)
        return safe
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError('Audit values must contain only JSON-compatible data')


def _encode(value):
    return json.dumps(_safe_value(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def append_audit_log(
    connection, *, actor_id, actor_name, action, entity_type, entity_id,
    old_value, new_value, created_at, metadata=None,
):
    """Append one audit event; callers must pass minimized, non-secret snapshots.

    Passwords, tokens, session identifiers and related fields are redacted defensively.
    The actor name is stored as a snapshot, so the audit trail remains attributable if
    an account is later renamed or removed.
    """
    actor_name = str(actor_name or '').strip()
    action = str(action or '').strip()
    entity_type = str(entity_type or '').strip()
    entity_id = str(entity_id or '').strip()
    if not actor_name or not action or not entity_type or not entity_id or not created_at:
        raise ValueError('actor_name, action, entity_type, entity_id and created_at are required')

    cursor = connection.execute('''
        INSERT INTO audit_log(
            actor_id,actor_name,action,entity_type,entity_id,old_value,new_value,metadata,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?)
    ''', (
        actor_id, actor_name, action, entity_type, entity_id,
        _encode(old_value), _encode(new_value), _encode(metadata or {}), str(created_at),
    ))
    return cursor.lastrowid
