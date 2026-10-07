# ORIENTAL24 — Plateforme de livraison & logistique

Version **1.12.0** — 35 technologies (RFID, pick-by-voice, chargement LIFO, IA locale, IoT,
blockchain de preuve, entrepôt intelligent, robotique, drone, points relais…).

Interface française, adaptée au mobile, **sans aucune dépendance payante** (pas de Google Maps,
Firebase, WhatsApp Business API ni agrégateur de paiement).

## Stack

| Élément | Valeur |
|---|---|
| Backend | **Python 3.13 + Flask 3.1** |
| Serveur | **gunicorn** (WSGI) |
| Frontend | **HTML / CSS / JavaScript natifs** (aucun framework, aucun build) |
| Base de données | **SQLite** (fichier unique, 74 tables) |
| Node.js / PHP / MySQL | **non requis** |

## Installation locale (mode démo)

```bash
pip install -r requirements.txt
python app.py                 # → http://localhost:3000
```

Le mode démo génère une base d'essai automatiquement (aucune configuration requise).
Comptes d'essai : `admin@oriental24.ma` · `client@oriental24.ma` · `livreur@oriental24.ma`
— mot de passe `Oriental24!Demo`.

## Mise en production

Voir **`GUIDE-DEPLOIEMENT-RENDER.md`** (pas à pas) et le modèle **`.env.production.example`**.

Variables obligatoires : `ORIENTAL24_MODE=production`, `SECRET_KEY` (≥ 32 caractères aléatoires),
`DB_PATH` (chemin absolu, dossier en 0700), `ORIENTAL24_TRUSTED_HOSTS` (votre domaine).
Sans elles, l'application **refuse de démarrer** (fail-closed).

```bash
gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 60 app:app
```

Premier administrateur :

```bash
python manage.py init-admin --email admin@votre-domaine.ma --name "Votre Nom"
# ou, sans shell : variable ORIENTAL24_BOOTSTRAP_ADMIN="email|Nom|MotDePasse>=12"
```

Outil d'exploitation : `python manage.py backup|restore|verify|reset-password|prune-security`.

## Contenu de ce paquet

```
app.py                 application Flask (routes, auth, colis, facturation…)
runtime.py             configuration démo / production (fail-closed)
security.py            sessions, CSRF, limites de connexion, audit
…                      30 modules métier (logistique, entrepôt, tour de contrôle, IA, RFID…)
manage.py              outil d'exploitation (init-admin, sauvegarde, restauration)
templates/index.html   page unique servie par Flask
static/                31 JS + 18 CSS + polices (factures PDF) + icônes
requirements.txt       11 dépendances (Flask, gunicorn, reportlab, qrcode, openpyxl…)
Procfile · render.yaml · runtime.txt · .env.production.example
GUIDE-DEPLOIEMENT-RENDER.md
```

Les tests automatisés (33 fichiers), les scripts QA, les miroirs de démonstration hors-ligne
et les guides de version ne sont **pas inclus** dans ce paquet de déploiement.

## Sécurité

HTTPS obligatoire en production · cookies de session `__Host-` (HttpOnly, Secure, SameSite=Lax)
· jeton CSRF sur chaque écriture · limitation des tentatives de connexion · journal d'audit
· révocation immédiate des sessions · taille de requête limitée à 2 Mo.
