"""Références et codes de suivi des palettes — générés automatiquement.

Une palette se reconnaît à son préfixe, selon la nature du mouvement :
  · **RP-** palette à RÉCEPTIONNER (arrivée société, transfert inter-Hub) ;
  · **RT-** palette RETOUR (vers le Central, vers le Hub d'origine, retour vendeur) ;
  · **RM-** palette RAMASSAGE.

Les anciennes références (`PP-`, `TRF-`, `RET-`, `RTO-`, `PR-`, `RAM-`) restent valides :
la numérotation continue par-dessus pour ne jamais réutiliser un numéro.

Le **code de suivi** (bordereau transporteur) est rempli automatiquement quand
l'utilisateur n'en saisit pas : il est unique et ne bloque jamais la création.
"""
import secrets

FAMILIES = {
    'reception': ('RP', ('RP', 'PP', 'TRF')),
    'retour': ('RT', ('RT', 'RET', 'RTO', 'PR')),
    'ramassage': ('RM', ('RM', 'RAM')),
}


def family_of(kind, purpose='standard'):
    """Nature de la palette : `reception`, `retour` ou `ramassage`."""
    if kind in ('pickup', 'ramassage'):
        return 'ramassage'
    if kind in ('return', 'return_palette', 'retour'):
        return 'retour'
    if kind in ('transfer', 'partner_palette', 'partner'):
        if purpose in ('return_to_central', 'return_to_origin'):
            return 'retour'
        return 'reception'
    return 'reception'


def prefix_of(kind, purpose='standard'):
    return FAMILIES[family_of(kind, purpose)][0]


def next_reference(c, kind, purpose='standard'):
    """Prochaine référence libre : RP-000042 / RT-000007 / RM-000003."""
    prefix, history = FAMILIES[family_of(kind, purpose)]
    highest = 0
    for old in history:
        row = c.execute("SELECT MAX(CAST(substr(reference, ?) AS INTEGER)) FROM ops_documents WHERE reference LIKE ?",
                        (len(old) + 2, old + '-%')).fetchone()
        if row and row[0]:
            highest = max(highest, int(row[0]))
    number = highest + 1
    while c.execute('SELECT 1 FROM ops_documents WHERE reference=?', ('%s-%06d' % (prefix, number),)).fetchone():
        number += 1
    return '%s-%06d' % (prefix, number)


def auto_tracking_code():
    """Bordereau interne : 16 caractères hexadécimaux (même format que les palettes existantes)."""
    return secrets.token_hex(8)


def tracking_or_auto(value):
    text = str(value or '').strip()[:80]
    return text or auto_tracking_code()
