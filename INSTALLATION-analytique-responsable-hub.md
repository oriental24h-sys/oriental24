# ORIENTAL24 — Analytique du responsable Hub

## Installation

Ce ZIP contient seulement les fichiers concernés par l’ajout Analytique, pas le projet complet. À appliquer sur la version précédente comprenant les factures Hubs Paid et les modifications déjà livrées.

1. Sauvegarder le code et la base SQLite.
2. Copier les fichiers en conservant leurs chemins. Nouveaux fichiers nécessaires : `hub_manager_analytics.py` et `static/hub-manager-analytics.js`.
3. Redémarrer le service Python puis recharger la page sans cache.

Aucune nouvelle dépendance, aucune modification des calculs financiers, paiements ou statuts de commandes. Cette fonctionnalité est en lecture seule et ne crée aucun historique fictif.

## Utilisation

Chez le responsable du Hub, nouveau menu **ANALYTIQUE → Analytique**, avec trois onglets :

### Activité du Hub

Hub du compte uniquement, nombre d’assignés, de traités, d’attentes, progression et indicateur de risque (moins de 50 % de traitement, uniquement si des affectations existent). Le responsable ne voit aucun autre Hub.

### Analyse des livreurs

Classement et affichage cartes / tableau : assignés, traités, livrés, retournés, progression, taux de livraison/retour, attentes. Le bouton En attente ouvre la liste des colis concernés avec tracking, affectation et dernière tentative. Un filtre permet de ne conserver que les livreurs à risque. Le total global représente toujours le périmètre de dates/livreur choisi, pas uniquement les cartes après filtre de risque.

### Activité quotidienne

Matrice **livreurs × jours**. Chaque case indique le nombre de colis distincts affectés au livreur ce jour-là. Un clic ouvre le détail de cette journée. Indicateurs : jours sélectionnés, comptes actifs, moyenne quotidienne de livreurs avec affectation, jours-livreurs sans affectation et comptes actifs sans aucune affectation sur la période.

**Important :** un jour sans affectation ne prouve pas une absence. « Jamais travaillé » signifie ici uniquement « aucune affectation enregistrée dans la période », pas « n’a jamais travaillé depuis sa création ».

## Filtres et export

- Période personnalisée, limitée à 31 jours inclus ; raccourcis Aujourd’hui / 7 / 14 / 30 jours.
- Heures saisies en **Africa/Casablanca**, conversion des dates serveur pour lire les événements.
- Filtre par livreur, bouton Actualiser et export CSV de la vue sélectionnée. Le CSV exporté depuis l’interface respecte les filtres de risque / sans affectation.
- Le sélecteur ne propose que les livreurs actuellement rattachés au Hub. Les comptes inactifs rattachés restent visibles pour leurs données opérationnelles ; les indicateurs de capacité utilisent les comptes actifs uniquement.

## Définitions de calcul

- Périmètre fondé sur les **affectations enregistrées dans la période**, avec leur `hub_id`. Les affectations sans preuve Hub ne sont ni attribuées par ville ni déduites de la position actuelle du colis.
- Résumé : un couple **colis / livreur** distinct sur la période. Une réaffectation du même colis à deux livreurs peut donc compter pour chacun. Plusieurs affectations au même livreur ne gonflent pas son total : le dernier cycle sélectionné est retenu.
- **Traité** : au moins une tentative du même livreur, enregistrée pour le même Hub après l’affectation retenue, avant l’affectation suivante et avant la fin du filtre. Toutes les tentatives comptent comme traitement, y compris Reporté et Injoignable ; elles ne sont pas assimilées à des livraisons.
- La dernière tentative du cycle fournit le résultat Livré / Retourné / Refusé affiché. Les tentatives répétées ne gonflent pas le nombre de colis traités.
- **En attente** : couple colis / livreur affecté sans tentative admissible dans ce cycle.
- **Progression** = traités / assignés ; taux de livraison = livrés / assignés. Zéro affectation donne 0 %, sans division par zéro.
- Matrice quotidienne : colis distincts par livreur et date d’affectation. Un même colis affecté sur deux jours est présent dans les deux cases. Les sommes quotidiennes ne sont donc pas nécessairement égales au total distinct de toute la période.
- Les anciens enregistrements qui ne contiennent pas les snapshots Hub nécessaires ne sont pas inventés. Les totaux de ce module peuvent différer d’une liste de stock actuel ou de la finance : ils mesurent des cohortes d’affectations.

## Sécurité

Route réservée au rôle agent / responsable, avec Hub actif requis. Le Hub est imposé côté serveur depuis le compte ; aucun paramètre Hub tiers accepté. Un livreur hors périmètre est refusé. Les détails et exports utilisent le même périmètre. Les accès administrateur existants aux autres statistiques ne sont pas modifiés.

## Tests

**172 tests Python réussis**, incluant cloisonnement réel HTTP, filtres de dates, CSV, Hub inactif, traitement Reporté/Injoignable, tentatives hors période ou hors Hub, déduplication, réaffectations et jours au fuseau marocain. Tests JavaScript de la navigation, cartes, matrice, filtres, détails et export réussis ; régression JavaScript factures réussie. Vérification syntaxique et `git diff --check` réussis.

Pas de déploiement ni validation visuelle dans un navigateur réel effectués.
