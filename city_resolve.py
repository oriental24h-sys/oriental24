"""Reconnaissance tolérante des villes (fautes de frappe, arabe, translittération).

Fonctionne pour **toute** ville présente dans la table `cities` : aucun nom ne doit
être ajouté à la main. Les alias ci-dessous ne servent qu'aux noms irréguliers
(ex. « الدار البيضاء » pour Casablanca) ; tout le reste est calculé :

1. correspondance exacte après normalisation (accents, casse, espaces, tirets) ;
2. alias connus (facultatif, accélérateur pour quelques noms irréguliers) ;
3. translittération arabe → latin, avec variantes (ج = j/dj/g, ق = q/k,
   و = ou/w/u, ي = i/y, ة = a…) puis comparaison aux noms de la base ;
4. comparaison « sans voyelles » : l'arabe n'écrit pas les voyelles courtes
   (« بركان » → brkn = Berkane), ce qui reconnaît les villes non listées ;
5. distance d'édition (faute de frappe : « Ojda », « Agadr ») ;
6. inclusion / saisie courte (« oujda centre », « jda »).

Rejet si deux villes sont aussi proches : on ne devine jamais à la place du client.
"""
import difflib
import re
import unicodedata

# DONNÉES facultatives : alias des noms irréguliers (graphie arabe non déductible du
# nom latin, ancien nom, surnom). Aucune ville n'a besoin d'être ajoutée ici : la
# translittération, le squelette consonantique et la distance d'édition couvrent le reste.
# Pour une ville dont la graphie arabe est irrégulière, le plus simple est de la saisir
# dans le champ « Nom en arabe » des paramètres Villes (colonne cities.name_ar).
ALIASES = {
    'casablanca': ['casa', 'dar el beida', 'dar lbaida', 'dar beida', 'darelbaida',
                   'الدار البيضاء', 'كازا', 'كازابلانكا', 'البيضاء', 'dar lbida'],
    'essaouira': ['mogador', 'الصويرة'],
    'el jadida': ['jadida', 'mazagan', 'الجديدة'],
    'fes': ['fez', 'fas', 'فاس'],
    'meknes': ['meknès'],
    'laayoune': ['laayoun', 'layoune', 'العيون'],
    'al hoceima': ['hoceima', 'الحسيمة', 'حسيمة'],
    'sidi bennour': ['sidi benour'],
    'oued zem': ['oued zem', 'واد زم', 'وادي زم'],
    'ait melloul': ['aït melloul'],
    'dcheira': ['الدشيرة', 'الدشيرة الجهادية'],
    'mohammedia': ['mohammadia'],
    'kenitra': ['qnitra', 'kénitra'],
    'tanger': ['tangier', 'tanja', 'tanjah', 'tandja', 'طنجة', 'طنجه'],
}

# Translittération : chaque lettre peut donner plusieurs latinisations usuelles.
ARABIC_ALTS = {
    'ا': ['a'], 'أ': ['a'], 'إ': ['i', 'a'], 'آ': ['a'], 'ٱ': ['a'],
    'ب': ['b'], 'ت': ['t'], 'ث': ['t', 's'], 'ج': ['j', 'dj', 'g'], 'ح': ['h'],
    'خ': ['kh', 'k'], 'د': ['d'], 'ذ': ['d', 'z'], 'ر': ['r'], 'ز': ['z'],
    'س': ['s'], 'ش': ['ch', 'sh'], 'ص': ['s'], 'ض': ['d'], 'ط': ['t'],
    'ظ': ['z', 'd'], 'ع': ['a', ''], 'غ': ['gh', 'g'], 'ف': ['f'],
    'ق': ['q', 'k'], 'ك': ['k'], 'ل': ['l'], 'م': ['m'], 'ن': ['n'],
    'ه': ['h', 'a'], 'ة': ['a', ''], 'و': ['ou', 'w', 'u'], 'ي': ['i', 'y'],
    'ى': ['a', 'i'], 'ء': [''], 'ئ': ['i', ''], 'ؤ': ['ou', 'o'],
}
ARABIC_RANGE = re.compile(r'[\u0600-\u06ff]')
TASHKEEL = re.compile(r'[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]')
NON_WORD = re.compile(r'[^a-z0-9]+')
VOWELS = re.compile(r'[aeiouy]')

MAX_VARIANTS = 24


