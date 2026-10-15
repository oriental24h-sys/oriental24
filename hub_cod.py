"""Hub COD custody ledger. Records physical handoffs; it does not trigger payouts.

All amounts are integer MAD centimes. Parcel-level lines remain Admin-only; Hub Manager
views expose only driver aggregates and custody receipts, preserving parcel visibility rules.
"""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

from audit_guard import install_hub_cod_audit_guards


_PREFIX = '/api/logistics/cod'


def resolve_cod_hub(connection, city_id):
    """Snapshot the active city owner, or the Admin-selected active Central Hub fallback."""
    city = connection.execute('SELECT hub_id FROM cities WHERE id=?', (city_id,)).fetchone()
    if city and city[0] is not None:
        assigned = connection.execute('SELECT id FROM ops_hubs WHERE id=? AND active=1', (city[0],)).fetchone()
        if assigned:
            return int(assigned[0])
    setting = connection.execute("SELECT value FROM settings WHERE key='central_hub_id'").fetchone()
    if not setting:
        return None
    try:
        central_id = int(setting[0])
    except (TypeError, ValueError):
        return None
    if central_id <= 0:
        return None
    active = connection.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1', (central_id,)).fetchone()
    return central_id if active else None


def money_cents(value, *, signed=False):
    """Convert MAD with at most two decimals to integer centimes."""
    try:
        amount = Decimal(str(value).strip().replace(',', '.'))
        if not amount.is_finite() or (not signed and amount < 0) or abs(amount) > Decimal('1000000000'):
            raise ValueError()
        cents = amount * 100
        if cents != cents.to_integral_value():
            raise ValueError()
        return int(cents)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise ValueError('Montant MAD invalide : deux décimales maximum.')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _effective_received(connection, table, row):
    if table not in ('hub_cod_handoffs', 'hub_cod_admin_receipts'):
        raise ValueError('Type de reçu invalide.')
    adjustment = connection.execute(
        'SELECT COALESCE(sum(delta_cents),0) FROM hub_cod_adjustments WHERE record_type=? AND record_id=?',
        ('driver_handoff' if table == 'hub_cod_handoffs' else 'admin_receipt', row['id']),
    ).fetchone()[0]
    return row['received_cents'] + adjustment


def _pending_attempts(connection, hub_id, driver_id):
    return connection.execute('''
        SELECT a.id,a.amount_cents
        FROM ops_attempts a
        WHERE a.cod_hub_id=? AND a.driver_id=? AND a.outcome='Livré' AND a.amount_cents>0
          AND NOT EXISTS(SELECT 1 FROM hub_cod_handoff_lines l WHERE l.attempt_id=a.id)
        ORDER BY a.created_at,a.id
    ''', (hub_id, driver_id)).fetchall()


def manager_overview(connection, hub_id):
    hub = connection.execute('''SELECT h.id,h.name,ci.name city FROM ops_hubs h
        JOIN cities ci ON ci.id=h.city_id WHERE h.id=? AND h.active=1''', (hub_id,)).fetchone()
    if not hub:
        raise ValueError('Le Hub de ce compte est inactif ou introuvable.')
    due = [dict(row) for row in connection.execute('''
        SELECT CASE WHEN u.id IS NULL THEN NULL ELSE a.driver_id END driver_id,
               COALESCE(u.name,'Livreur non attribué') driver_name,count(*) delivery_count,
               COALESCE(sum(a.amount_cents),0) expected_cents
        FROM ops_attempts a LEFT JOIN users u ON u.id=a.driver_id AND u.role IN ('livreur','driver')
        WHERE a.cod_hub_id=? AND a.outcome='Livré' AND a.amount_cents>0
          AND NOT EXISTS(SELECT 1 FROM hub_cod_handoff_lines l WHERE l.attempt_id=a.id)
        GROUP BY a.driver_id,u.name ORDER BY u.name COLLATE NOCASE
    ''', (hub_id,)).fetchall()]
    pending_handoffs = []
    for row in connection.execute('''SELECT h.*,u.name driver_name FROM hub_cod_handoffs h
        JOIN users u ON u.id=h.driver_id WHERE h.hub_id=? ORDER BY h.id DESC LIMIT 100''', (hub_id,)).fetchall():
        item = dict(row)
        for private_key in ('request_key','payload_hash','actor_id'):
            item.pop(private_key, None)
        item['effective_received_cents'] = _effective_received(connection, 'hub_cod_handoffs', row)
        item['variance_cents'] = item['effective_received_cents'] - item['expected_cents']
        item['remitted_to_admin'] = bool(connection.execute(
            'SELECT 1 FROM hub_cod_admin_receipt_lines WHERE handoff_id=?', (row['id'],)
        ).fetchone())
        pending_handoffs.append(item)
    unremitted_cents = 0
    for row in connection.execute('''SELECT h.* FROM hub_cod_handoffs h WHERE h.hub_id=?
        AND NOT EXISTS(SELECT 1 FROM hub_cod_admin_receipt_lines l WHERE l.handoff_id=h.id)''', (hub_id,)).fetchall():
        unremitted_cents += _effective_received(connection, 'hub_cod_handoffs', row)
    return {
        'hub': dict(hub), 'drivers_due': due,
        'expected_due_cents': sum(row['expected_cents'] for row in due),
        'unremitted_cents': unremitted_cents,
        'handoffs': pending_handoffs,
    }


