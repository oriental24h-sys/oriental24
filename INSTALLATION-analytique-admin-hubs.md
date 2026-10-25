# Analytique Admin — comparaison des Hubs

## Fonctionnalité
Une entrée **Analytique**, réservée à Admin, ouvre trois vues reprenant les composants et les couleurs de l’analytique du responsable de Hub :

1. **Activité générale** : synthèse globale des Hubs, affectations nettes, traitements, attentes, progression et cartes des Hubs.
2. **Analyse des Hubs** : classement des Hubs, cartes ou tableau, livrés, retournés, assignés, attentes, progression et taux de livraison/retour.
3. **Activité quotidienne des Hubs** : matrice Hubs × jours ou liste, nombre de jours actifs, Hubs actifs, moyenne quotidienne, jours sans activité et filtre Sans activité.

Filtres de dates en heure du Maroc, raccourcis de périodes, sélection d’un Hub ou Tous les Hubs, filtre de risque, export CSV et détails des colis en attente / des affectations. Cliquer une case quotidienne ouvre les colis du Hub correspondant, avec le même périmètre net que la matrice.

Chaque ligne/carte compare un **Hub**, pas un livreur. Les noms des livreurs ne sont pas les unités de comparaison de cette interface.

## Règles de calcul
Les données proviennent des affectations aux livreurs ayant un rattachement explicite au Hub : même source opérationnelle que l’analytique existante des responsables. Ce n’est pas un nouvel inventaire de tous les colis physiquement présents dans un Hub : un colis jamais affecté à un livreur n’entre pas dans les Assignés de cette analyse.

- Scans/remises moins récupérations, avec maintien des Livrés.
- Traitement : tentative structurée ou changement d’état admissible du livreur, borné au cycle d’affectation et à la période.
- Un colis compte une fois par Hub : dernière affectation du colis dans ce Hub sur la période, sans doublon si plusieurs livreurs se sont succédé. Un dernier cycle récupéré ne réactive pas un ancien cycle.
- La matrice attribue le colis au jour de cette affectation retenue, avec le même périmètre net que la carte du Hub.
- Les totaux globaux additionnent les périmètres des Hubs ; ils ne sont pas un comptage des trackings uniques du réseau si un colis a participé à plusieurs Hubs durant la période.
- Pourcentages globaux pondérés par les volumes, jamais une moyenne des pourcentages des Hubs.
- Hubs sans activité et Hubs inactifs restent visibles ; les indicateurs d’activité des Hubs actifs les distinguent.
- Les filtres risque / sans activité limitent la liste affichée ; la synthèse du périmètre sélectionné demeure stable.
- Le rattachement n’est jamais déduit de la ville du destinataire.

## Sécurité et non-régression
GET `/api/admin-hub-analytics` est réservé à Admin. Les responsables de Hub, clients, livreurs et visiteurs n’obtiennent pas cet accès global. Le contrôle serveur existe indépendamment de la visibilité du menu.

Les vues du responsable de Hub conservent leur propre état JavaScript et leur API limitée à leur Hub. Aucun changement de leurs fichiers de calcul ou d’affichage. Aucune migration de base ni écriture dans les données opérationnelles. Aucun changement du scan, du dé-scan, des statuts, des factures ou des paiements. Pas de refonte du sidebar : seulement ajout de l’entrée Analytique visible pour Admin.

## Installation
Prérequis : version cumulative installée avec l’Analytique du responsable de Hub, son design de référence et le correctif Assignés nets. Les fichiers existants `hub_manager_analytics.py` et `static/hub-manager-analytics.css` sont réutilisés et ne sont pas remplacés par cette archive.

1. Sauvegarder les fichiers actuels.
2. Copier aux mêmes chemins les cinq fichiers d’exécution :
   - `admin_hub_analytics.py` (nouveau)
   - `static/admin-hub-analytics.js` (nouveau)
   - `app.py`
   - `static/app.js`
   - `templates/index.html`
3. Redémarrer le service Python/Gunicorn.
4. Se connecter en Admin, recharger sans cache (Ctrl+F5), puis ouvrir **Analytique**.

Les trois fichiers `tests/` et cette notice sont fournis pour la vérification. L’archive contient uniquement les fichiers ajoutés/modifiés pour cette fonctionnalité, pas le projet complet. Aucun envoi GitHub ou déploiement effectué.

## Vérifications effectuées
- **197 tests Python réussis** : agrégation multi-Hubs, pondération, déduplication, filtres, jours vides, récupération, maintien des Livrés, dernier cycle, événements historiques, lecture seule, HTTP authentifié, refus des accès non Admin, exports CSV et non-régression des autres modules.
- **8 suites JavaScript réussies** : navigation, cartes/liste, matrice/liste, filtres, détails, CSV, isolation d’état Admin/responsable, facturation, permissions, compteurs et livraison.
- Syntaxe JavaScript et `git diff --check` validés.

Ces vérifications utilisent des données de test isolées et des tests frontend automatisés ; elles ne constituent pas une vérification de la base ou du déploiement réel du client.