def strip_accents(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    return ''.join(c for c in text if not unicodedata.combining(c))


def has_arabic(value):
    return bool(ARABIC_RANGE.search(str(value or '')))


def _latinise(text, choices):
    """Applique la translittération avec les choix indiqués (position → variante)."""
    out, step = [], 0
    for ch in text:
        alts = ARABIC_ALTS.get(ch)
        if alts:
            index = choices[step] if step < len(choices) else 0
            out.append(alts[min(index, len(alts) - 1)])
            step += 1
        else:
            out.append(ch)
    return ''.join(out)


def arabic_variants(value):
    """Latinisations possibles d'une saisie arabe (première = la plus probable)."""
    text = TASHKEEL.sub('', str(value or '')).replace('\u0640', '')
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return []
    if not has_arabic(text):
        return [text]
    # « ال » initial (article défini) inutile au rapprochement.
    stripped = re.sub(r'(^|\s)ال', r'\1', text)
    variants, seen = [], set()
    positions = [i for i, ch in enumerate(stripped) if len(ARABIC_ALTS.get(ch, [''])) > 1][:4]
    patterns = [[0] * len(stripped)]
    for pos in positions:
        extra = []
        for pattern in patterns:
            for alt_index in range(1, len(ARABIC_ALTS.get(stripped[pos], ['x']))):
                copy = list(pattern)
                copy[pos] = alt_index
                extra.append(copy)
        patterns.extend(extra)
        if len(patterns) > MAX_VARIANTS:
            break
    for pattern in patterns[:MAX_VARIANTS]:
        candidate = NON_WORD.sub('', strip_accents(_latinise(stripped, pattern).casefold()))
        if candidate and candidate not in seen:
            seen.add(candidate)
            variants.append(candidate)
    return variants


def key(value):
    """Clé de comparaison : sans accents, sans espaces, sans ponctuation."""
    text = strip_accents(value).casefold().replace('’', "'")
    text = TASHKEEL.sub('', text)
    text = NON_WORD.sub('', text)
    return text


DIGRAPHS = [('ch', 'c'), ('sh', 'c'), ('gh', 'g'), ('kh', 'k'), ('th', 't'), ('dh', 'd'),
            ('ou', 'u'), ('ph', 'f')]
BASE_EQUIVALENT = str.maketrans({'q': 'k', 'x': 'ks', 'v': 'f', 'p': 'b'})


def _skeleton_variants(text):
    """Squelettes possibles : le même son s'écrit c/k/s ou g/k selon la graphie."""
    base = key(text)
    for source, target in DIGRAPHS:
        base = base.replace(source, target)
    base = base.translate(BASE_EQUIVALENT)
    for letters in {('c', 'k'), ('c', 's'), ('g', 'k'), ('g', 'g')}:
        yield re.sub(r'(.)\1+', r'\1', VOWELS.sub('', base.replace(letters[0], letters[1])))


def skeleton_set(value):
    """Squelettes consonantiques d'un nom (voyelles non écrites en arabe)."""
    return {sk for sk in _skeleton_variants(value) if len(sk) >= 2}


def skeleton(value):
    """Squelette principal (le plus courant : c → k, g → g)."""
    return sorted(skeleton_set(value) or {key(value)})[0]


def keys_for(value):
    """Toutes les clés comparables d'une saisie (latin, arabe, variantes)."""
    keys = set()
    for variant in arabic_variants(value):
        base = key(variant)
        if base:
            keys.add(base)
    if not keys:
        base = key(value)
        if base:
            keys.add(base)
    return keys


def _alias_index():
    """Index alias : clés latines + variantes arabes + squelettes de chaque alias."""
    index = {}
    for canonical, values in ALIASES.items():
        strings = values + [canonical]
        for value in strings:
            for candidate in keys_for(value) or {key(value)}:
                if len(candidate) >= 3:
                    index.setdefault(candidate, canonical)
    return index


_ALIAS = None


def alias_target(value):
    global _ALIAS
    if _ALIAS is None:
        _ALIAS = _alias_index()
    for candidate in (keys_for(value) or {key(value)}):
        target = _ALIAS.get(candidate)
        if target:
            return target
    return None


def similarity(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def _score(wanted_keys, wanted_skels, row_keys, row_skels):
    """Meilleur score entre une saisie et une ville (clés exactes + squelettes)."""
    best = 0.0
    for wanted in wanted_keys:
        for other in row_keys:
            best = max(best, similarity(wanted, other))
    # Squelette identique = même consonnes malgré les voyelles non écrites en arabe.
    for wanted in wanted_skels:
        for other in row_skels:
            if wanted == other:
                best = max(best, 0.9)
            elif len(wanted) >= 4 and len(other) >= 4 and wanted[0] == other[0]:
                best = max(best, similarity(wanted, other) * 0.92)
    return best


def _skeleton_matches(index, wanted_skels):
    """Villes dont le squelette consonantique est identique à la saisie."""
    hits = []
    for row, row_keys, row_skels in index:
        if wanted_skels & row_skels:
            hits.append(row)
    unique = {row['id']: row for row in hits}
    return list(unique.values())


def resolve(city_rows, value, cutoff=0.82):
    """Retourne (ligne_ville, score, methode) ou (None, score, raison).

    `city_rows` : itérable de dicts/Row avec au moins id/name (et fee/return_fee).
    Méthodes : exacte | alias | alias partiel | arabe | corrigée | partielle |
               ambigu | inconnue | vide
    """
    raw = '' if value is None else str(value).strip()
    if not raw:
        return None, 0.0, 'vide'
    rows = [dict(r) if not isinstance(r, dict) else r for r in city_rows]
    if not rows:
        return None, 0.0, 'aucune ville'
    wanted_keys = keys_for(raw)
    if not wanted_keys:
        return None, 0.0, 'vide'
    wanted_skels = {skeleton(k) for k in wanted_keys if skeleton(k)}
    arabic_input = has_arabic(raw)

    index = []
    for row in rows:
        # « name_ar » : nom arabe saisi dans les paramètres Villes (facultatif).
        spellings = [row['name']] + [row.get('name_ar') or '']
        row_keys = set()
        row_skels = set()
        for spelling in spellings:
            if not spelling:
                continue
            row_keys |= {key(spelling)} | keys_for(spelling)
            row_skels |= skeleton_set(spelling)
        row_keys.discard('')
        row_skels.discard('')
        index.append((row, row_keys, row_skels))

    # 1. nom officiel de la base
    for row, row_keys, _ in index:
        if wanted_keys & row_keys:
            return row, 1.0, 'exacte'

    # 2. alias connus (noms irréguliers seulement)
    target = alias_target(raw)
    if target:
        target_key = key(target)
        for row, row_keys, _ in index:
            if target_key in row_keys:
                return row, 0.97, 'alias'
        for row, row_keys, _ in index:
            if any(k.startswith(target_key) or target_key.startswith(k) for k in row_keys):
                return row, 0.9, 'alias partiel'

    # 3. squelette consonantique (« بركان » → brkn = Berkane, « سلا » → sl = Salé)
    matches = _skeleton_matches(index, {sk for sk in wanted_skels if len(sk) >= 2})
    if matches:
        def full_key_score(row):
            return max((similarity(w, k) for w in wanted_keys for k in row_key_sets[id(row)]), default=0.0)
        row_key_sets = {id(row): row_keys for row, row_keys, _ in index}
        ranked = sorted(matches, key=full_key_score, reverse=True)
        best = ranked[0]
        margin = full_key_score(best) - (full_key_score(ranked[1]) if len(ranked) > 1 else 0.0)
        if len(ranked) == 1 or margin >= 0.08:
            method = 'arabe' if arabic_input and key(best['name']) not in wanted_keys else 'corrigée'
            return best, 0.9, method
        # Deux villes partagent ces consonnes et aucune ne se détache : on ne devine pas.
        return None, 0.9, 'ambigu'

    # 4. translittération / faute de frappe
    # Une saisie courte (« sla », « asfi ») a peu de lettres : seuil adapté.
    short = min(len(k) for k in wanted_keys) <= 4
    local_cutoff = min(cutoff, 0.72) if short else cutoff
    scored = sorted(((_score(wanted_keys, wanted_skels, row_keys, row_skels), row, row_keys)
                     for row, row_keys, row_skels in index),
                    key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] >= local_cutoff:
        best_score, best, best_keys = scored[0]
        if len(scored) > 1 and scored[1][0] >= cutoff and abs(best_score - scored[1][0]) < 0.02 \
                and best['id'] != scored[1][1]['id']:
            return None, best_score, 'ambigu'
        method = 'arabe' if arabic_input and not (wanted_keys & best_keys) else 'corrigée'
        return best, best_score, method

    # 5. saisie courte contenue dans un seul nom (« jda » → Oujda, « ber » → Berkane)
    for wanted in wanted_keys:
        if len(wanted) < 3:
            continue
        contained = [row for row, row_keys, _ in index if any(wanted in k for k in row_keys)]
        if len(contained) == 1:
            return contained[0], 0.8, 'partielle'

    # 6. inclusion (« oujda centre », « ville d'agadir »)
    inside = []
    for row, row_keys, _ in index:
        for k in row_keys:
            if len(k) >= 4 and any(k in wanted for wanted in wanted_keys):
                inside.append((len(k), row))
    if inside:
        inside.sort(key=lambda item: item[0], reverse=True)
        if len(inside) == 1 or inside[0][0] > inside[1][0]:
            return inside[0][1], 0.88, 'partielle'

    return None, scored[0][0] if scored else 0.0, 'inconnue'


def explain(value, row, method):
    """Message court prêt à afficher dans une prévisualisation d'import."""
    if row is None or method == 'exacte':
        return ''
    saisie = str(value).strip()
    if method == 'arabe':
        return '« %s » (arabe) reconnue comme %s' % (saisie, row['name'])
    return '« %s » reconnue comme %s' % (saisie, row['name'])