def admin_overview(connection):
    hubs = [dict(row) for row in connection.execute('''SELECT h.id,h.name,ci.name city,h.active
        FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id ORDER BY h.name COLLATE NOCASE''').fetchall()]
    for hub in hubs:
        due = connection.execute('''SELECT count(*) deliveries,COALESCE(sum(a.amount_cents),0) amount_cents,
                   COALESCE(sum(CASE WHEN u.id IS NULL THEN 1 ELSE 0 END),0) unassigned_count,
                   COALESCE(sum(CASE WHEN u.id IS NULL THEN a.amount_cents ELSE 0 END),0) unassigned_cents
            FROM ops_attempts a LEFT JOIN users u ON u.id=a.driver_id AND u.role IN ('livreur','driver')
            WHERE a.cod_hub_id=? AND a.outcome='Livré' AND a.amount_cents>0
              AND NOT EXISTS(SELECT 1 FROM hub_cod_handoff_lines l WHERE l.attempt_id=a.id)''', (hub['id'],)).fetchone()
        hub['driver_cod_count'] = due['deliveries']
        hub['driver_cod_due_cents'] = due['amount_cents']
        hub['unassigned_driver_cod_count'] = due['unassigned_count']
        hub['unassigned_driver_cod_cents'] = due['unassigned_cents']
        unremitted = 0
        for row in connection.execute('''SELECT h.* FROM hub_cod_handoffs h WHERE h.hub_id=?
            AND NOT EXISTS(SELECT 1 FROM hub_cod_admin_receipt_lines l WHERE l.handoff_id=h.id)''', (hub['id'],)).fetchall():
            unremitted += _effective_received(connection, 'hub_cod_handoffs', row)
        hub['unremitted_cents'] = unremitted

    handoffs = []
    for row in connection.execute('''SELECT h.*,u.name driver_name,o.name hub_name
        FROM hub_cod_handoffs h JOIN users u ON u.id=h.driver_id JOIN ops_hubs o ON o.id=h.hub_id
        WHERE NOT EXISTS(SELECT 1 FROM hub_cod_admin_receipt_lines l WHERE l.handoff_id=h.id)
        ORDER BY h.id DESC LIMIT 500''').fetchall():
        item = dict(row)
        for private_key in ('request_key','payload_hash','actor_id'):
            item.pop(private_key, None)
        item['effective_received_cents'] = _effective_received(connection, 'hub_cod_handoffs', row)
        item['variance_cents'] = item['effective_received_cents'] - item['expected_cents']
        handoffs.append(item)

    settlements=[];settlement_handoffs=[]
    for row in connection.execute('''SELECT r.*,h.name hub_name FROM hub_cod_admin_receipts r
        JOIN ops_hubs h ON h.id=r.hub_id ORDER BY r.id DESC LIMIT 200''').fetchall():
        item=dict(row)
        for private_key in ('request_key','payload_hash','actor_id'):
            item.pop(private_key,None)
        item['effective_received_cents']=_effective_received(connection,'hub_cod_admin_receipts',row)
        item['variance_cents']=item['effective_received_cents']-item['expected_cents']
        linked=connection.execute('''SELECT COALESCE(sum(l.amount_cents),0) FROM hub_cod_settlement_links l
            JOIN driver_transactions t ON t.id=l.driver_transaction_id
            WHERE l.receipt_id=? AND t.voided_at IS NULL''',(row['id'],)).fetchone()[0]
        item['settlement_allocated_cents']=linked
        item['settlement_unlinked_cents']=max(0,item['effective_received_cents']-linked)
        item['settlement_handoffs']=[]
        for handoff_row in connection.execute('''SELECT h.*,u.name driver_name FROM hub_cod_admin_receipt_lines rl
            JOIN hub_cod_handoffs h ON h.id=rl.handoff_id JOIN users u ON u.id=h.driver_id
            WHERE rl.receipt_id=? ORDER BY h.id''',(row['id'],)).fetchall():
            handoff=dict(handoff_row)
            for private_key in ('request_key','payload_hash','actor_id'):
                handoff.pop(private_key,None)
            handoff['effective_received_cents']=_effective_received(connection,'hub_cod_handoffs',handoff_row)
            handoff['variance_cents']=handoff['effective_received_cents']-handoff['expected_cents']
            handoff['settlement_allocated_cents']=connection.execute('''SELECT COALESCE(sum(l.amount_cents),0)
                FROM hub_cod_settlement_links l JOIN driver_transactions t ON t.id=l.driver_transaction_id
                WHERE l.handoff_id=? AND t.voided_at IS NULL''',(handoff['id'],)).fetchone()[0]
            handoff['settlement_unlinked_cents']=max(0,handoff['effective_received_cents']-handoff['settlement_allocated_cents'])
            receipt_allocated=connection.execute('''SELECT COALESCE(sum(l.amount_cents),0)
                FROM hub_cod_settlement_links l JOIN driver_transactions t ON t.id=l.driver_transaction_id
                WHERE l.receipt_id=? AND t.voided_at IS NULL''',(row['id'],)).fetchone()[0]
            handoff['receipt_unlinked_cents']=max(0,item['effective_received_cents']-receipt_allocated)
            handoff['receipt_id']=row['id'];handoff['hub_name']=row['hub_name']
            link_rows=connection.execute('''SELECT l.id,l.statement_id,l.driver_transaction_id,l.amount_cents,
                    l.old_cash_remaining_cents,l.new_cash_remaining_cents,l.reason,l.actor_name,l.created_at,t.voided_at
                FROM hub_cod_settlement_links l JOIN driver_transactions t ON t.id=l.driver_transaction_id
                WHERE l.handoff_id=? ORDER BY l.id DESC''',(handoff['id'],)).fetchall()
            handoff['settlement_links']=[dict(link) for link in link_rows]
            item['settlement_handoffs'].append(handoff)
            settlement_handoffs.append({k:handoff[k] for k in ('id','receipt_id','hub_id','hub_name','driver_id','driver_name',
                'expected_cents','effective_received_cents','variance_cents','settlement_allocated_cents','settlement_unlinked_cents','receipt_unlinked_cents','created_at')})
        settlements.append(item)
    unassigned=connection.execute('''SELECT count(*) count,COALESCE(sum(amount_cents),0) amount_cents
        FROM ops_attempts WHERE outcome='Livré' AND amount_cents>0 AND cod_hub_id IS NULL''').fetchone()
    unlinked_total=sum(max(0,row['received_cents']+row['adjustments_cents']-row['linked_cents'])
        for row in connection.execute('''SELECT r.received_cents,COALESCE(a.adjustments_cents,0) adjustments_cents,
            COALESCE(l.linked_cents,0) linked_cents FROM hub_cod_admin_receipts r
            LEFT JOIN (SELECT record_id,sum(delta_cents) adjustments_cents FROM hub_cod_adjustments
                WHERE record_type='admin_receipt' GROUP BY record_id) a ON a.record_id=r.id
            LEFT JOIN (SELECT l.receipt_id,sum(l.amount_cents) linked_cents FROM hub_cod_settlement_links l
                JOIN driver_transactions t ON t.id=l.driver_transaction_id WHERE t.voided_at IS NULL GROUP BY l.receipt_id) l
                ON l.receipt_id=r.id''').fetchall())
    return {'hubs':hubs,'pending_handoffs':handoffs,'admin_receipts':settlements,
            'settlement_handoffs':settlement_handoffs,'settlement_unlinked_cents':unlinked_total,
            'unassigned_cod_count':unassigned['count'],'unassigned_cod_cents':unassigned['amount_cents']}


