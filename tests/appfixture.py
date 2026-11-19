"""Fixture partagée : un seul module `app` par processus de test.

Plusieurs fichiers de tests HTTP importent `app`. Quand `pytest` exécute
plusieurs fichiers dans le même processus, le module est mis en cache : le
second fichier doit réutiliser la même base, sinon il travaille sur un fichier
déjà supprimé par le premier (`unable to open database file`).

Règle : le premier fichier crée la base temporaire, les suivants la réutilisent.
Le dossier temporaire n'est jamais supprimé pendant la suite (il vit dans /tmp) :
ainsi aucun test ultérieur ne pointe vers une base disparue.
"""
import importlib
import os
import sys
import tempfile

_holder = {'tmp': None, 'created': False}


def acquire(directory='app-tests'):
    """Renvoie (module_app, est_il_le_createur)."""
    module = sys.modules.get('app')
    if module is not None:
        return module, False
    if _holder['tmp'] is None:
        _holder['tmp'] = tempfile.TemporaryDirectory()
    os.environ['DB_PATH'] = os.path.join(_holder['tmp'].name, directory + '.sqlite')
    os.environ['ORIENTAL24_MODE'] = 'demo'
    _holder['created'] = True
    return importlib.import_module('app'), True


def release():
    """Libère la référence ; la base reste sur disque pour les fichiers suivants."""
    return None
