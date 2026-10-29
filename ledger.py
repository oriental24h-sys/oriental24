"""Registre monétaire exact : centimes entiers à côté des colonnes historiques REAL.

Pourquoi : les montants COD sont aujourd'hui stockés en `REAL` (float). Additionner des
floats accumule des écarts de centimes (« 0.1 + 0.2 ») et rend la réconciliation
mensuelle approximative. `ops_attempts.amount_cents` prouvait déjà que le centime entier
est la bonne unité.

Approche **non destructive** (aucune colonne existante n'est modifiée) :

* colonnes `*_cents INTEGER` ajoutées à `parcels` et `invoices` ;
* **triggers** qui les recopient à chaque INSERT/UPDATE des colonnes REAL : toutes les
  voies d'écriture existantes (formulaires, imports, API partenaire, scripts) sont donc
  couvertes sans en modifier aucune ;
* backfill idempotent pour l'historique ;
* les totaux de facture sont désormais calculés **en centimes** puis divisés par 100,
  donc exacts au centime ;
* `invoice_lines` : le détail par colis de chaque facture (audit et litiges).

`refresh_cents()` peut être appelé à tout moment (démarrage, maintenance) : il ne touche
que les lignes incohérentes.
"""

import logging

log = logging.getLogger('oriental24')

PARCEL_COLUMNS = (('amount_cents', 'amount'), ('fee_cents', 'fee'), ('return_fee_cents', 'return_fee'))
INVOICE_COLUMNS = (('cod_cents', 'cod'), ('fees_cents', 'fees'), ('total_cents', 'total'))


def cents(value):
    """Convertit un montant MAD en centimes entiers (jamais de float en sortie)."""
    try:
        return int(round(float(value or 0) * 100))
    except (TypeError, ValueError):
        return 0


def units(value_cents):
    """Centimes entiers → montant MAD arrondi au centime."""
    return round(int(value_cents or 0) / 100.0, 2)


def _columns(c, table):
    return {r['name'] for r in c.execute('PRAGMA table_info(%s)' % table)}


def migrate(c):
    """Colonnes + triggers + backfill + table de détail (idempotent)."""
    for table, mapping in (('parcels', PARCEL_COLUMNS), ('invoices', INVOICE_COLUMNS)):
        existing = _columns(c, table)
        for column, _source in mapping:
            if column not in existing:
                c.execute('ALTER TABLE %s ADD COLUMN %s INTEGER' % (table, column))
    # Synchronisation permanente REAL → centimes, quel que soit le code qui écrit.
    for table, mapping in (('parcels', PARCEL_COLUMNS), ('invoices', INVOICE_COLUMNS)):
        assignments = ', '.join('%s=CAST(ROUND(COALESCE(NEW.%s,0)*100) AS INTEGER)' % (col, src)
                                for col, src in mapping)
        columns = ', '.join(src for _col, src in mapping)
        for timing, prefix, row in (('INSERT', 'NEW', 'NEW'), ('UPDATE', 'NEW', 'NEW')):
            trigger = '%s_cents_sync_%s' % (table, timing.lower())
            c.execute('DROP TRIGGER IF EXISTS %s' % trigger)
            update_of = ' OF %s' % columns if timing == 'UPDATE' else ''
            c.execute('CREATE TRIGGER %s AFTER %s%s ON %s FOR EACH ROW BEGIN '
                      'UPDATE %s SET %s WHERE id=%s.id; END'
                      % (trigger, timing, update_of, table, table, assignments, row))
    refresh_cents(c)
    c.execute('''CREATE TABLE IF NOT EXISTS invoice_lines(
        id INTEGER PRIMARY KEY,
        invoice_id INTEGER NOT NULL REFERENCES invoices(id),
        parcel_id INTEGER NOT NULL REFERENCES parcels(id),
        tracking TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT '',
        cod_cents INTEGER NOT NULL DEFAULT 0,
        fee_cents INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(invoice_id, parcel_id))''')


def refresh_cents(c):
    """Backfill/contrôle : aligne les colonnes centimes sur les colonnes REAL."""
    pairs = (('parcels', PARCEL_COLUMNS), ('invoices', INVOICE_COLUMNS))
    for table, mapping in pairs:
        condition = ' OR '.join('%s IS NULL OR %s<>CAST(ROUND(COALESCE(%s,0)*100) AS INTEGER)'
                                % (col, col, src) for col, src in mapping)
        assignments = ', '.join('%s=CAST(ROUND(COALESCE(%s,0)*100) AS INTEGER)' % (col, src)
                                for col, src in mapping)
        c.execute('UPDATE %s SET %s WHERE %s' % (table, assignments, condition))


def invoice_totals(parcels):
    """Totaux d'une facture calculés en centimes entiers (exacts au centime).

    `parcels` : lignes avec `status`, et soit `amount_cents/fee_cents/return_fee_cents`,
    soit `amount/fee/return_fee` (base ancienne).
    """
    cod = fees = 0
    lines = []
    for p in parcels:
        row = dict(p)
        delivered = row.get('status') == 'Livré'
        amount = row.get('amount_cents')
        fee = row.get('fee_cents')
        ret = row.get('return_fee_cents')
        amount = cents(row.get('amount')) if amount is None else int(amount)
        fee = cents(row.get('fee')) if fee is None else int(fee)
        ret = cents(row.get('return_fee')) if ret is None else int(ret)
        if delivered:
            cod += amount
            fees += fee
            line_cod, line_fee = amount, fee
        else:
            fees += ret
            line_cod, line_fee = 0, ret
        lines.append({'parcel_id': row.get('id'), 'tracking': row.get('tracking') or '',
                      'status': row.get('status') or '', 'cod_cents': line_cod, 'fee_cents': line_fee})
    return {'cod_cents': cod, 'fees_cents': fees, 'total_cents': cod - fees,
            'cod': units(cod), 'fees': units(fees), 'total': units(cod - fees), 'lines': lines}


def record_lines(c, invoice_id, totals, created_at):
    """Enregistre le détail par colis d'une facture (idempotent)."""
    for line in totals.get('lines', []):
        if not line.get('parcel_id'):
            continue
        try:
            c.execute('INSERT OR IGNORE INTO invoice_lines'
                      '(invoice_id,parcel_id,tracking,status,cod_cents,fee_cents,created_at) '
                      'VALUES(?,?,?,?,?,?,?)',
                      (invoice_id, line['parcel_id'], line['tracking'], line['status'],
                       int(line['cod_cents']), int(line['fee_cents']), created_at))
        except Exception:
            log.warning('Ligne de facture %s non enregistrée', line.get('parcel_id'), exc_info=True)


def lines_for(c, invoice_id):
    try:
        return [dict(r) for r in c.execute(
            'SELECT parcel_id,tracking,status,cod_cents,fee_cents FROM invoice_lines '
            'WHERE invoice_id=? ORDER BY id', (invoice_id,))]
    except Exception:
        return []