def record_driver_handoff(connection, *, hub_id, driver_id, received_cents, reason,
                          actor_id, actor_name, request_key, created_at):
    payload = {'hub_id': hub_id, 'driver_id': driver_id, 'received_cents': received_cents, 'reason': reason}
    hashed = _digest(payload)
    prior = connection.execute('SELECT * FROM hub_cod_handoffs WHERE request_key=?', (request_key,)).fetchone()
    if prior:
        if prior['actor_id'] != actor_id or prior['payload_hash'] != hashed:
            raise ValueError('Clé déjà utilisée pour une autre remise.')
        return {'id': prior['id'], 'already_recorded': True}
    driver = connection.execute("SELECT id FROM users WHERE id=? AND role IN ('livreur','driver')", (driver_id,)).fetchone()
    if not driver:
        raise ValueError('Livreur introuvable.')
    pending = _pending_attempts(connection, hub_id, driver_id)
    if not pending:
        raise ValueError('Aucun COD livré en attente de remise pour ce livreur et ce Hub.')
    expected = sum(row['amount_cents'] for row in pending)
    variance = received_cents - expected
    reason = str(reason or '').strip()
    if variance and not reason:
        raise ValueError('Motif obligatoire lorsque le montant reçu diffère du montant attendu.')
    cursor = connection.execute('''INSERT INTO hub_cod_handoffs(
        hub_id,driver_id,expected_cents,received_cents,variance_cents,reason,actor_id,actor_name,
        request_key,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
        (hub_id, driver_id, expected, received_cents, variance, reason, actor_id, actor_name,
         request_key, hashed, created_at))
    receipt_id = cursor.lastrowid
    connection.executemany('''INSERT INTO hub_cod_handoff_lines(handoff_id,attempt_id,amount_cents)
        VALUES(?,?,?)''', [(receipt_id, row['id'], row['amount_cents']) for row in pending])
    return {'id': receipt_id, 'already_recorded': False, 'expected_cents': expected,
            'received_cents': received_cents, 'variance_cents': variance, 'delivery_count': len(pending)}


def record_admin_receipt(connection, *, hub_id, handoff_ids, received_cents, reason,
                          actor_id, actor_name, request_key, created_at):
    if not isinstance(handoff_ids, list) or not handoff_ids or len(handoff_ids) > 500:
        raise ValueError('Sélectionnez de 1 à 500 remises de Hub.')
    if any(type(value) is not int or value <= 0 for value in handoff_ids) or len(set(handoff_ids)) != len(handoff_ids):
        raise ValueError('La sélection des remises est invalide ou répétée.')
    payload = {'hub_id': hub_id, 'handoff_ids': handoff_ids, 'received_cents': received_cents, 'reason': reason}
    hashed = _digest(payload)
    prior = connection.execute('SELECT * FROM hub_cod_admin_receipts WHERE request_key=?', (request_key,)).fetchone()
    if prior:
        if prior['actor_id'] != actor_id or prior['payload_hash'] != hashed:
            raise ValueError('Clé déjà utilisée pour une autre opération.')
        return {'id': prior['id'], 'already_recorded': True}
    marks = ','.join('?' for _ in handoff_ids)
    rows = connection.execute(f'''SELECT h.* FROM hub_cod_handoffs h
        WHERE h.id IN ({marks}) AND h.hub_id=?
          AND NOT EXISTS(SELECT 1 FROM hub_cod_admin_receipt_lines l WHERE l.handoff_id=h.id)''',
        [*handoff_ids, hub_id]).fetchall()
    if len(rows) != len(handoff_ids):
        raise ValueError('Une remise est introuvable, appartient à un autre Hub ou a déjà été rapprochée.')
    expected_amounts = {row['id']: _effective_received(connection, 'hub_cod_handoffs', row) for row in rows}
    expected = sum(expected_amounts.values())
    variance = received_cents - expected
    reason = str(reason or '').strip()
    if variance and not reason:
        raise ValueError('Motif obligatoire lorsque le montant reçu diffère du montant attendu.')
    cursor = connection.execute('''INSERT INTO hub_cod_admin_receipts(
        hub_id,expected_cents,received_cents,variance_cents,reason,actor_id,actor_name,
        request_key,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
        (hub_id, expected, received_cents, variance, reason, actor_id, actor_name,
         request_key, hashed, created_at))
    receipt_id = cursor.lastrowid
    connection.executemany('''INSERT INTO hub_cod_admin_receipt_lines(receipt_id,handoff_id,amount_cents)
        VALUES(?,?,?)''', [(receipt_id, row['id'], expected_amounts[row['id']]) for row in rows])
    return {'id': receipt_id, 'already_recorded': False, 'expected_cents': expected,
            'received_cents': received_cents, 'variance_cents': variance, 'handoff_count': len(rows)}


def add_adjustment(connection, *, record_type, record_id, delta_cents, reason,
                    actor_id, actor_name, request_key, created_at):
    table = {'driver_handoff': 'hub_cod_handoffs', 'admin_receipt': 'hub_cod_admin_receipts'}.get(record_type)
    if not table or type(record_id) is not int or record_id <= 0:
        raise ValueError('Écriture à ajuster introuvable.')
    if type(delta_cents) is not int or delta_cents == 0:
        raise ValueError('Un ajustement doit être différent de zéro.')
    reason = str(reason or '').strip()
    if not reason:
        raise ValueError('Motif obligatoire pour tout ajustement.')
    payload = {'record_type': record_type, 'record_id': record_id, 'delta_cents': delta_cents, 'reason': reason}
    hashed = _digest(payload)
    prior = connection.execute('SELECT * FROM hub_cod_adjustments WHERE request_key=?', (request_key,)).fetchone()
    if prior:
        if prior['actor_id'] != actor_id or prior['payload_hash'] != hashed:
            raise ValueError('Clé déjà utilisée pour une autre opération.')
        return {'id': prior['id'], 'already_recorded': True}
    row = connection.execute(f'SELECT * FROM {table} WHERE id=?', (record_id,)).fetchone()
    if not row:
        raise ValueError('Écriture à ajuster introuvable.')
    if record_type == 'driver_handoff' and connection.execute(
        'SELECT 1 FROM hub_cod_admin_receipt_lines WHERE handoff_id=?', (record_id,)
    ).fetchone():
        raise ValueError('Cette remise a déjà été rapprochée par l’Administration; ajustez le reçu Admin.')
    old_amount = _effective_received(connection, table, row)
    new_amount = old_amount + delta_cents
    if new_amount < 0:
        raise ValueError('L’ajustement ne peut pas produire un montant reçu négatif.')
    if record_type == 'admin_receipt':
        driver_linked = connection.execute('''SELECT COALESCE(sum(l.amount_cents),0)
            FROM hub_cod_settlement_links l JOIN driver_transactions t ON t.id=l.driver_transaction_id
            WHERE l.receipt_id=? AND t.voided_at IS NULL''', (record_id,)).fetchone()[0]
        invoice_links_exist=connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hub_invoice_settlement_links'").fetchone()
        invoice_linked=0
        if invoice_links_exist:
            invoice_linked=connection.execute('SELECT COALESCE(sum(amount_cents),0) FROM hub_invoice_settlement_links WHERE receipt_id=?',(record_id,)).fetchone()[0]
        # The same physical receipt may close both sides of the COD chain (Hub→Admin and
        # driver statement→Admin). Those ledgers mirror one cash movement, so compare floors
        # within each ledger rather than summing the two allocations.
        linked=max(int(driver_linked or 0),int(invoice_linked or 0))
        if new_amount < linked:
            raise ValueError('Le montant ne peut pas être réduit sous les règlements déjà liés; annulez-les d’abord manuellement.')
    cursor = connection.execute('''INSERT INTO hub_cod_adjustments(
        record_type,record_id,delta_cents,old_amount_cents,new_amount_cents,reason,
        actor_id,actor_name,request_key,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
        (record_type, record_id, delta_cents, old_amount, new_amount, reason,
         actor_id, actor_name, request_key, hashed, created_at))
    return {'id': cursor.lastrowid, 'already_recorded': False,
            'old_amount_cents': old_amount, 'new_amount_cents': new_amount}


def admin_settlement_options(connection, handoff_id, *, actor, statement_reader, balances_reader):
    """Return driver-matched statements and unallocated physical cash for an Admin review."""
    if type(handoff_id) is not int or handoff_id <= 0:
        raise ValueError('Remise de Hub invalide.')
    row = connection.execute('''SELECT r.id receipt_id,r.hub_id,r.received_cents,
        h.id handoff_id,h.driver_id,u.name driver_name,h.expected_cents,h.received_cents handoff_received_cents,
        h.created_at handoff_created_at,o.name hub_name
        FROM hub_cod_admin_receipt_lines rl
        JOIN hub_cod_admin_receipts r ON r.id=rl.receipt_id
        JOIN hub_cod_handoffs h ON h.id=rl.handoff_id
        JOIN users u ON u.id=h.driver_id
        JOIN ops_hubs o ON o.id=h.hub_id
        WHERE rl.handoff_id=?''', (handoff_id,)).fetchone()
    if not row:
        raise ValueError('Cette remise n’a pas encore été reçue par l’Administration.')
    handoff = dict(row)
    receipt_row = connection.execute('SELECT * FROM hub_cod_admin_receipts WHERE id=?',
                                     (handoff['receipt_id'],)).fetchone()
    handoff_row = connection.execute('SELECT * FROM hub_cod_handoffs WHERE id=?',
                                     (handoff_id,)).fetchone()
    receipt_received = _effective_received(connection, 'hub_cod_admin_receipts', receipt_row)
    handoff_received = _effective_received(connection, 'hub_cod_handoffs', handoff_row)
    allocated_handoff = connection.execute('''SELECT COALESCE(sum(l.amount_cents),0)
        FROM hub_cod_settlement_links l JOIN driver_transactions t ON t.id=l.driver_transaction_id
        WHERE l.handoff_id=? AND t.voided_at IS NULL''', (handoff_id,)).fetchone()[0]
    allocated_receipt = connection.execute('''SELECT COALESCE(sum(l.amount_cents),0)
        FROM hub_cod_settlement_links l JOIN driver_transactions t ON t.id=l.driver_transaction_id
        WHERE l.receipt_id=? AND t.voided_at IS NULL''', (handoff['receipt_id'],)).fetchone()[0]
    handoff_remaining = max(0, handoff_received - allocated_handoff)
    receipt_remaining = max(0, receipt_received - allocated_receipt)
    statements = []
    for statement_row in connection.execute('''SELECT s.id,s.driver_id,s.driver_name,s.mode,s.period_from,s.period_to,
            s.parcel_count,s.created_at FROM driver_statements s
        WHERE s.driver_id=? AND s.cancelled_at IS NULL
          AND EXISTS(
            SELECT 1 FROM driver_statement_lines sl
            JOIN ops_attempts a ON a.parcel_id=sl.parcel_id
            JOIN hub_cod_handoff_lines hl ON hl.attempt_id=a.id
            WHERE sl.statement_id=s.id AND sl.active=1 AND hl.handoff_id=?
          ) ORDER BY s.id DESC''', (handoff['driver_id'], handoff_id)).fetchall():
        raw = statement_reader(connection, statement_row['id'], actor)
        balance = balances_reader(connection, raw)
        if balance.get('cash_remaining_cents', 0) <= 0:
            continue
        match_count = connection.execute('''SELECT count(DISTINCT sl.parcel_id)
            FROM driver_statement_lines sl JOIN ops_attempts a ON a.parcel_id=sl.parcel_id
            JOIN hub_cod_handoff_lines hl ON hl.attempt_id=a.id
            WHERE sl.statement_id=? AND sl.active=1 AND hl.handoff_id=?''',
            (statement_row['id'], handoff_id)).fetchone()[0]
        statements.append({**dict(statement_row), 'cash_remaining_cents':balance['cash_remaining_cents'],
                           'matched_delivery_count':match_count})
    return {
        'receipt_id':handoff['receipt_id'],'hub_id':handoff['hub_id'],'hub_name':handoff['hub_name'],
        'receipt_received_cents':receipt_received,'receipt_remaining_cents':receipt_remaining,
        'handoff_id':handoff_id,'driver_id':handoff['driver_id'],'driver_name':handoff['driver_name'],
        'handoff_expected_cents':handoff['expected_cents'],'handoff_received_cents':handoff_received,
        'handoff_remaining_cents':handoff_remaining,'handoff_created_at':handoff['handoff_created_at'],
        'statements':statements,
    }


def record_admin_driver_settlement(connection, *, receipt_id, handoff_id, statement_id, amount_cents,
                                   reason, actor, request_key, paid_on, created_at,
                                   statement_reader, balances_reader, add_transaction_fn):
    """Manually post Hub COD cash to a matching driver statement; never initiates a transfer."""
    ids=(receipt_id,handoff_id,statement_id)
    if any(type(value) is not int or value <= 0 for value in ids):
        raise ValueError('Référence de rapprochement invalide.')
    if type(amount_cents) is not int or amount_cents <= 0:
        raise ValueError('Le montant à rapprocher doit être positif.')
    reason=str(reason or '').strip()
    payload={'receipt_id':receipt_id,'handoff_id':handoff_id,'statement_id':statement_id,
             'amount_cents':amount_cents,'reason':reason,'paid_on':paid_on}
    hashed=_digest(payload)
    prior=connection.execute('SELECT * FROM hub_cod_settlement_links WHERE request_key=?',(request_key,)).fetchone()
    if prior:
        if prior['actor_id']!=actor['id'] or prior['payload_hash']!=hashed:
            raise ValueError('Clé déjà utilisée pour un autre rapprochement.')
        return {'id':prior['id'],'transaction_id':prior['driver_transaction_id'],
                'already_recorded':True,'old_cash_remaining_cents':prior['old_cash_remaining_cents'],
                'new_cash_remaining_cents':prior['new_cash_remaining_cents']}
    receipt=connection.execute('''SELECT r.* FROM hub_cod_admin_receipts r
        JOIN hub_cod_admin_receipt_lines rl ON rl.receipt_id=r.id
        WHERE r.id=? AND rl.handoff_id=?''',(receipt_id,handoff_id)).fetchone()
    handoff=connection.execute('SELECT * FROM hub_cod_handoffs WHERE id=?',(handoff_id,)).fetchone()
    statement_row=connection.execute('SELECT * FROM driver_statements WHERE id=?',(statement_id,)).fetchone()
    if not receipt or not handoff or not statement_row:
        raise ValueError('Reçu, remise ou relevé introuvable.')
    if statement_row['driver_id']!=handoff['driver_id']:
        raise ValueError('Le relevé sélectionné appartient à un autre livreur.')
    if statement_row['cancelled_at']:
        raise ValueError('Le relevé sélectionné est annulé.')
    matched=connection.execute('''SELECT 1 FROM driver_statement_lines sl
        JOIN ops_attempts a ON a.parcel_id=sl.parcel_id
        JOIN hub_cod_handoff_lines hl ON hl.attempt_id=a.id
        WHERE sl.statement_id=? AND sl.active=1 AND hl.handoff_id=? LIMIT 1''',
        (statement_id,handoff_id)).fetchone()
    if not matched:
        raise ValueError('Le relevé ne contient aucun des colis de cette remise.')
    handoff_received=_effective_received(connection,'hub_cod_handoffs',handoff)
    receipt_received=_effective_received(connection,'hub_cod_admin_receipts',receipt)
    allocated_handoff=connection.execute('''SELECT COALESCE(sum(l.amount_cents),0)
        FROM hub_cod_settlement_links l JOIN driver_transactions t ON t.id=l.driver_transaction_id
        WHERE l.handoff_id=? AND t.voided_at IS NULL''',(handoff_id,)).fetchone()[0]
    allocated_receipt=connection.execute('''SELECT COALESCE(sum(l.amount_cents),0)
        FROM hub_cod_settlement_links l JOIN driver_transactions t ON t.id=l.driver_transaction_id
        WHERE l.receipt_id=? AND t.voided_at IS NULL''',(receipt_id,)).fetchone()[0]
    handoff_remaining=max(0,handoff_received-allocated_handoff)
    receipt_remaining=max(0,receipt_received-allocated_receipt)
    available=min(handoff_remaining,receipt_remaining)
    if amount_cents>available:
        raise ValueError('Le montant dépasse le cash reçu et encore non rapproché.')
    if amount_cents!=handoff_remaining and not reason:
        raise ValueError('Motif obligatoire pour un rapprochement partiel ou réparti entre plusieurs relevés.')
    raw_statement=statement_reader(connection,statement_id,actor)
    before=balances_reader(connection,raw_statement)
    old_cash=before.get('cash_remaining_cents',0)
    if amount_cents>old_cash:
        raise ValueError('Le montant dépasse le solde COD restant du relevé sélectionné.')
    reference=f'HUBCOD-R{receipt_id}-H{handoff_id}-{request_key[:12]}'
    note=f'Rapprochement manuel COD Hub · reçu {receipt_id} · remise {handoff_id}'
    if reason:note+=' · '+reason
    transaction=add_transaction_fn(connection,statement_id,actor,{
        'kind':'cash','amount':str(Decimal(amount_cents)/100),'method':'Espèces','reference':reference,
        'paid_on':paid_on,'note':note,'request_key':request_key,
    })
    transaction_id=transaction.get('transaction_id')
    if type(transaction_id) is not int or transaction_id<=0:
        raise ValueError('La transaction financière n’a pas été créée.')
    updated_statement=statement_reader(connection,statement_id,actor)
    after=balances_reader(connection,updated_statement)
    new_cash=after.get('cash_remaining_cents',0)
    if new_cash!=old_cash-amount_cents:
        raise ValueError('Le solde du relevé a changé; actualisez avant de confirmer.')
    cursor=connection.execute('''INSERT INTO hub_cod_settlement_links(
        receipt_id,handoff_id,statement_id,driver_transaction_id,amount_cents,
        old_cash_remaining_cents,new_cash_remaining_cents,reason,actor_id,actor_name,
        request_key,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (receipt_id,handoff_id,statement_id,transaction_id,amount_cents,old_cash,new_cash,reason,
         actor['id'],actor['name'],request_key,hashed,created_at))
    return {'id':cursor.lastrowid,'transaction_id':transaction_id,'already_recorded':False,
            'old_cash_remaining_cents':old_cash,'new_cash_remaining_cents':new_cash,
            'amount_cents':amount_cents,'available_cents':available}


def ensure_hub_cod_schema(connection):
    columns = {row[1] for row in connection.execute('PRAGMA table_info(ops_attempts)')}
    if 'cod_hub_id' not in columns:
        connection.execute('ALTER TABLE ops_attempts ADD COLUMN cod_hub_id INTEGER REFERENCES ops_hubs(id)')
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS hub_cod_handoffs(
            id INTEGER PRIMARY KEY,
            hub_id INTEGER NOT NULL REFERENCES ops_hubs(id),
            driver_id INTEGER NOT NULL REFERENCES users(id),
            expected_cents INTEGER NOT NULL CHECK(expected_cents>=0),
            received_cents INTEGER NOT NULL CHECK(received_cents>=0),
            variance_cents INTEGER NOT NULL,
            reason TEXT NOT NULL,
            actor_id INTEGER NOT NULL REFERENCES users(id),
            actor_name TEXT NOT NULL,
            request_key TEXT NOT NULL UNIQUE,
            payload_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hub_cod_handoff_lines(
            id INTEGER PRIMARY KEY,
            handoff_id INTEGER NOT NULL REFERENCES hub_cod_handoffs(id),
            attempt_id INTEGER NOT NULL UNIQUE REFERENCES ops_attempts(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents>=0)
        );
        CREATE TABLE IF NOT EXISTS hub_cod_admin_receipts(
            id INTEGER PRIMARY KEY,
            hub_id INTEGER NOT NULL REFERENCES ops_hubs(id),
            expected_cents INTEGER NOT NULL CHECK(expected_cents>=0),
            received_cents INTEGER NOT NULL CHECK(received_cents>=0),
            variance_cents INTEGER NOT NULL,
            reason TEXT NOT NULL,
            actor_id INTEGER NOT NULL REFERENCES users(id),
            actor_name TEXT NOT NULL,
            request_key TEXT NOT NULL UNIQUE,
            payload_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hub_cod_admin_receipt_lines(
            id INTEGER PRIMARY KEY,
            receipt_id INTEGER NOT NULL REFERENCES hub_cod_admin_receipts(id),
            handoff_id INTEGER NOT NULL UNIQUE REFERENCES hub_cod_handoffs(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents>=0)
        );
        CREATE TABLE IF NOT EXISTS hub_cod_adjustments(
            id INTEGER PRIMARY KEY,
            record_type TEXT NOT NULL CHECK(record_type IN ('driver_handoff','admin_receipt')),
            record_id INTEGER NOT NULL,
            delta_cents INTEGER NOT NULL CHECK(delta_cents<>0),
            old_amount_cents INTEGER NOT NULL CHECK(old_amount_cents>=0),
            new_amount_cents INTEGER NOT NULL CHECK(new_amount_cents>=0),
            reason TEXT NOT NULL,
            actor_id INTEGER NOT NULL REFERENCES users(id),
            actor_name TEXT NOT NULL,
            request_key TEXT NOT NULL UNIQUE,
            payload_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hub_cod_settlement_links(
            id INTEGER PRIMARY KEY,
            receipt_id INTEGER NOT NULL REFERENCES hub_cod_admin_receipts(id),
            handoff_id INTEGER NOT NULL REFERENCES hub_cod_handoffs(id),
            statement_id INTEGER NOT NULL REFERENCES driver_statements(id),
            driver_transaction_id INTEGER NOT NULL UNIQUE REFERENCES driver_transactions(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
            old_cash_remaining_cents INTEGER NOT NULL CHECK(old_cash_remaining_cents>=0),
            new_cash_remaining_cents INTEGER NOT NULL CHECK(new_cash_remaining_cents>=0),
            reason TEXT NOT NULL,
            actor_id INTEGER NOT NULL REFERENCES users(id),
            actor_name TEXT NOT NULL,
            request_key TEXT NOT NULL UNIQUE,
            payload_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS hub_cod_handoffs_hub_driver ON hub_cod_handoffs(hub_id,driver_id,id);
        CREATE INDEX IF NOT EXISTS hub_cod_receipt_lines_attempt ON hub_cod_handoff_lines(attempt_id);
        CREATE INDEX IF NOT EXISTS hub_cod_settlement_receipt ON hub_cod_settlement_links(receipt_id,id);
    ''')
    install_hub_cod_audit_guards(connection)


def register_hub_cod(app, services):
    from flask import jsonify, request
    conn, auth, user, now, text, Error = (services[k] for k in ('conn','auth','user','now','text','APIError'))
    append_audit_log = services['append_audit_log']
    with conn() as c:
        ensure_hub_cod_schema(c)

    def actor_log(c, actor, action, entity_type, entity_id, old_value, new_value, metadata=None):
        append_audit_log(c, actor_id=actor['id'], actor_name=actor['name'], action=action,
                         entity_type=entity_type, entity_id=entity_id, old_value=old_value,
                         new_value=new_value, metadata=metadata or {}, created_at=now())

    def key(d):
        value=text(d,'request_key',maxlen=80)
        if not re.fullmatch(r'[A-Za-z0-9_-]{20,80}', value):
            raise Error('Clé de remise invalide.')
        return value

    def manager_hub(actor, requested=None):
        hub_id=actor.get('agent_hub_id') if actor['role']=='agent' else requested
        if type(hub_id) is not int or hub_id<=0:
            raise Error('Hub invalide.')
        with conn() as c:
            row=c.execute('SELECT id,active FROM ops_hubs WHERE id=?',(hub_id,)).fetchone()
        if not row or not row['active']:
            raise Error('Hub actif introuvable.',403)
        if actor['role']=='agent' and hub_id!=actor.get('agent_hub_id'):
            raise Error('Accès refusé à un autre Hub.',403)
        return hub_id

    @app.get(_PREFIX+'/hub')
    @auth('admin','agent')
    def hub_cod_overview():
        actor=user()
        requested=request.args.get('hub_id',type=int) if actor['role']=='admin' else None
        hub_id=manager_hub(actor,requested)
        with conn() as c:
            c.execute('BEGIN')
            try:result=manager_overview(c,hub_id)
            except ValueError as exc:raise Error(str(exc),403)
            return jsonify(result)

    @app.post(_PREFIX+'/hub/handoffs')
    @auth('admin','agent')
    def hub_cod_handoff_create():
        d=request.get_json(silent=True);actor=user()
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        hub_id=manager_hub(actor,d.get('hub_id'))
        driver_id=d.get('driver_id')
        if type(driver_id) is not int or driver_id<=0:raise Error('Livreur invalide.')
        try:received_cents=money_cents(d.get('received_amount'))
        except ValueError as exc:raise Error(str(exc))
        reason=text(d,'reason',False,maxlen=600);request_key=key(d)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                result=record_driver_handoff(c,hub_id=hub_id,driver_id=driver_id,
                    received_cents=received_cents,reason=reason,actor_id=actor['id'],actor_name=actor['name'],
                    request_key=request_key,created_at=now())
            except ValueError as exc:raise Error(str(exc),409)
            if not result.get('already_recorded'):
                actor_log(c,actor,'hub_driver_cod_handoff_recorded','hub_cod_handoff',result['id'],None,
                          {k:result.get(k) for k in ('id','expected_cents','received_cents','variance_cents','delivery_count')},
                          {'hub_id':hub_id,'driver_id':driver_id,'reason':reason})
            return jsonify(ok=True,**result)

    @app.get(_PREFIX+'/admin')
    @auth('admin')
    def hub_cod_admin_overview():
        with conn() as c:
            c.execute('BEGIN')
            return jsonify(admin_overview(c))

    @app.post(_PREFIX+'/admin/receipts')
    @auth('admin')
    def hub_cod_admin_receipt_create():
        d=request.get_json(silent=True);actor=user()
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        hub_id=d.get('hub_id')
        if type(hub_id) is not int or hub_id<=0:raise Error('Hub invalide.')
        try:received_cents=money_cents(d.get('received_amount'))
        except ValueError as exc:raise Error(str(exc))
        reason=text(d,'reason',False,maxlen=600);request_key=key(d)
        handoff_ids=d.get('handoff_ids')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            hub_row=c.execute('SELECT id FROM ops_hubs WHERE id=?',(hub_id,)).fetchone()
            if not hub_row:raise Error('Hub introuvable.',404)
            try:
                result=record_admin_receipt(c,hub_id=hub_id,handoff_ids=handoff_ids,
                    received_cents=received_cents,reason=reason,actor_id=actor['id'],actor_name=actor['name'],
                    request_key=request_key,created_at=now())
            except ValueError as exc:raise Error(str(exc),409)
            if not result.get('already_recorded'):
                actor_log(c,actor,'hub_cod_received_by_admin','hub_cod_admin_receipt',result['id'],None,
                          {k:result.get(k) for k in ('id','expected_cents','received_cents','variance_cents','handoff_count')},
                          {'hub_id':hub_id,'handoff_ids':handoff_ids,'reason':reason})
            return jsonify(ok=True,**result)

    @app.get(_PREFIX+'/admin/handoffs/<int:handoff_id>/settlement-options')
    @auth('admin')
    def hub_cod_admin_settlement_options(handoff_id):
        actor=user()
        with conn() as c:
            c.execute('BEGIN')
            try:
                result=admin_settlement_options(c,handoff_id,actor=actor,
                    statement_reader=services['driver_finance_statement'],
                    balances_reader=services['driver_finance_balances'])
            except ValueError as exc:raise Error(str(exc),404)
            return jsonify(result)

    @app.post(_PREFIX+'/admin/receipts/<int:receipt_id>/settlements')
    @auth('admin')
    def hub_cod_admin_settlement_link_create(receipt_id):
        d=request.get_json(silent=True);actor=user()
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        if d.get('confirmed') is not True:raise Error('Confirmez explicitement le rapprochement manuel.')
        handoff_id=d.get('handoff_id');statement_id=d.get('statement_id')
        if type(handoff_id) is not int or handoff_id<=0:raise Error('Remise de Hub invalide.')
        if type(statement_id) is not int or statement_id<=0:raise Error('Relevé livreur invalide.')
        try:amount_cents=money_cents(d.get('amount'))
        except ValueError as exc:raise Error(str(exc))
        if amount_cents<=0:raise Error('Le montant à rapprocher doit être strictement positif.')
        reason=text(d,'reason',False,maxlen=600);paid_on=text(d,'paid_on',maxlen=10);request_key=key(d)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                result=record_admin_driver_settlement(c,receipt_id=receipt_id,handoff_id=handoff_id,
                    statement_id=statement_id,amount_cents=amount_cents,reason=reason,actor=actor,
                    request_key=request_key,paid_on=paid_on,created_at=now(),
                    statement_reader=services['driver_finance_statement'],
                    balances_reader=services['driver_finance_balances'],
                    add_transaction_fn=services['add_driver_transaction'])
            except ValueError as exc:raise Error(str(exc),409)
            if not result.get('already_recorded'):
                actor_log(c,actor,'hub_cod_driver_statement_settlement_linked','hub_cod_settlement_link',
                    result['id'],{'cash_remaining_cents':result['old_cash_remaining_cents']},
                    {'cash_remaining_cents':result['new_cash_remaining_cents'],
                     'amount_cents':result['amount_cents'],'driver_transaction_id':result['transaction_id']},
                    {'receipt_id':receipt_id,'handoff_id':handoff_id,'statement_id':statement_id,'reason':reason})
            return jsonify(ok=True,**result)

    @app.post(_PREFIX+'/admin/adjustments')
    @auth('admin')
    def hub_cod_admin_adjustment_create():
        d=request.get_json(silent=True);actor=user()
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        record_type=d.get('record_type');record_id=d.get('record_id')
        if type(record_id) is not int or record_id<=0:raise Error('Reçu à ajuster invalide.')
        try:delta_cents=money_cents(d.get('delta_amount'),signed=True)
        except ValueError as exc:raise Error(str(exc))
        reason=text(d,'reason',maxlen=600);request_key=key(d)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                result=add_adjustment(c,record_type=record_type,record_id=record_id,delta_cents=delta_cents,
                    reason=reason,actor_id=actor['id'],actor_name=actor['name'],request_key=request_key,created_at=now())
            except ValueError as exc:raise Error(str(exc),409)
            if not result.get('already_recorded'):
                actor_log(c,actor,'hub_cod_adjustment_added','hub_cod_adjustment',result['id'],
                          {'amount_cents':result['old_amount_cents']},{'amount_cents':result['new_amount_cents']},
                          {'record_type':record_type,'record_id':record_id,'delta_cents':delta_cents,'reason':reason})
            return jsonify(ok=True,**result)
