# Correction du comptage « Traités / En attente » — 25 octobre 2026

## Problème corrigé
L’analytique ne lisait que `ops_attempts`. Or plusieurs parcours autorisés du livreur enregistrent leur résultat uniquement dans `events` via PATCH `/api/parcels/<id>` : par exemple Annulé, Intéressé, Reporté depuis Reçu par le livreur. Ces traitements pouvaient rester affichés « En attente ».

Le calcul lit désormais les tentatives structurées **et** les changements d’état de traitement réellement effectués par le livreur dans son cycle d’affectation. Le détail affiche la preuve : « Tentative enregistrée » ou « Changement d’état ».

Unité de comptage : un colis par livreur dans le dernier cycle d’affectation retenu. Une tentative et son événement miroir ne comptent jamais deux fois. Le résultat retenu est le dernier traitement admissible, pas simplement le statut actuel du colis.

États de traitement reconnus dans l’historique : Livré, Programmé, Refusé, Retourné, Reporté, Intéressé, Annulé ; prise en compte également d’un éventuel ancien événement Injoignable. L’événement doit être signé par le livreur affecté et constituer un changement réel par rapport au précédent état métier. En absence d’historique antérieur, seules les traces explicites de mise à jour du statut / de tentative sont admissibles.

## Garanties conservées
- Uniquement le Hub actif du responsable, via l’affectation enregistrée ; jamais une déduction par ville.
- Traitement situé après l’affectation, avant la prochaine réaffectation et avant la fin de période.
- Une tentative ancienne sans snapshot de Hub (`NULL`) peut être rattachée au cycle d’affectation explicite de ce Hub. Une affectation sans Hub n’est pas récupérée par supposition.
- Une tentative portant explicitement un autre Hub demeure exclue ; son événement miroir ne contourne pas cette exclusion.
- Retour physique / réception en agence, note ou preuve sans changement d’état, action d’un client ou du responsable : ne constituent pas à eux seuls un traitement du livreur.
- Aucun changement des statuts, de la garde physique, des affectations ou des données financières ; pas d’écriture rétroactive ni de migration de base.

## Exemple vérifié
Sur une base de test isolée, avec authentification et appels HTTP réels :
- 4 colis affectés ;
- 1 livraison par l’API de tentative ;
- 3 résultats via l’API de changement de statut : Annulé, Intéressé, Reporté ;
- récupération physique de ces trois colis au Hub.

Résultat avant et après récupération : **4 traités, 0 en attente, progression 100 %, taux de livraison 25 %**. La base ne contient qu’une tentative structurée : les trois autres traitements sont retrouvés dans l’historique.

Ces tests valident le défaut du code et sa correction. Ils ne constituent pas une consultation de la base réelle du client ni une confirmation des historiques des quatre colis de sa capture.

## Installation
Prérequis : version cumulative avec le module Analytique du responsable de Hub et le dernier correctif de présentation déjà installés.

1. Sauvegarder les fichiers actuels.
2. Remplacer, aux mêmes chemins :
   - `hub_manager_analytics.py`
   - `static/hub-manager-analytics.js`
   - `templates/index.html`
3. Redémarrer le service Python/Gunicorn suivant votre hébergement.
4. Recharger la page sans cache (Ctrl+F5), puis relancer le filtre de période.
5. Dans Analyse des livreurs, ouvrir le détail : les changements de statut historiques admissibles sont pris en compte automatiquement. Aucun besoin de modifier à nouveau les colis.

Les fichiers `tests/` sont les tests de régression ; ils ne sont pas nécessaires à l’exécution en production. L’archive ne contient que les fichiers modifiés pour cette correction et cette notice, pas le projet complet. Le menu latéral et le design ne sont pas modifiés.

## Vérifications réalisées
- 180 tests Python réussis (analytique, HTTP réel, Hub, récupération, facturation, PDF, réception, départ, COD, compteurs).
- Tests JavaScript de l’analytique et de la facturation réussis.
- Vérification de syntaxe JavaScript et `git diff --check` réussies.

Aucun déploiement ni envoi GitHub effectué.
