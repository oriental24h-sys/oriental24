# Correction des filtres de dates — calendrier du Maroc

## Problème corrigé

Certaines dates « aujourd’hui » et les plages rapides étaient construites par `Date.toISOString()`, qui convertit d’abord en UTC. Au Maroc, autour de minuit, cette conversion pouvait faire afficher/filtrer le jour précédent. Le filtre des colis dans l’application livreur et les plages rapides des analyses pouvaient alors sembler décalés.

## Correction

Un helper commun construit désormais le jour civil `Africa/Casablanca`. Les filtres concernés sont :

- dates de l’application livreur (plage par défaut, raccourci Aujourd’hui, rendez-vous minimal);
- plages rapides 7 / 14 / 30 jours de l’analyse opérationnelle;
- date initiale de l’historique trajet du contrôle Ramassage.

La plage par défaut du livreur est maintenant calculée par jours calendaires, non par une différence de 60 × 24 heures. Les autres filtres et leurs périmètres métier n’ont pas été modifiés.

## Installation

Remplacer les fichiers inclus, redémarrer l’application et faire un rechargement forcé du navigateur. Le cache-buster JavaScript est inclus dans `templates/index.html`. Aucune migration de base n’est nécessaire.

## Vérification

- `PYTHONPATH=.:tests .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q` — 270 tests réussis.
- Toutes les suites `tests/frontend/*.cjs` et `tests/js/*.cjs` réussies.
- `tests/browser/test_list_pagination.py` réussi avec Chromium.

Le contrôle du filtre Date couvre une simulation de l’instant où UTC affiche encore la veille, alors qu’il est déjà le lendemain au Maroc. Aucun déploiement en production n’a été effectué.
