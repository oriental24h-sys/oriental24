"""Ticket PDF d'une palette : la NATURE dépend du SENS du trajet.

Exigence : le ticket d'une palette envoyée DEPUIS mon Hub VERS le Hub Central doit
être **RAMASSAGE**, en **vert** — jamais RÉCEPTION, jamais bleu.
Ce qui ARRIVE dans un Hub (Central → Hub, palette société) reste RÉCEPTION en bleu,
et un retour reste RETOUR en rouge.

Le test lit le vrai PDF produit par la route `/ticket.pdf` : la bande de couleur est
dessinée avec `r g b rg` en clair dans le flux (compressé zlib), donc on vérifie la
vraie couleur imprimée, pas seulement la constante Python.
"""
import re
import unittest
import zlib

import test_hub_palette_flow as fixtures
from palette_docs import register_palette_docs, nature_of, is_hub_send, NATURE_COLORS

GREEN = (29, 125, 63)     # #1d7d3f
BLUE = (27, 78, 216)      # #1b4ed8
RED = (179, 38, 30)       # #b3261e


def hex_of(color):
    return '#%02x%02x%02x' % tuple(round(v * 255) for v in (color.red, color.green, color.blue))


def _decompress(raw):
    body = raw.strip()
    if body.endswith(b'~>'):                       # /ASCII85Decode /FlateDecode
        try:
            import base64
            return zlib.decompress(base64.a85decode(body.replace(b'<~', b''), adobe=True))
        except Exception:
            return b''
    try:
        return zlib.decompress(body)
    except zlib.error:
        return b''


def pdf_colors(payload):
    """Couleurs réellement peintes dans le PDF, en RGB 0-255 (opérateurs `rg`)."""
    found = set()
    for raw in re.findall(rb'stream\r?\n(.*?)endstream', payload, re.S):
        text = _decompress(raw).decode('latin-1')
        for triple in re.findall(r'(?<![\d.])(\d*\.\d+|\d)\s+(\d*\.\d+|\d)\s+(\d*\.\d+|\d)\s+rg\b', text):
            found.add(tuple(round(float(v) * 255) for v in triple))
    return found


