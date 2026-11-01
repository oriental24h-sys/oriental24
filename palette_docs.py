"""Documents d'une palette — toutes les palettes qui ARRIVENT (société ou inter-Hub).

Quatre documents, une seule adresse pour les deux types de palette :
  · `ticket.pdf`  : ticket de palette 100 × 100 mm (+ QR) à coller / agrafer sur la palette ;
  · `bon.pdf`     : bon de réception A4 (liste des CMD, compteurs, signatures) ;
  · `colis.csv`   : toutes les CMD de la palette (Excel / CSV, séparateur `;`) ;
  · `attachments` : pièces jointes (photo du bon, réserve transporteur…), en base.

`kind` accepté : `partner` (palette société → Hub) et `transfer` (palette inter-Hub).
Aucun document n'est stocké sur disque : les PDF sont générés à la demande, les pièces
jointes sont des BLOB en base (même table que la console Palettes).
"""
import base64
import io
import re
import sqlite3

from flask import Response, jsonify, request
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import billing_pdf  # enregistre les polices O24/O24Bold (sans accents, arabe réordonné)
from hub_access import hub_received_lines

NAVY = colors.HexColor('#0c274c')
ORANGE = colors.HexColor('#f58024')
GREY = colors.HexColor('#6b7787')
LINE = colors.HexColor('#c9d2dd')
MAX_ATTACHMENT = 1_500_000
ALLOWED_ATTACHMENT = re.compile(r'data:(image/(?:jpeg|png|webp)|application/pdf);base64,([A-Za-z0-9+/=\s]+)')

DB_KINDS = {'partner': 'partner_palette', 'return': 'return_palette',
            'transfer': 'transfer', 'pickup': 'pickup'}
TITLES = {'partner': 'Palette société', 'transfer': 'Palette inter-Hub',
          'pickup': 'Ramassage', 'return': 'Retour vendeur'}
# Mêmes couleurs que l'écran (bon-print.js) : vert = RAMASSAGE, bleu = RÉCEPTION, rouge = RETOUR.
NATURE_COLORS = {'RAMASSAGE': colors.HexColor('#1d7d3f'), 'RETOUR': colors.HexColor('#b3261e'),
                 'RÉCEPTION': colors.HexColor('#1b4ed8')}


def is_hub_send(doc):
    """Palette partie d'un Hub vers le Hub Central (sens « envoi »)."""
    doc = doc or {}
    central = doc.get('central_hub_id')
    source, destination = doc.get('source_hub_id'), doc.get('destination_hub_id')
    if not central or not destination:
        return False
    try:
        central, destination = int(central), int(destination)
        source = int(source) if source not in (None, '') else None
    except (TypeError, ValueError):
        return False
    return destination == central and source != central


def nature_of(kind, doc):
    """Nature du mouvement, telle qu'elle doit sauter aux yeux sur le ticket :
    RAMASSAGE (colis ramassés / envoi vers le Hub Central), RETOUR (retour Central,
    origine ou vendeur) ou RÉCEPTION (ce qui arrive dans un Hub).

    Un transfert n'a pas UNE nature : c'est le SENS du document qui la donne.
    Hub → Central = RAMASSAGE (vert). Central → Hub = RÉCEPTION (bleu).
    """
    purpose = (doc or {}).get('palette_purpose') or 'standard'
    if kind == 'pickup':
        return 'RAMASSAGE', 'Colis ramassés à réceptionner au Hub'
    if kind == 'return':
        return 'RETOUR', 'Retour à remettre au vendeur'
    if kind == 'transfer' and purpose in ('return_to_central', 'return_to_origin'):
        return 'RETOUR', ('Retour vers le Hub Central' if purpose == 'return_to_central'
                          else 'Retour vers le Hub d’origine')
    if kind == 'partner':
        return 'RÉCEPTION', 'Arrivée société à réceptionner au Hub'
    if kind == 'transfer' and is_hub_send(doc):
        return 'RAMASSAGE', 'CMD ramassées à mon Hub, expédiées vers le Hub Central pour tri'
    return 'RÉCEPTION', 'Transfert inter-Hub à réceptionner'


