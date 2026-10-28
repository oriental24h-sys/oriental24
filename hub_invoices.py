"""Admin-issued, Hub-scoped COD invoices and manual settlement links.

Invoices snapshot gross COD from Hub-attributed delivered attempts. Driver commissions,
fees, client invoices, and bank transfers are outside this ledger. Cash receipts are only
recorded after Admin confirmation; allocations are append-only and capped.
"""
import hashlib
import json
import re
from datetime import datetime

from hub_cod import _effective_received, money_cents


_PREFIX = '/api/logistics/hub-invoices'
_MANAGER_PREFIX = '/api/logistics/hub/invoices'


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def _valid_period(period_from, period_to):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(period_from or '')):
            raise ValueError()
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(period_to or '')):
            raise ValueError()
        start = datetime.strptime(period_from, '%Y-%m-%d')
        end = datetime.strptime(period_to, '%Y-%m-%d')
        if start.strftime('%Y-%m-%d') != period_from or end.strftime('%Y-%m-%d') != period_to:
            raise ValueError()
        if start > end or (end - start).days > 365:
            raise ValueError()
        return period_from, period_to
    except (ValueError, TypeError):
        raise ValueError('Période invalide (366 jours maximum).')


def ensure_hub_invoice_schema(connection):
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS hub_invoices(
            id INTEGER PRIMARY KEY,
            hub_id INTEGER NOT NULL REFERENCES ops_hubs(id),
            period_from TEXT NOT NULL,
            period_to TEXT NOT NULL,
            delivery_count INTEGER NOT NULL CHECK(delivery_count>0),
            total_cents INTEGER NOT NULL CHECK(total_cents>=0),
            status TEXT NOT NULL CHECK(status IN ('draft','issued','cancelled')),
            request_key TEXT NOT NULL UNIQUE,
            payload_hash TEXT NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            issued_by INTEGER REFERENCES users(id),
            issued_at TEXT,
            cancelled_by INTEGER REFERENCES users(id),
            cancelled_at TEXT,
            cancel_reason TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_hub_invoices_hub_status
            ON hub_invoices(hub_id,status,id);
        CREATE TABLE IF NOT EXISTS hub_invoice_lines(
            id INTEGER PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES hub_invoices(id),
            attempt_id INTEGER NOT NULL REFERENCES ops_attempts(id),
            parcel_id INTEGER NOT NULL REFERENCES parcels(id),
            tracking TEXT NOT NULL,
            delivery_at TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
            UNIQUE(invoice_id,attempt_id)
        );
        CREATE INDEX IF NOT EXISTS idx_hub_invoice_lines_attempt ON hub_invoice_lines(attempt_id);
        CREATE TABLE IF NOT EXISTS hub_invoice_settlement_links(
            id INTEGER PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES hub_invoices(id),
            receipt_id INTEGER NOT NULL REFERENCES hub_cod_admin_receipts(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
            old_balance_cents INTEGER NOT NULL CHECK(old_balance_cents>=0),
            new_balance_cents INTEGER NOT NULL CHECK(new_balance_cents>=0),
            reason TEXT NOT NULL,
            actor_id INTEGER NOT NULL REFERENCES users(id),
            actor_name TEXT NOT NULL,
            request_key TEXT NOT NULL UNIQUE,
            payload_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hub_invoice_settlements_invoice
            ON hub_invoice_settlement_links(invoice_id,id);
        CREATE INDEX IF NOT EXISTS idx_hub_invoice_settlements_receipt
            ON hub_invoice_settlement_links(receipt_id,id);
        CREATE TABLE IF NOT EXISTS hub_invoice_adjustments(
            id INTEGER PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES hub_invoices(id),
            delta_cents INTEGER NOT NULL CHECK(delta_cents<>0),
            old_total_cents INTEGER NOT NULL CHECK(old_total_cents>=0),
            new_total_cents INTEGER NOT NULL CHECK(new_total_cents>=0),
            reason TEXT NOT NULL,
            actor_id INTEGER NOT NULL REFERENCES users(id),
            actor_name TEXT NOT NULL,
            request_key TEXT NOT NULL UNIQUE,
            payload_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hub_invoice_adjustments_invoice
            ON hub_invoice_adjustments(invoice_id,id);
        CREATE TRIGGER IF NOT EXISTS hub_invoice_header_transition_only
        BEFORE UPDATE ON hub_invoices
        WHEN OLD.status!='draft'
          OR NEW.status NOT IN ('issued','cancelled')
          OR NEW.id IS NOT OLD.id
          OR NEW.hub_id IS NOT OLD.hub_id
          OR NEW.period_from IS NOT OLD.period_from
          OR NEW.period_to IS NOT OLD.period_to
          OR NEW.delivery_count IS NOT OLD.delivery_count
          OR NEW.total_cents IS NOT OLD.total_cents
          OR NEW.request_key IS NOT OLD.request_key
          OR NEW.payload_hash IS NOT OLD.payload_hash
          OR NEW.created_by IS NOT OLD.created_by
          OR NEW.created_at IS NOT OLD.created_at
          OR (NEW.status='issued' AND (NEW.issued_by IS NULL OR NEW.issued_at IS NULL
              OR NEW.cancelled_by IS NOT NULL OR NEW.cancelled_at IS NOT NULL OR NEW.cancel_reason IS NOT NULL))
          OR (NEW.status='cancelled' AND (NEW.cancelled_by IS NULL OR NEW.cancelled_at IS NULL
              OR length(trim(COALESCE(NEW.cancel_reason,'')))=0
              OR NEW.issued_by IS NOT NULL OR NEW.issued_at IS NOT NULL))
        BEGIN
            SELECT RAISE(ABORT,'invalid or immutable Hub invoice transition');
        END;
        CREATE TRIGGER IF NOT EXISTS hub_invoice_line_insert_guard
        BEFORE INSERT ON hub_invoice_lines
        WHEN (SELECT status FROM hub_invoices WHERE id=NEW.invoice_id)!='draft'
          OR EXISTS(SELECT 1 FROM hub_invoice_lines l JOIN hub_invoices i ON i.id=l.invoice_id
                    WHERE l.attempt_id=NEW.attempt_id AND i.status!='cancelled')
        BEGIN
            SELECT RAISE(ABORT,'Hub COD attempt already claimed by an active invoice');
        END;
        CREATE TRIGGER IF NOT EXISTS hub_invoice_settlement_insert_guard
        BEFORE INSERT ON hub_invoice_settlement_links
        WHEN (SELECT status FROM hub_invoices WHERE id=NEW.invoice_id)!='issued'
          OR (SELECT hub_id FROM hub_invoices WHERE id=NEW.invoice_id)
             !=(SELECT hub_id FROM hub_cod_admin_receipts WHERE id=NEW.receipt_id)
        BEGIN
            SELECT RAISE(ABORT,'Hub invoice settlement scope or status invalid');
        END;
    ''')
    receipt_columns={row[1] for row in connection.execute('PRAGMA table_info(hub_cod_admin_receipts)')}
    if 'source_type' not in receipt_columns:
        connection.execute("ALTER TABLE hub_cod_admin_receipts ADD COLUMN source_type TEXT NOT NULL DEFAULT 'driver_handoff'")
    if 'invoice_id' not in receipt_columns:
        connection.execute('ALTER TABLE hub_cod_admin_receipts ADD COLUMN invoice_id INTEGER REFERENCES hub_invoices(id)')
    from audit_guard import install_hub_invoice_audit_guards
    install_hub_invoice_audit_guards(connection)


def _invoice_summary(connection, row):
    item = dict(row)
    item['base_total_cents']=int(item['total_cents'])
    adjustment=connection.execute('SELECT COALESCE(sum(delta_cents),0) FROM hub_invoice_adjustments WHERE invoice_id=?',(item['id'],)).fetchone()[0]
    item['adjustments_cents']=int(adjustment or 0)
    item['total_cents']=item['base_total_cents']+item['adjustments_cents']
    paid = connection.execute('''SELECT COALESCE(sum(amount_cents),0)
        FROM hub_invoice_settlement_links WHERE invoice_id=?''', (item['id'],)).fetchone()[0]
    item['paid_cents'] = int(paid or 0)
    item['remaining_cents'] = max(0, int(item['total_cents']) - item['paid_cents'])
    item['reference'] = f"HUB-{item['hub_id']:03d}-{item['id']:06d}"
    item['settlement_status'] = (
        'Brouillon' if item['status']=='draft' else
        'Annulée' if item['status']=='cancelled' else
        'Ajustée à zéro' if item['total_cents']==0 and item['paid_cents']==0 else
        'Soldée' if item['remaining_cents']==0 else
        'Partielle' if item['paid_cents']>0 else 'Émise'
    )
    return item


def create_hub_invoice_draft(connection, *, hub_id, period_from, period_to,
                             actor_id, request_key, created_at):
    if type(hub_id) is not int or hub_id <= 0:
        raise ValueError('Hub invalide.')
    if not isinstance(request_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}', request_key):
        raise ValueError('Clé de génération invalide.')
    period_from, period_to = _valid_period(period_from, period_to)
    hub = connection.execute('SELECT id FROM ops_hubs WHERE id=?', (hub_id,)).fetchone()
    if not hub:
        raise ValueError('Hub introuvable.')
    payload = {'hub_id':hub_id,'period_from':period_from,'period_to':period_to}
    hashed = _digest(payload)
    prior = connection.execute('SELECT * FROM hub_invoices WHERE request_key=?', (request_key,)).fetchone()
    if prior:
        if prior['created_by'] != actor_id or prior['payload_hash'] != hashed:
            raise ValueError('Clé déjà utilisée pour une autre génération.')
        return {'already_created':True,**_invoice_summary(connection, prior)}
    lines = connection.execute('''SELECT a.id attempt_id,a.parcel_id,p.tracking,a.created_at delivery_at,a.amount_cents
        FROM ops_attempts a JOIN parcels p ON p.id=a.parcel_id
        WHERE a.cod_hub_id=? AND a.outcome='Livré' AND a.amount_cents>0
          AND substr(a.created_at,1,10) BETWEEN ? AND ?
          AND NOT EXISTS(
              SELECT 1 FROM hub_invoice_lines l JOIN hub_invoices i ON i.id=l.invoice_id
              WHERE l.attempt_id=a.id AND i.status!='cancelled'
          )
        ORDER BY a.created_at,a.id''', (hub_id,period_from,period_to)).fetchall()
    if not lines:
        raise ValueError('Aucun COD livré, attribué à ce Hub et non facturé dans cette période.')
    if len(lines)>10000:
        raise ValueError('Plus de 10 000 livraisons : réduisez la période de génération.')
    total = sum(int(line['amount_cents']) for line in lines)
    cursor = connection.execute('''INSERT INTO hub_invoices(
        hub_id,period_from,period_to,delivery_count,total_cents,status,request_key,payload_hash,created_by,created_at)
        VALUES(?,?,?,?,?,'draft',?,?,?,?)''',
        (hub_id,period_from,period_to,len(lines),total,request_key,hashed,actor_id,created_at))
    invoice_id = cursor.lastrowid
    connection.executemany('''INSERT INTO hub_invoice_lines(
        invoice_id,attempt_id,parcel_id,tracking,delivery_at,amount_cents) VALUES(?,?,?,?,?,?)''',
        [(invoice_id,line['attempt_id'],line['parcel_id'],line['tracking'],line['delivery_at'],line['amount_cents'])
         for line in lines])
    row = connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
    return {'already_created':False,**_invoice_summary(connection,row)}


def issue_hub_invoice(connection, *, invoice_id, actor_id, issued_at):
    row = connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
    if not row:
        raise ValueError('Facture Hub introuvable.')
    if row['status']=='issued':
        return {'already_issued':True,**_invoice_summary(connection,row)}
    if row['status']!='draft':
        raise ValueError('Cette facture n’est plus une brouillon active.')
    lines = connection.execute('''SELECT l.*,a.cod_hub_id,a.outcome,a.amount_cents source_amount,
            a.created_at source_created_at,a.parcel_id source_parcel_id
        FROM hub_invoice_lines l LEFT JOIN ops_attempts a ON a.id=l.attempt_id
        WHERE l.invoice_id=?''',(invoice_id,)).fetchall()
    if (not lines or len(lines)!=row['delivery_count']
            or sum(int(line['amount_cents']) for line in lines)!=row['total_cents']
            or any(line['cod_hub_id']!=row['hub_id'] or line['outcome']!='Livré'
                   or line['source_amount']!=line['amount_cents']
                   or line['source_created_at']!=line['delivery_at']
                   or line['source_parcel_id']!=line['parcel_id'] for line in lines)):
        raise ValueError('Le contenu du brouillon a changé ou n’est plus cohérent. Annulez-le avec motif et recréez-le.')
    connection.execute("UPDATE hub_invoices SET status='issued',issued_by=?,issued_at=? WHERE id=?",
                       (actor_id,issued_at,invoice_id))
    updated=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
    return {'already_issued':False,**_invoice_summary(connection,updated)}


def cancel_hub_invoice_draft(connection, *, invoice_id, actor_id, cancelled_at, reason):
    reason=str(reason or '').strip()
    if not reason:
        raise ValueError('Motif obligatoire pour annuler un brouillon.')
    row=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
    if not row:
        raise ValueError('Facture Hub introuvable.')
    if row['status']!='draft':
        raise ValueError('Seul un brouillon peut être annulé; une facture émise n’est jamais effacée ni inversée automatiquement.')
    connection.execute("UPDATE hub_invoices SET status='cancelled',cancelled_by=?,cancelled_at=?,cancel_reason=? WHERE id=?",
                       (actor_id,cancelled_at,reason,invoice_id))
    updated=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
    return _invoice_summary(connection,updated)


def _link_receipt(connection, *, invoice, receipt, amount_cents, reason,
                  actor_id, actor_name, request_key, created_at, payload_extra=None):
    reason=str(reason or '').strip()
    payload={'invoice_id':invoice['id'],'receipt_id':receipt['id'],'amount_cents':amount_cents,
             'reason':reason,**(payload_extra or {})}
    hashed=_digest(payload)
    prior=connection.execute('SELECT * FROM hub_invoice_settlement_links WHERE request_key=?',(request_key,)).fetchone()
    if prior:
        if prior['actor_id']!=actor_id or prior['payload_hash']!=hashed:
            raise ValueError('Clé déjà utilisée pour un autre rapprochement.')
        current_invoice=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice['id'],)).fetchone()
        effective=_effective_received(connection,'hub_cod_admin_receipts',receipt)
        allocated=connection.execute('SELECT COALESCE(sum(amount_cents),0) FROM hub_invoice_settlement_links WHERE receipt_id=?',(receipt['id'],)).fetchone()[0]
        return {'already_recorded':True,'link_id':prior['id'],
                'invoice':_invoice_summary(connection,current_invoice),
                'receipt_remaining_cents':max(0,effective-allocated)}
    current=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice['id'],)).fetchone()
    if not current or current['status']!='issued':
        raise ValueError('Seule une facture Hub émise peut être réglée.')
    fresh_receipt=connection.execute('SELECT * FROM hub_cod_admin_receipts WHERE id=?',(receipt['id'],)).fetchone()
    if not fresh_receipt or fresh_receipt['hub_id']!=current['hub_id']:
        raise ValueError('Le reçu Admin appartient à un autre Hub ou est introuvable.')
    current_summary=_invoice_summary(connection,current)
    due=current_summary['remaining_cents']
    effective=_effective_received(connection,'hub_cod_admin_receipts',fresh_receipt)
    allocated=connection.execute('SELECT COALESCE(sum(amount_cents),0) FROM hub_invoice_settlement_links WHERE receipt_id=?',(fresh_receipt['id'],)).fetchone()[0]
    receipt_remaining=max(0,int(effective)-int(allocated or 0))
    cap=min(due,receipt_remaining)
    if type(amount_cents) is not int or amount_cents<=0 or amount_cents>cap:
        raise ValueError('Le rapprochement dépasse le solde de la facture ou le reçu Admin encore disponible.')
    if amount_cents!=cap and not reason:
        raise ValueError('Motif obligatoire pour un rapprochement partiel ou réparti.')
    new_balance=due-amount_cents
    cursor=connection.execute('''INSERT INTO hub_invoice_settlement_links(
        invoice_id,receipt_id,amount_cents,old_balance_cents,new_balance_cents,reason,
        actor_id,actor_name,request_key,payload_hash,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
        (current['id'],fresh_receipt['id'],amount_cents,due,new_balance,reason,actor_id,actor_name,
         request_key,hashed,created_at))
    updated=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(current['id'],)).fetchone()
    return {'already_recorded':False,'link_id':cursor.lastrowid,'invoice':_invoice_summary(connection,updated),
            'receipt_remaining_cents':receipt_remaining-amount_cents,'amount_cents':amount_cents}


def link_existing_admin_receipt(connection, *, invoice_id, receipt_id, amount_cents, reason,
                                actor_id, actor_name, request_key, created_at):
    invoice=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
    receipt=connection.execute('SELECT * FROM hub_cod_admin_receipts WHERE id=?',(receipt_id,)).fetchone()
    if not invoice or not receipt:
        raise ValueError('Facture ou reçu Admin introuvable.')
    return _link_receipt(connection,invoice=invoice,receipt=receipt,amount_cents=amount_cents,
        reason=reason,actor_id=actor_id,actor_name=actor_name,request_key=request_key,
        created_at=created_at)


def record_hub_invoice_receipt(connection, *, invoice_id, received_cents, applied_cents,
                               reason, actor_id, actor_name, request_key, created_at,
                               not_recorded_before=False):
    invoice=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
    if not invoice or invoice['status']!='issued':
        raise ValueError('Seule une facture Hub émise peut recevoir un règlement.')
    if not_recorded_before is not True:
        raise ValueError('Confirmez que ce cash n’a pas déjà été enregistré dans Caisse COD.')
    if type(received_cents) is not int or received_cents<=0:
        raise ValueError('Le montant reçu doit être positif.')
    if type(applied_cents) is not int or applied_cents<=0 or applied_cents>received_cents:
        raise ValueError('Le montant relié doit être positif et ne pas dépasser le cash reçu.')
    reason=str(reason or '').strip()
    receipt_payload={'source':'hub_invoice','invoice_id':invoice_id,'hub_id':invoice['hub_id'],
                     'received_cents':received_cents,'applied_cents':applied_cents,'reason':reason}
    receipt_hash=_digest(receipt_payload)
    prior=connection.execute('SELECT * FROM hub_cod_admin_receipts WHERE request_key=?',(request_key,)).fetchone()
    if prior:
        if prior['actor_id']!=actor_id or prior['payload_hash']!=receipt_hash:
            raise ValueError('Clé déjà utilisée pour une autre réception.')
        link=connection.execute('SELECT * FROM hub_invoice_settlement_links WHERE request_key=?',(request_key,)).fetchone()
        if not link or link['invoice_id']!=invoice_id:
            raise ValueError('Le reçu idempotent ne possède pas son lien de facture attendu.')
        fresh=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
        return {'already_recorded':True,'receipt_id':prior['id'],'amount_received_cents':prior['received_cents'],
                'amount_applied_cents':link['amount_cents'],'invoice':_invoice_summary(connection,fresh),
                'unlinked_cents':max(0,prior['received_cents']-link['amount_cents'])}
    existing_unlinked=0
    for old_receipt in connection.execute('SELECT * FROM hub_cod_admin_receipts WHERE hub_id=?',(invoice['hub_id'],)).fetchall():
        effective=_effective_received(connection,'hub_cod_admin_receipts',old_receipt)
        allocated=connection.execute('SELECT COALESCE(sum(amount_cents),0) FROM hub_invoice_settlement_links WHERE receipt_id=?',(old_receipt['id'],)).fetchone()[0]
        existing_unlinked+=max(0,int(effective)-int(allocated or 0))
    if existing_unlinked:
        raise ValueError('Il existe déjà un reçu Admin non relié pour ce Hub; reliez-le au lieu de ressaisir le cash.')
    pending_handoffs=connection.execute('''SELECT count(DISTINCT h.id)
        FROM hub_invoice_lines il JOIN hub_cod_handoff_lines hl ON hl.attempt_id=il.attempt_id
        JOIN hub_cod_handoffs h ON h.id=hl.handoff_id
        WHERE il.invoice_id=? AND NOT EXISTS(
            SELECT 1 FROM hub_cod_admin_receipt_lines rl WHERE rl.handoff_id=h.id
        )''',(invoice_id,)).fetchone()[0]
    if pending_handoffs:
        raise ValueError('Des remises chauffeur→Hub de cette facture attendent encore la réception Admin; enregistrez-les dans Caisse COD avant toute nouvelle saisie.')
    due=_invoice_summary(connection,invoice)['remaining_cents']
    if due<=0:
        raise ValueError('La facture Hub est déjà soldée; tout nouvel excédent doit rester non relié.')
    if applied_cents>due:
        raise ValueError('Le montant relié dépasse le solde restant de la facture; l’excédent restera non relié.')
    if (received_cents!=due or applied_cents!=min(received_cents,due)) and not reason:
        raise ValueError('Motif obligatoire pour un reçu partiel, excédentaire ou partiellement relié.')
    variance=received_cents-due
    receipt_cursor=connection.execute('''INSERT INTO hub_cod_admin_receipts(
        hub_id,expected_cents,received_cents,variance_cents,reason,actor_id,actor_name,
        request_key,payload_hash,created_at,source_type,invoice_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
        (invoice['hub_id'],due,received_cents,variance,reason,actor_id,actor_name,request_key,
         receipt_hash,created_at,'hub_invoice',invoice_id))
    receipt=connection.execute('SELECT * FROM hub_cod_admin_receipts WHERE id=?',(receipt_cursor.lastrowid,)).fetchone()
    linked=_link_receipt(connection,invoice=invoice,receipt=receipt,amount_cents=applied_cents,
        reason=reason,actor_id=actor_id,actor_name=actor_name,request_key=request_key,
        created_at=created_at,payload_extra={'source':'hub_invoice','received_cents':received_cents,
                                             'applied_cents':applied_cents})
    return {'already_recorded':False,'receipt_id':receipt['id'],'amount_received_cents':received_cents,
            'amount_applied_cents':applied_cents,'invoice':linked['invoice'],
            'unlinked_cents':max(0,received_cents-applied_cents)}


def adjust_hub_invoice(connection, *, invoice_id, delta_cents, reason, actor_id, actor_name,
                       request_key, created_at):
    invoice=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
    if not invoice or invoice['status']!='issued':
        raise ValueError('Seule une facture Hub émise peut être ajustée.')
    if type(delta_cents) is not int or delta_cents==0:
        raise ValueError('L’ajustement doit être différent de zéro.')
    reason=str(reason or '').strip()
    if not reason:
        raise ValueError('Motif obligatoire pour tout ajustement de facture.')
    payload={'invoice_id':invoice_id,'delta_cents':delta_cents,'reason':reason}
    hashed=_digest(payload)
    prior=connection.execute('SELECT * FROM hub_invoice_adjustments WHERE request_key=?',(request_key,)).fetchone()
    if prior:
        if prior['actor_id']!=actor_id or prior['payload_hash']!=hashed:
            raise ValueError('Clé déjà utilisée pour un autre ajustement.')
        fresh=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
        return {'already_recorded':True,'adjustment_id':prior['id'],
                'old_total_cents':prior['old_total_cents'],'new_total_cents':prior['new_total_cents'],
                'invoice':_invoice_summary(connection,fresh)}
    before=_invoice_summary(connection,invoice)
    after_total=before['total_cents']+delta_cents
    if after_total<0:
        raise ValueError('L’ajustement ne peut pas rendre le montant de facture négatif.')
    if after_total<before['paid_cents']:
        raise ValueError('L’ajustement ne peut pas réduire la facture sous les reçus déjà rapprochés; aucun remboursement automatique n’est permis.')
    cursor=connection.execute('''INSERT INTO hub_invoice_adjustments(
        invoice_id,delta_cents,old_total_cents,new_total_cents,reason,actor_id,actor_name,
        request_key,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
        (invoice_id,delta_cents,before['total_cents'],after_total,reason,actor_id,actor_name,
         request_key,hashed,created_at))
    fresh=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
    return {'already_recorded':False,'adjustment_id':cursor.lastrowid,
            'old_total_cents':before['total_cents'],'new_total_cents':after_total,
            'invoice':_invoice_summary(connection,fresh)}


def _receipt_info(connection, row):
    item=dict(row)
    item['effective_received_cents']=_effective_received(connection,'hub_cod_admin_receipts',row)
    item['invoice_allocated_cents']=connection.execute('SELECT COALESCE(sum(amount_cents),0) FROM hub_invoice_settlement_links WHERE receipt_id=?',(row['id'],)).fetchone()[0]
    item['invoice_unlinked_cents']=max(0,item['effective_received_cents']-item['invoice_allocated_cents'])
    item['driver_statement_allocated_cents']=connection.execute('''SELECT COALESCE(sum(l.amount_cents),0)
        FROM hub_cod_settlement_links l JOIN driver_transactions t ON t.id=l.driver_transaction_id
        WHERE l.receipt_id=? AND t.voided_at IS NULL''',(row['id'],)).fetchone()[0]
    return item


def hub_manager_invoice_list(connection, hub_id):
    hub=connection.execute('SELECT id,name FROM ops_hubs WHERE id=? AND active=1',(hub_id,)).fetchone()
    if not hub:
        raise ValueError('Le Hub de ce compte est inactif ou introuvable.')
    rows=[]
    for row in connection.execute("SELECT * FROM hub_invoices WHERE hub_id=? AND status='issued' ORDER BY id DESC LIMIT 500",(hub_id,)).fetchall():
        rows.append(_invoice_summary(connection,row))
    return {'hub':dict(hub),'invoices':rows,'count':len(rows),'read_only':True}


def hub_admin_invoice_overview(connection):
    hubs=[dict(row) for row in connection.execute('''SELECT h.id,h.name,h.active,ci.name city
        FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id ORDER BY h.name COLLATE NOCASE''').fetchall()]
    invoices=[]
    for row in connection.execute('SELECT * FROM hub_invoices ORDER BY id DESC LIMIT 2000').fetchall():
        item=_invoice_summary(connection,row)
        hub=connection.execute('SELECT name FROM ops_hubs WHERE id=?',(row['hub_id'],)).fetchone()
        item['hub_name']=hub['name'] if hub else 'Hub archivé'
        invoices.append(item)
    total_due=sum(row['remaining_cents'] for row in invoices if row['status']=='issued')
    total_received=sum(row['paid_cents'] for row in invoices if row['status']=='issued')
    drafts=sum(row['status']=='draft' for row in invoices)
    unlinked_receipts=0;unlinked_receipt_count=0
    for receipt in connection.execute('SELECT * FROM hub_cod_admin_receipts').fetchall():
        effective=_effective_received(connection,'hub_cod_admin_receipts',receipt)
        allocated=connection.execute('SELECT COALESCE(sum(amount_cents),0) FROM hub_invoice_settlement_links WHERE receipt_id=?',(receipt['id'],)).fetchone()[0]
        remaining=max(0,int(effective)-int(allocated or 0))
        if remaining:
            unlinked_receipts+=remaining;unlinked_receipt_count+=1
    unassigned=connection.execute("SELECT count(*) count,COALESCE(sum(amount_cents),0) cents FROM ops_attempts WHERE outcome='Livré' AND amount_cents>0 AND cod_hub_id IS NULL").fetchone()
    return {'hubs':hubs,'invoices':invoices,'total_due_cents':total_due,
            'total_received_cents':total_received,'draft_count':drafts,
            'unlinked_receipt_count':unlinked_receipt_count,'unlinked_receipt_cents':unlinked_receipts,
            'unattributed_delivery_count':unassigned['count'],'unattributed_cod_cents':unassigned['cents']}


def get_hub_admin_invoice_detail(connection, invoice_id):
    row=connection.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
    if not row:
        raise ValueError('Facture Hub introuvable.')
    invoice=_invoice_summary(connection,row)
    hub=connection.execute('SELECT name FROM ops_hubs WHERE id=?',(row['hub_id'],)).fetchone()
    invoice['hub_name']=hub['name'] if hub else 'Hub archivé'
    lines=[dict(line) for line in connection.execute('''SELECT l.id,l.attempt_id,l.parcel_id,l.tracking,l.delivery_at,
            l.amount_cents,p.status current_status,ci.name city
        FROM hub_invoice_lines l JOIN parcels p ON p.id=l.parcel_id JOIN cities ci ON ci.id=p.city_id
        WHERE l.invoice_id=? ORDER BY l.delivery_at,l.id''',(invoice_id,)).fetchall()]
    receipts=[_receipt_info(connection,receipt) for receipt in connection.execute('''SELECT * FROM hub_cod_admin_receipts
        WHERE hub_id=? ORDER BY id DESC''',(row['hub_id'],)).fetchall()]
    settlements=[dict(link) for link in connection.execute('''SELECT l.*,r.created_at receipt_created_at,r.reason receipt_reason
        FROM hub_invoice_settlement_links l JOIN hub_cod_admin_receipts r ON r.id=l.receipt_id
        WHERE l.invoice_id=? ORDER BY l.id DESC''',(invoice_id,)).fetchall()]
    adjustments=[dict(adjustment) for adjustment in connection.execute('SELECT * FROM hub_invoice_adjustments WHERE invoice_id=? ORDER BY id DESC',(invoice_id,)).fetchall()]
    pending_handoffs=connection.execute('''SELECT count(DISTINCT h.id) FROM hub_invoice_lines il
        JOIN hub_cod_handoff_lines hl ON hl.attempt_id=il.attempt_id
        JOIN hub_cod_handoffs h ON h.id=hl.handoff_id
        WHERE il.invoice_id=? AND NOT EXISTS(
            SELECT 1 FROM hub_cod_admin_receipt_lines rl WHERE rl.handoff_id=h.id
        )''',(invoice_id,)).fetchone()[0]
    return {'invoice':invoice,'lines':lines,'receipts':receipts,'settlements':settlements,
            'adjustments':adjustments,'pending_handoff_count':pending_handoffs}


def register_hub_invoices(app, services):
    from flask import jsonify, request
    conn, auth, user, now, text, Error = (services[k] for k in ('conn','auth','user','now','text','APIError'))
    append_audit_log=services['append_audit_log']
    with conn() as c:
        ensure_hub_invoice_schema(c)

    def audit(c,actor,action,entity_id,old_value,new_value,metadata):
        append_audit_log(c,actor_id=actor['id'],actor_name=actor['name'],action=action,
            entity_type='hub_invoice',entity_id=entity_id,old_value=old_value,new_value=new_value,
            metadata=metadata,created_at=now())

    def key(data):
        value=data.get('request_key')
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}',value):
            raise Error('Clé de saisie invalide.')
        return value

    def manager_hub(c,actor):
        hub_id=actor.get('agent_hub_id')
        if type(hub_id) is not int or hub_id<=0:
            raise Error('Aucun Hub actif n’est attribué à ce compte.',403)
        hub=c.execute('SELECT id,name FROM ops_hubs WHERE id=? AND active=1',(hub_id,)).fetchone()
        if not hub:
            raise Error('Le Hub attribué à ce compte est inactif ou introuvable.',403)
        return hub

    @app.get(_MANAGER_PREFIX)
    @auth('hub_manager')
    def hub_manager_invoices():
        actor=user()
        with conn() as c:
            c.execute('BEGIN')
            hub=manager_hub(c,actor)
            try:result=hub_manager_invoice_list(c,hub['id'])
            except ValueError as exc:raise Error(str(exc),403)
            return jsonify(result)

    @app.get(_PREFIX)
    @auth('admin')
    def hub_admin_invoices():
        with conn() as c:
            c.execute('BEGIN')
            return jsonify(hub_admin_invoice_overview(c))

    @app.post(_PREFIX+'/drafts')
    @auth('admin')
    def hub_admin_invoice_draft_create():
        data=request.get_json(silent=True);actor=user()
        if not isinstance(data,dict) or set(data)!={'hub_id','period_from','period_to','request_key'}:
            raise Error('Données de brouillon invalides.')
        if type(data.get('hub_id')) is not int or data['hub_id']<=0:raise Error('Hub invalide.')
        request_key=key(data)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                result=create_hub_invoice_draft(c,hub_id=data['hub_id'],period_from=data['period_from'],
                    period_to=data['period_to'],actor_id=actor['id'],request_key=request_key,created_at=now())
            except ValueError as exc:raise Error(str(exc),409)
            if not result.get('already_created'):
                audit(c,actor,'hub_invoice_draft_created',result['id'],None,
                    {'status':'draft','total_cents':result['total_cents'],'delivery_count':result['delivery_count']},
                    {'hub_id':data['hub_id'],'period_from':data['period_from'],'period_to':data['period_to']})
            return jsonify(ok=True,**result)

    @app.get(_PREFIX+'/<int:invoice_id>')
    @auth('admin')
    def hub_admin_invoice_detail(invoice_id):
        with conn() as c:
            c.execute('BEGIN')
            try:result=get_hub_admin_invoice_detail(c,invoice_id)
            except ValueError as exc:raise Error(str(exc),404)
            return jsonify(result)

    @app.post(_PREFIX+'/<int:invoice_id>/issue')
    @auth('admin')
    def hub_admin_invoice_issue(invoice_id):
        data=request.get_json(silent=True);actor=user()
        if not isinstance(data,dict) or data.get('confirmed') is not True:raise Error('Confirmez explicitement l’émission après revue.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
            if not old:raise Error('Facture Hub introuvable.',404)
            try:result=issue_hub_invoice(c,invoice_id=invoice_id,actor_id=actor['id'],issued_at=now())
            except ValueError as exc:raise Error(str(exc),409)
            if not result.get('already_issued'):
                audit(c,actor,'hub_invoice_issued',invoice_id,{'status':'draft'},
                      {'status':'issued','total_cents':result['total_cents'],'issued_at':result['issued_at']},
                      {'hub_id':result['hub_id']})
            return jsonify(ok=True,**result)

    @app.post(_PREFIX+'/<int:invoice_id>/cancel')
    @auth('admin')
    def hub_admin_invoice_cancel(invoice_id):
        data=request.get_json(silent=True);actor=user()
        if not isinstance(data,dict) or data.get('confirmed') is not True:raise Error('Confirmez explicitement l’annulation du brouillon.')
        reason=text(data,'reason',maxlen=600)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
            if not old:raise Error('Facture Hub introuvable.',404)
            try:result=cancel_hub_invoice_draft(c,invoice_id=invoice_id,actor_id=actor['id'],cancelled_at=now(),reason=reason)
            except ValueError as exc:raise Error(str(exc),409)
            audit(c,actor,'hub_invoice_draft_cancelled',invoice_id,{'status':'draft'},
                  {'status':'cancelled','reason':reason}, {'hub_id':old['hub_id']})
            return jsonify(ok=True,**result)

    @app.post(_PREFIX+'/<int:invoice_id>/adjustments')
    @auth('admin')
    def hub_admin_invoice_adjustment_create(invoice_id):
        data=request.get_json(silent=True);actor=user()
        if not isinstance(data,dict) or data.get('confirmed') is not True:
            raise Error('Confirmez explicitement l’ajustement après revue.')
        try:delta_cents=money_cents(data.get('delta_amount'),signed=True)
        except ValueError as exc:raise Error(str(exc))
        if delta_cents==0:raise Error('L’ajustement doit être différent de zéro.')
        reason=text(data,'reason',maxlen=600);request_key=key(data)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
            if not old:raise Error('Facture Hub introuvable.',404)
            before=_invoice_summary(c,old)
            try:result=adjust_hub_invoice(c,invoice_id=invoice_id,delta_cents=delta_cents,
                reason=reason,actor_id=actor['id'],actor_name=actor['name'],
                request_key=request_key,created_at=now())
            except ValueError as exc:raise Error(str(exc),409)
            if not result.get('already_recorded'):
                audit(c,actor,'hub_invoice_adjusted',invoice_id,
                    {'total_cents':result['old_total_cents']},
                    {'total_cents':result['new_total_cents'],'delta_cents':delta_cents,'reason':reason},
                    {'hub_id':old['hub_id']})
            return jsonify(ok=True,**result)

    @app.post(_PREFIX+'/<int:invoice_id>/settlements')
    @auth('admin')
    def hub_admin_invoice_settlement_create(invoice_id):
        data=request.get_json(silent=True);actor=user()
        if not isinstance(data,dict) or data.get('confirmed') is not True:raise Error('Confirmez le rapprochement manuel du reçu à cette facture.')
        receipt_id=data.get('receipt_id')
        if type(receipt_id) is not int or receipt_id<=0:raise Error('Reçu Admin invalide.')
        try:amount_cents=money_cents(data.get('amount'))
        except ValueError as exc:raise Error(str(exc))
        reason=text(data,'reason',False,maxlen=600);request_key=key(data)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            invoice=c.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
            receipt=c.execute('SELECT * FROM hub_cod_admin_receipts WHERE id=?',(receipt_id,)).fetchone()
            if not invoice or not receipt:raise Error('Facture ou reçu Admin introuvable.',404)
            before=_invoice_summary(c,invoice)
            try:result=link_existing_admin_receipt(c,invoice_id=invoice_id,receipt_id=receipt_id,
                amount_cents=amount_cents,reason=reason,actor_id=actor['id'],actor_name=actor['name'],
                request_key=request_key,created_at=now())
            except ValueError as exc:raise Error(str(exc),409)
            if not result.get('already_recorded'):
                audit(c,actor,'hub_invoice_receipt_linked',invoice_id,
                    {'remaining_cents':before['remaining_cents']},
                    {'remaining_cents':result['invoice']['remaining_cents'],'receipt_id':receipt_id,
                     'amount_cents':amount_cents,'receipt_remaining_cents':result['receipt_remaining_cents']},
                    {'hub_id':invoice['hub_id'],'reason':reason})
            return jsonify(ok=True,**result)

    @app.post(_PREFIX+'/<int:invoice_id>/receipts')
    @auth('admin')
    def hub_admin_invoice_receipt_create(invoice_id):
        data=request.get_json(silent=True);actor=user()
        if not isinstance(data,dict) or data.get('confirmed') is not True:
            raise Error('Confirmez le montant physiquement reçu du Hub.')
        try:
            received=money_cents(data.get('received_amount'))
            applied=money_cents(data.get('applied_amount'))
        except ValueError as exc:raise Error(str(exc))
        reason=text(data,'reason',False,maxlen=600);request_key=key(data)
        if data.get('not_recorded_before') is not True:
            raise Error('Confirmez que ce cash n’a pas déjà été enregistré dans Caisse COD.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM hub_invoices WHERE id=?',(invoice_id,)).fetchone()
            if not old:raise Error('Facture Hub introuvable.',404)
            before=_invoice_summary(c,old)
            try:result=record_hub_invoice_receipt(c,invoice_id=invoice_id,received_cents=received,
                applied_cents=applied,reason=reason,actor_id=actor['id'],actor_name=actor['name'],
                request_key=request_key,created_at=now(),not_recorded_before=True)
            except ValueError as exc:raise Error(str(exc),409)
            if not result.get('already_recorded'):
                audit(c,actor,'hub_invoice_receipt_recorded',invoice_id,
                    {'remaining_cents':before['remaining_cents']},
                    {'remaining_cents':result['invoice']['remaining_cents'],'receipt_id':result['receipt_id'],
                     'received_cents':received,'applied_cents':applied,'unlinked_cents':result['unlinked_cents']},
                    {'hub_id':old['hub_id'],'reason':reason,'source':'hub_invoice'})
            return jsonify(ok=True,**result)