class PaletteTicketNatureTests(unittest.TestCase):
    def setUp(self):
        self.t = fixtures.HubPaletteFlowTests()
        self.t.setUp()
        register_palette_docs(self.t.app, self.t.services)
        with self.t.conn() as c:
            c.execute('ALTER TABLE ops_document_lines ADD COLUMN missing_at TEXT')
            c.execute('ALTER TABLE ops_document_lines ADD COLUMN missing_by INTEGER')
            c.execute("ALTER TABLE parcels ADD COLUMN address TEXT DEFAULT ''")
            c.execute("ALTER TABLE parcels ADD COLUMN product TEXT DEFAULT ''")
        self.client, self.conn = self.t.client, self.t.conn
        self.admin = {'X-Role': 'admin', 'X-Actor': '1', 'X-Name': 'Admin'}

    def tearDown(self):
        self.t.tearDown()

    # ---------- unités ----------
    def test_couleurs_identiques_a_l_ecran(self):
        self.assertEqual(hex_of(NATURE_COLORS['RAMASSAGE']), '#1d7d3f', 'RAMASSAGE doit être vert')
        self.assertEqual(hex_of(NATURE_COLORS['RÉCEPTION']), '#1b4ed8', 'RÉCEPTION doit être bleu')
        self.assertEqual(hex_of(NATURE_COLORS['RETOUR']), '#b3261e', 'RETOUR doit être rouge')

    def test_nature_par_sens(self):
        send = {'palette_purpose': 'standard', 'source_hub_id': 10, 'destination_hub_id': 90, 'central_hub_id': 90}
        self.assertEqual(nature_of('transfer', send)[0], 'RAMASSAGE')
        self.assertTrue(is_hub_send(send))
        arrive = {'palette_purpose': 'standard', 'source_hub_id': 90, 'destination_hub_id': 20, 'central_hub_id': 90}
        self.assertEqual(nature_of('transfer', arrive)[0], 'RÉCEPTION')
        self.assertFalse(is_hub_send(arrive))
        self.assertEqual(nature_of('transfer', {'palette_purpose': 'return_to_central', 'central_hub_id': 90})[0], 'RETOUR')
        self.assertEqual(nature_of('pickup', {})[0], 'RAMASSAGE')
        self.assertEqual(nature_of('partner', {})[0], 'RÉCEPTION')
        # sans Hub Central connu : on ne devine pas, on reste sur RÉCEPTION
        self.assertEqual(nature_of('transfer', {'palette_purpose': 'standard', 'source_hub_id': 10,
                                                'destination_hub_id': 90})[0], 'RÉCEPTION')

    # ---------- bout en bout : le vrai PDF ----------
    def ticket(self, did):
        response = self.client.get('/api/palette-docs/transfer/%d/ticket.pdf' % did, headers=self.admin)
        self.assertEqual(response.status_code, 200, 'HTTP %s · %r' % (response.status_code, response.data[:120]))
        self.assertEqual(response.mimetype, 'application/pdf')
        return pdf_colors(response.data)

    def palette(self, source, destination, parcel_ids, purpose='standard'):
        response = self.t.create_palette('agent', source, purpose, source, destination, list(parcel_ids), 910)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()['id']

    def test_ticket_envoi_hub_vers_central_est_vert_ramassage(self):
        did = self.palette(10, 90, [3])
        colors = self.ticket(did)
        self.assertIn(GREEN, colors, 'la bande du ticket n’est pas verte (#1d7d3f absent du PDF)')
        self.assertNotIn(BLUE, colors, 'le ticket d’un envoi de mon Hub est encore bleu (#1b4ed8 présent)')

    def test_ticket_arrivee_central_vers_hub_reste_bleu(self):
        with self.conn() as c:
            c.execute('UPDATE parcels SET current_hub_id=90 WHERE id=3')
            c.execute('UPDATE cities SET hub_id=20 WHERE id=2')
        did = self.palette(90, 20, [3])
        colors = self.ticket(did)
        self.assertIn(BLUE, colors, 'une arrivée dans un Hub doit rester bleue')
        self.assertNotIn(GREEN, colors, 'une arrivée ne doit pas être verte')


    # ---------- format 100 × 100 mm ----------
    def page_mm(self, payload):
        import re
        box = re.search(rb'/MediaBox\s*\[([^\]]+)\]', payload)
        self.assertIsNotNone(box, 'MediaBox absent du PDF')
        parts = [float(v) for v in box.group(1).split()]
        return round((parts[2] - parts[0]) / 72 * 25.4, 2), round((parts[3] - parts[1]) / 72 * 25.4, 2)

    def pdf_of(self, kind, did):
        response = self.client.get('/api/palette-docs/%s/%d/ticket.pdf' % (kind, did), headers=self.admin)
        self.assertEqual(response.status_code, 200, 'HTTP %s' % response.status_code)
        return response.data

    def test_ticket_palette_format_100x100(self):
        """Le ticket d'une palette tient sur un carré 100 × 100 mm, quel que soit le flux."""
        transfer = self.palette(10, 90, [3])
        self.assertEqual(self.page_mm(self.pdf_of('transfer', transfer)), (100.0, 100.0),
                         'le ticket de palette n’est pas en 100 × 100 mm')
        with self.conn() as c:
            c.execute("UPDATE parcels SET status='Refusé' WHERE id=1")
        retour = self.t.create_palette('agent', 10, 'return_to_central', 10, 90, [1], 910).get_json()['id']
        self.assertEqual(self.page_mm(self.pdf_of('transfer', retour)), (100.0, 100.0),
                         'le ticket de retour n’est pas en 100 × 100 mm')

    def test_ticket_long_texte_ne_deborde_pas(self):
        """Un nom de Hub très long est réduit/tronqué : le PDF reste généré en 100 × 100."""
        with self.conn() as c:
            c.execute("UPDATE ops_hubs SET name=? WHERE id=10",
                      ('HUB BOUJDOUR NORD · AGENCE PRINCIPALE TRES LONGUE',))
        did = self.palette(10, 90, [3])
        payload = self.pdf_of('transfer', did)
        self.assertEqual(self.page_mm(payload), (100.0, 100.0))
        self.assertIn(GREEN, pdf_colors(payload), 'la couleur de nature a disparu avec le texte long')


if __name__ == '__main__':
    unittest.main()
