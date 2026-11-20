"""Remise à zéro des données, pilotée par l'Administrateur.

Ce module n'expose que trois routes, toutes réservées au rôle `admin` :

* `GET  /api/admin/data-reset`  → aperçu (compteurs avant, tables qui seront
  vidées, ce qui est conservé). Aucune écriture.
* `POST /api/admin/data-reset`  → exécution réelle. Trois verrous :
  1. mot de passe du compte administrateur ;
  2. phrase exacte « REMETTRE A ZERO » ;
  3. jeton CSRF habituel.
* `POST /api/admin/data-reset/seed-demo` → réinjecte le jeu de démonstration
  (mode démo uniquement) pour retrouver une préversion utilisable.

Aucune sauvegarde n'est créée : la décision est explicite côté produit. En
contrepartie, l'opération est :
* atomique (une seule transaction : tout ou rien) ;
* protégée par une double confirmation : phrase exacte + mot de passe admin ;
* traçable (empreinte SHA-256 de l'état avant/après dans le journal d'audit) ;
* confirmée par un recomptage : si une seule ligne métier subsiste, l'appel
  échoue avec la liste des tables concernées.
"""
import os
from functools import wraps
from pathlib import Path

from flask import jsonify, request
from werkzeug.security import check_password_hash

import data_reset

PHRASE = 'REMETTRE A ZERO'


def phrase_key(value):
    """Normalise la phrase de confirmation : casse, accents et espaces ignorés."""
    import unicodedata
    text = unicodedata.normalize('NFD', str(value or ''))
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    return ' '.join(text.replace('\u00a0', ' ').split()).upper()


def register_data_reset(app, services):
    conn = services['conn']
    auth = services['auth']
    user = services['user']
    Error = services['APIError']
    now = services['now']

    def admin_only(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            actor = user()
            if actor.get('role') != 'admin':
                raise Error('Remise à zéro réservée à l’Administrateur.', 403)
            return fn(actor, *args, **kwargs)
        return wrapper

    def reset_allowed_here():
        """La remise à zéro est toujours possible : seule la double confirmation
        (phrase exacte + mot de passe administrateur) décide."""
        return True

    def deployment_facts():
        """Ce que l'admin doit voir pour savoir OÙ il travaille (Railway/volume)."""
        return {'mode': 'production' if app.config['PRODUCTION_MODE'] else 'demo',
                'database': Path(app.config.get('DB_PATH') or '').name or 'oriental24.sqlite',
                'allowed': reset_allowed_here()}

    def preview_payload(c):
        return {'before': data_reset.counters(c),
                'tables': len(data_reset.purge_targets(c)),
                'kept': sorted(data_reset.KEEP_TABLES),
                'demo': bool(app.config['DEMO_MODE']),
                'allowed': reset_allowed_here(),
                'deployment': deployment_facts(),
                'phrase': PHRASE}

    @app.get('/api/admin/data-reset')
    @auth('admin')
    @admin_only
    def data_reset_preview(actor):
        with conn() as c:
            return jsonify(preview_payload(c))

    @app.post('/api/admin/data-reset')
    @auth('admin')
    @admin_only
    def data_reset_run(actor):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise Error('Objet JSON requis.')
        typed = str(payload.get('confirmation', ''))
        import re as _re
        if '@' in typed or _re.fullmatch(r'[+\d][\d\s().-]{5,}', typed.strip()):
            raise Error('La zone de confirmation contient une adresse e-mail ou un numéro de téléphone : '
                        'effacez-la et tapez « ' + PHRASE + ' ».')
        if phrase_key(typed) != PHRASE:
            raise Error('Tapez exactement « ' + PHRASE + ' » pour confirmer la remise à zéro.')
        password = str(payload.get('password', ''))[:129]
        if not password:
            raise Error('Votre mot de passe administrateur est obligatoire.')
        keep_accounts = payload.get('keep_accounts', True)
        if type(keep_accounts) is not bool:
            raise Error('Option keep_accounts invalide.')
        reseed = bool(payload.get('reseed_demo', False))
        if reseed and not app.config['DEMO_MODE']:
            raise Error('Le jeu de démonstration ne s’injecte qu’en mode démonstration.', 409)
        with conn() as c:
            stored = c.execute('SELECT password FROM users WHERE id=?', (actor['id'],)).fetchone()
            if not stored or not check_password_hash(stored[0], password):
                raise Error('Mot de passe administrateur incorrect.', 400)
            # Une variable d'environnement n'est plus exigée : la double confirmation
            # « phrase exacte + mot de passe administrateur » suffit et ne dépend
            # d'aucun redéploiement Railway.
            try:
                report = data_reset.reset_operations(
                    c, keep_accounts=keep_accounts, reseed_demo=reseed, actor=actor, now=now())
            except data_reset.ResetRefused as exc:
                raise Error(str(exc), 409) from exc
            leftovers = data_reset.verify_empty(c)
        if leftovers:
            raise Error('Remise à zéro incomplète : ' + ', '.join(sorted(leftovers)) + '.')
        report['leftovers'] = leftovers
        report['message'] = ('Remise à zéro terminée : ' + str(report['tables_purged']) +
                             ' tables vidées' + (' · jeu de démonstration réinjecté' if reseed else '') + '.')
        return jsonify(report)

    @app.post('/api/admin/data-reset/seed-demo')
    @auth('admin')
    @admin_only
    def data_reset_seed_demo(actor):
        if not app.config['DEMO_MODE']:
            raise Error('Le jeu de démonstration ne s’injecte qu’en mode démonstration.', 409)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            seeded = data_reset.seed_demo(c)
            c.execute('COMMIT')
            after = data_reset.counters(c)
        return jsonify(ok=True, seeded=bool(seeded), after=after)