def register_palette_docs(app, s):
    conn, auth, user, now, Error = (s[k] for k in ('conn', 'auth', 'user', 'now', 'APIError'))
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS palette_attachments(
            id INTEGER PRIMARY KEY,kind TEXT NOT NULL,document_id INTEGER NOT NULL REFERENCES ops_documents(id),
            mime TEXT NOT NULL,content BLOB NOT NULL,note TEXT NOT NULL DEFAULT '',
            actor_id INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL)''')

    def load(c, kind, did, u):
        if kind not in TITLES:
            raise Error('Type de palette inconnu.', 404)
        if kind == 'partner':
            row = c.execute("""SELECT d.*,COALESCE(m.partner_reference,'') societe_reference,
                               COALESCE(NULLIF(m.transport,''),d.transport) palette_transport FROM ops_documents d
                               JOIN partner_palette_meta m ON m.document_id=d.id
                               WHERE d.id=? AND d.kind='partner_palette'""", (did,)).fetchone()
        elif kind == 'return':
            row = c.execute("SELECT d.* FROM ops_documents d WHERE d.id=? AND d.kind IN ('return','return_palette')", (did,)).fetchone()
        else:
            row = c.execute("SELECT d.* FROM ops_documents d WHERE d.id=? AND d.kind=?", (did, kind)).fetchone()
        if not row:
            raise Error('Document introuvable.', 404)
        doc = dict(row)
        hub_id = u.get('agent_hub_id')
        if u['role'] == 'client':
            if kind != 'partner' or doc['client_id'] != u['id']:
                raise Error('Document introuvable.', 404)
        elif u['role'] == 'agent':
            allowed = doc['destination_hub_id'] if kind == 'partner' else None
            if kind == 'partner' and allowed != hub_id:
                raise Error('Palette introuvable.', 404)
            if kind in ('transfer', 'pickup', 'return') and hub_id not in (doc['source_hub_id'], doc['destination_hub_id']):
                raise Error('Document introuvable.', 404)
        elif u['role'] != 'admin':
            raise Error('Accès réservé.', 403)
        doc['partner_reference'] = doc.pop('societe_reference', '') or ''
        doc['transport'] = doc.pop('palette_transport', '') or doc.get('transport') or ''
        # Le sens du trajet décide de la nature du ticket : il faut savoir où est le Central.
        try:
            row = c.execute("SELECT value FROM settings WHERE key='central_hub_id'").fetchone()
            doc['central_hub_id'] = int(row['value']) if row and row['value'] else None
        except (sqlite3.Error, TypeError, ValueError):
            doc['central_hub_id'] = None
        return doc

    def lines(c, did, u, kind):
        rows = [dict(r) for r in c.execute("""SELECT l.id,l.tracking,l.recipient,l.city,l.received_at,l.missing_at,
                    l.departure_scanned_at,l.initial_status,p.phone,p.amount,p.address,p.product,p.current_hub_id
                    FROM ops_document_lines l JOIN parcels p ON p.id=l.parcel_id
                    WHERE l.document_id=? ORDER BY l.id""", (did,))]
        if u['role'] == 'agent':
            # Le Hub ne voit le détail que des colis réellement scannés chez lui.
            rows = hub_received_lines(rows, u.get('agent_hub_id'))
        return rows

    def stats(c, did):
        row = c.execute('''SELECT count(*)-COALESCE(sum(departure_reconciled_at IS NOT NULL),0) total,
                    COALESCE(sum(received_at IS NOT NULL AND departure_reconciled_at IS NULL),0) received,
                    COALESCE(sum(missing_at IS NOT NULL),0) missing
                    FROM ops_document_lines WHERE document_id=?''', (did,)).fetchone()
        return int(row['total'] or 0), int(row['received'] or 0), int(row['missing'] or 0)

    def csv_safe(value):
        text = str('' if value is None else (('%g' % round(float(value), 2)) if isinstance(value, (int, float)) else value))
        text = text.replace('\r', ' ').replace('\n', ' ')
        return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text

    def stamp(value):
        return str(value or '').replace('T', ' ')[:16]

    def doc_head(story, doc, kind, subtitle, width):
        normal = ParagraphStyle('n', fontName='O24', fontSize=8.5, leading=12, textColor=NAVY)
        small = ParagraphStyle('s', parent=normal, fontSize=6.8, leading=9.5, textColor=GREY)

        def p(value, style=normal):
            return Paragraph(str(value or '').replace('\n', '<br/>'), style)

        logo = Image(str(billing_pdf.ROOT / 'static' / 'wordmark.png'), width=42 * mm, height=11.5 * mm, kind='proportional')
        right = [p(TITLES[kind], small), p(subtitle, normal), p('Réf. ' + str(doc['reference']), normal)]
        head = Table([[logo, right]], colWidths=[width * .42, width * .58])
        head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                  ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                                  ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        story.extend([head, Spacer(1, 7 * mm)])
        return normal, small, p

    def info_table(story, pairs, width, normal):
        def p(value):
            txt = '—' if value is None or value == '' else str(value)
            return Paragraph(txt, ParagraphStyle('v', parent=normal, fontSize=8))

        def label(value):
            return Paragraph('<b>' + value + '</b>', ParagraphStyle('l', parent=normal, fontSize=7, textColor=GREY))

        cells = [[label(a), p(b), label(c), p(d)] for (a, b), (c, d) in zip(pairs[0::2], pairs[1::2] + [(('', ''))] * (len(pairs) % 2))]
        t = Table(cells, colWidths=[width * .16, width * .34, width * .16, width * .34])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('LINEBELOW', (0, 0), (-1, -1), .3, LINE),
                               ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        story.extend([t, Spacer(1, 5 * mm)])

    def lines_table(story, rows, width, normal, with_money=True):
        head = ['#', 'Tracking', 'Destinataire', 'Ville', 'Téléphone']
        if with_money:
            head.append('COD')
        head.append('Réception')
        weights = [6, 26, 24, 14, 14] + ([10] if with_money else []) + [12]
        body = [[Paragraph('<b>' + h + '</b>', ParagraphStyle('h', parent=normal, fontSize=6.6, textColor=GREY)) for h in head]]
        for index, line in enumerate(rows, 1):
            values = [str(index), line['tracking'] or '', line['recipient'] or '', line['city'] or '', line.get('phone') or '']
            if with_money:
                amount = line.get('amount')
                values.append('%.2f' % float(amount) if amount not in (None, '') else '')
            values.append(stamp(line['received_at']) if line['received_at'] else ('NON REÇU' if line.get('missing_at') else '—'))
            body.append([Paragraph(str(v)[:60], ParagraphStyle('c', parent=normal, fontSize=6.8)) for v in values])
        t = Table(body, colWidths=[width * w / sum(weights) for w in weights], repeatRows=1)
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('LINEBELOW', (0, 0), (-1, 0), .8, NAVY),
                               ('LINEBELOW', (0, 1), (-1, -1), .25, LINE),
                               ('TOPPADDING', (0, 0), (-1, -1), 3.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
                               ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3)]))
        story.append(t)

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont('O24', 6.5)
        canvas.setFillColor(GREY)
        canvas.drawString(14 * mm, 10 * mm, 'ORIENTAL24 · document interne de suivi de palette · aucun paiement exécuté')
        canvas.drawRightString(A4[0] - 14 * mm, 10 * mm, 'Page %d' % canvas.getPageNumber())
        canvas.restoreState()

    def build(doc, kind, rows, title, totals, nature):
        width = A4[0] - 28 * mm
        out = io.BytesIO()
        story = []
        normal, small, p = doc_head(story, doc, kind, title, width)
        total, received, missing = totals
        pairs = [('Source', doc.get('source_name') or doc.get('client_name') or '—'),
                 ('Destination', doc.get('destination_name') or '—'),
                 ('Transport', doc.get('transport') or '—'),
                 ('Code de suivi', doc.get('tracking_code') or '—')]
        if kind == 'partner':
            pairs.append(('Réf. société', doc.get('partner_reference') or '—'))
        else:
            pairs.append(('Lots', doc.get('lots') if doc.get('lots') is not None else '—'))
        pairs += [('État', doc.get('status') or '—'),
                  ('Créée le', stamp(doc.get('created_at'))),
                  ('Expédiée le', stamp(doc.get('dispatched_at'))),
                  ('Colis annoncés', total),
                  ('Colis réceptionnés', received),
                  ('Colis restants', max(0, total - received - missing)),
                  ('Non réceptionnés', missing)]
        info_table(story, pairs, width, normal)
        chip = Table([[Paragraph('<b>' + nature + '</b>', ParagraphStyle('chip', fontName='O24Bold', fontSize=10,
                           textColor=colors.white, alignment=TA_CENTER))]],
                     colWidths=[52 * mm], rowHeights=[7.5 * mm])
        chip.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), NATURE_COLORS.get(nature, NAVY)),
                                  ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        chip.hAlign = 'LEFT'
        story.extend([chip, Spacer(1, 3 * mm)])
        if doc.get('note'):
            story.extend([Paragraph('<b>Note :</b> ' + str(doc['note'])[:400], ParagraphStyle('note', parent=normal, fontSize=7.5, textColor=GREY)), Spacer(1, 4 * mm)])
        story.append(Paragraph('<b>Détail des CMD de la palette</b>' if kind in ('partner', 'return') else '<b>Détail des colis transférés</b>',
                               ParagraphStyle('sec', parent=normal, fontSize=9, spaceAfter=3 * mm)))
        if rows:
            lines_table(story, rows, width, normal)
        else:
            story.append(Paragraph('Aucun détail de colis visible pour ce compte : les colis apparaissent après leur réception physique au Hub.',
                                   ParagraphStyle('empty', parent=normal, fontSize=7.5, textColor=GREY)))
        story.extend([Spacer(1, 10 * mm)])
        sign = ['Hub de réception' if kind == 'partner' else 'Hub de départ', 'Transporteur', 'Réception par le Hub']
        cells = [[Paragraph('<b>' + label + '</b>', ParagraphStyle('sg', parent=normal, fontSize=7, textColor=GREY)) for label in sign],
                 [Paragraph('<br/><br/><br/>', ParagraphStyle('sp', parent=normal, fontSize=7)) for _ in sign]]
        t = Table(cells, colWidths=[width / 3] * 3)
        t.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), .4, LINE), ('INNERGRID', (0, 0), (-1, -1), .4, LINE),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 5)]))
        story.append(t)
        pdf = SimpleDocTemplate(out, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                                topMargin=13 * mm, bottomMargin=18 * mm,
                                title='ORIENTAL24 ' + str(doc['reference']), author='ORIENTAL24')
        pdf.build(story, onFirstPage=footer, onLaterPages=footer)
        return out.getvalue()

    def _fit(canvas, text, max_width, size, min_size=5.0, font='O24Bold'):
        """Réduit la taille puis tronque : un ticket 100 × 100 ne déborde jamais."""
        text = str('' if text is None else text)
        while size > min_size and canvas.stringWidth(text, font, size) > max_width:
            size -= .2
        if canvas.stringWidth(text, font, size) > max_width:
            while text and canvas.stringWidth(text + '…', font, size) > max_width:
                text = text[:-1]
            text += '…'
        canvas.setFont(font, size)
        return text

    def ticket_pdf(doc, kind, total, received):
        """Ticket de palette **100 × 100 mm** (carré) : même module que l'étiquette de
        livraison 100 × 100. La NATURE du mouvement est écrite en grand et colorée
        (vert ramassage · bleu réception · rouge retour), QR en bas à droite."""
        nature, subtitle = nature_of(kind, doc)
        side = 100 * mm
        width = height = side
        pad = 6 * mm
        out = io.BytesIO()
        canvas = Canvas(out, pagesize=(width, height))

        # --- bandeau de nature ---
        band = 22 * mm
        canvas.setFillColor(NATURE_COLORS.get(nature, NAVY))
        canvas.rect(0, height - band, width, band, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont('O24Bold', 20)
        canvas.drawString(pad, height - 11 * mm, nature)
        canvas.setFont('O24', 6.2)
        canvas.drawString(pad, height - 16.6 * mm, _fit(canvas, subtitle, width - 2 * pad - 34 * mm, 6.2, 4.6, 'O24'))
        canvas.setFillColor(colors.white)
        canvas.setFont('O24', 5.6)
        canvas.drawRightString(width - pad, height - 6 * mm, TITLES.get(kind, 'Palette'))
        canvas.setFont('O24Bold', 12)
        canvas.drawRightString(width - pad, height - 13.5 * mm, str(doc.get('reference') or ''))

        # --- champs : deux colonnes, quatre lignes, jamais de débordement ---
        remaining = max(0, total - received)
        left_rows = [('SOURCE', doc.get('source_name') or doc.get('client_name') or '—'),
                     ('DESTINATION', doc.get('destination_name') or '—'),
                     ('TRANSPORT', doc.get('transport') or '—'),
                     ('CODE DE SUIVI', doc.get('tracking_code') or '—')]
        right_rows = [('COLIS', '%s annoncés · %s reçus' % (total, received)),
                      ('ÉTAT', doc.get('status') or '—'),
                      ('DATE', stamp(doc.get('dispatched_at') or doc.get('created_at'))),
                      ('LOTS / RÉF. SOCIÉTÉ', (doc.get('partner_reference') or '—') if kind == 'partner'
                       else str(doc.get('lots') if doc.get('lots') is not None else '—'))]
        left_x, left_w = pad, 44 * mm
        right_x, right_w = 56 * mm, width - pad - 56 * mm
        first_y = height - band - 7 * mm
        row_h = 11 * mm
        for index, ((label, value), (label2, value2)) in enumerate(zip(left_rows, right_rows)):
            y = first_y - index * row_h
            for x, w, lab, val in ((left_x, left_w, label, value), (right_x, right_w, label2, value2)):
                canvas.setFillColor(GREY)
                canvas.setFont('O24', 5.4)
                canvas.drawString(x, y, _fit(canvas, lab, w, 5.4, 4.4, 'O24'))
                canvas.setFillColor(NAVY)
                canvas.setFont('O24Bold', 8.4)
                canvas.drawString(x, y - 4.3 * mm, _fit(canvas, val, w, 8.4))

        # --- QR en bas à droite ---
        qr_side = 22 * mm
        qr_x = width - pad - qr_side
        qr_y = 9 * mm
        try:
            import qrcode
            buf = io.BytesIO()
            qrcode.make(str(doc.get('reference') or '')).save(buf, format='PNG')
            buf.seek(0)
            canvas.drawImage(ImageReader(buf), qr_x, qr_y, qr_side, qr_side,
                             preserveAspectRatio=True, mask='auto')
        except Exception:  # le ticket reste imprimable même si le QR échoue
            pass

        # --- pied de page ---
        canvas.setFillColor(NAVY)
        canvas.setFont('O24Bold', 8)
        canvas.drawString(pad, 24 * mm, 'ORIENTAL24')
        canvas.setFillColor(GREY)
        canvas.setFont('O24', 5.8)
        canvas.drawString(pad, 20 * mm, _fit(canvas, 'ticket de palette · 100 × 100 mm', 62 * mm, 5.8, 4.4, 'O24'))
        canvas.drawString(pad, 16.4 * mm, _fit(canvas, nature + ' · ' + str(doc.get('reference') or ''), 62 * mm, 5.8, 4.4, 'O24'))
        canvas.drawString(pad, 12.8 * mm, _fit(canvas, ('%s restant(s)' % remaining) if remaining else 'Tous les colis reçus',
                                                62 * mm, 5.8, 4.4, 'O24'))
        canvas.showPage()
        canvas.save()
        return out.getvalue()

    def pdf_response(payload, name):
        return Response(payload, mimetype='application/pdf',
                        headers={'Content-Disposition': 'inline; filename="%s"' % name, 'Cache-Control': 'no-store'})

    def safe_name(doc, suffix):
        base = re.sub(r'[^A-Za-z0-9._-]+', '-', str(doc['reference'])) or 'palette'
        return 'ORIENTAL24-%s-%s' % (base, suffix)

    @app.get('/api/palette-docs/<kind>/<int:did>/bon.pdf')
    @auth('admin', 'agent', 'client')
    def palette_bon_pdf(kind, did):
        u = user()
        with conn() as c:
            doc = load(c, kind, did, u)
            rows = lines(c, did, u, kind)
            totals = stats(c, did)
        nature = nature_of(kind, doc)[0]
        title = {'RÉCEPTION': 'BON DE RÉCEPTION', 'RETOUR': 'BON DE RETOUR', 'RAMASSAGE': 'BON DE RAMASSAGE'}[nature]
        if doc.get('status') == 'Annulé':
            title += ' · ANNULÉ'
        return pdf_response(build(doc, kind, rows, title, totals, nature), safe_name(doc, 'bon.pdf'))

    @app.get('/api/palette-docs/<kind>/<int:did>/ticket.pdf')
    @auth('admin', 'agent', 'client')
    def palette_ticket_pdf(kind, did):
        u = user()
        with conn() as c:
            doc = load(c, kind, did, u)
            total, received, _missing = stats(c, did)
        return pdf_response(ticket_pdf(doc, kind, total, received), safe_name(doc, 'ticket.pdf'))

    @app.get('/api/palette-docs/<kind>/<int:did>/colis.csv')
    @auth('admin', 'agent', 'client')
    def palette_colis_csv(kind, did):
        u = user()
        with conn() as c:
            doc = load(c, kind, did, u)
            rows = lines(c, did, u, kind)
        head = ['ID de suivi', 'Destinataire', 'Adresse', 'Ville', 'Nature de produit', 'Numéro de téléphone', 'COD', 'Statut', 'Réception']
        out = ['sep=;', ';'.join(head)]
        for line in rows:
            out.append(';'.join([csv_safe(line['tracking']), csv_safe(line['recipient']), csv_safe(line.get('address')),
                                 csv_safe(line['city']), csv_safe(line.get('product')), csv_safe(line.get('phone')),
                                 csv_safe(line.get('amount')), csv_safe(str(line.get('initial_status') or '').upper()),
                                 csv_safe(stamp(line['received_at']))]) + ';')
        payload = '\ufeff' + '\n'.join(out) + '\n'
        return Response(payload, mimetype='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="%s"' % safe_name(doc, 'colis.csv'),
                                 'Cache-Control': 'private, no-store'})

    @app.get('/api/palette-docs/<kind>/<int:did>/attachments')
    @auth('admin', 'agent', 'client')
    def palette_attachments_list(kind, did):
        u = user()
        with conn() as c:
            doc = load(c, kind, did, u)
            db_kind = doc['kind']
            rows = [dict(r) for r in c.execute("""SELECT a.id,a.mime,a.note,a.created_at,u.name actor,a.content
                        FROM palette_attachments a JOIN users u ON u.id=a.actor_id
                        WHERE a.kind=? AND a.document_id=? ORDER BY a.id DESC""", (db_kind, did))]
        for row in rows:
            row['size'] = len(row.pop('content', b'') or b'')
            row['name'] = ('photo-%d' % row['id']) + ('.pdf' if row['mime'] == 'application/pdf' else '.jpg')
        return jsonify(rows=rows, count=len(rows), max_bytes=MAX_ATTACHMENT)

    @app.post('/api/palette-docs/<kind>/<int:did>/attachments')
    @auth('admin', 'agent', 'client')
    def palette_attachments_add(kind, did):
        u = user()
        d = request.get_json(silent=True) or {}
        match = ALLOWED_ATTACHMENT.fullmatch(str(d.get('data_url') or ''))
        if not match:
            raise Error('Pièce jointe invalide : photo JPEG/PNG/WebP ou PDF attendu.')
        try:
            raw = base64.b64decode(match.group(2), validate=True)
        except Exception:
            raise Error('Pièce jointe illisible.')
        if not raw or len(raw) > MAX_ATTACHMENT:
            raise Error('Pièce jointe trop lourde (1,5 Mo maximum après compression).')
        note = str(d.get('note') or '').strip()[:300]
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            doc = load(c, kind, did, u)
            db_kind = doc['kind']
            aid = c.execute("""INSERT INTO palette_attachments(kind,document_id,mime,content,note,actor_id,created_at)
                               VALUES(?,?,?,?,?,?,?)""", (db_kind, did, match.group(1), raw, note, u['id'], now())).lastrowid
            c.execute("INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)",
                      (did, u['id'], 'Pièce jointe ajoutée', '{"attachment_id": %d}' % aid, now()))
            return jsonify(ok=True, id=aid, size=len(raw))

    @app.get('/api/palette-docs/attachments/<int:aid>')
    @auth('admin', 'agent', 'client')
    def palette_attachment_get(aid):
        u = user()
        with conn() as c:
            row = c.execute('SELECT a.*,d.id did,d.kind dkind,d.client_id,d.destination_hub_id,d.source_hub_id FROM palette_attachments a JOIN ops_documents d ON d.id=a.document_id WHERE a.id=?', (aid,)).fetchone()
            if not row:
                raise Error('Pièce jointe introuvable.', 404)
            kind = 'partner' if row['dkind'] == 'partner_palette' else 'transfer'
            load(c, kind, row['did'], u)
            name = 'piece-jointe-%d' % aid + ('.pdf' if row['mime'] == 'application/pdf' else '.jpg')
            return Response(row['content'], mimetype=row['mime'],
                            headers={'Content-Disposition': 'inline; filename="%s"' % name,
                                     'Cache-Control': 'private, no-store'})

    @app.delete('/api/palette-docs/attachments/<int:aid>')
    @auth('admin', 'agent', 'client')
    def palette_attachment_delete(aid):
        u = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT a.*,d.id did,d.kind dkind FROM palette_attachments a JOIN ops_documents d ON d.id=a.document_id WHERE a.id=?', (aid,)).fetchone()
            if not row:
                raise Error('Pièce jointe introuvable.', 404)
            kind = 'partner' if row['dkind'] == 'partner_palette' else 'transfer'
            load(c, kind, row['did'], u)
            if u['role'] != 'admin' and row['actor_id'] != u['id']:
                raise Error('Seul l’auteur ou Admin peut retirer cette pièce jointe.', 403)
            c.execute('DELETE FROM palette_attachments WHERE id=?', (aid,))
            c.execute("INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)",
                      (row['did'], u['id'], 'Pièce jointe retirée', '{"attachment_id": %d}' % aid, now()))
            return jsonify(ok=True, deleted=aid)
