# Analytique uniquement : Assignés et activité quotidienne nets

## Règle confirmée
Dans les vues Analytique du responsable de Hub uniquement :
- scan / remise au livreur : le colis entre dans les Assignés ;
- dé-scan / récupération physique : le colis sort des Assignés et du nombre de la journée d’affectation correspondante ;
- les colis Livrés restent comptés au livreur.

Exemple testé : 4 colis scannés, dont 2 livrés et 2 récupérés => Assignés 2, Livrés 2, tableau quotidien 2, En attente 0. Les compteurs de traitement et les pourcentages de cette vue sont calculés sur le même périmètre net : progression 100 %, livraison 100 % dans cet exemple, au lieu de 50 % sur les 4 affectations brutes.

La récupération ne devient pas une tentative de livraison. Les colis récupérés sont simplement retirés du périmètre de cette analyse. Leurs statuts et leurs historiques restent intacts dans le système.

## Périmètre technique
Le calcul lit l’audit des remises/récupérations (`driver_workspace_audit`) et, en secours pour les anciennes données, les réceptions (`driver_receipts`). Seules les opérations du même colis, du même livreur et du cycle d’affectation considéré sont retenues, jusqu’à la fin de la période sélectionnée. Une récupération postérieure à la période ne réécrit pas son résultat historique. Une nouvelle remise ouvre un nouveau cycle comptable dans l’analyse.

Les affectations et la visibilité restent limitées au propre Hub actif du responsable. Les changements de statut de traitement historiquement enregistrés sans tentative structurée restent reconnus par le correctif précédent.

Aucun changement apporté aux routes de scan/dé-scan, aux affectations, aux statuts, à la garde physique, à la facturation, aux paiements, au sidebar ou aux autres écrans. Aucune migration ni mise à jour de données : le code de calcul fait uniquement des lectures.

## Installation
Prérequis : version cumulative existante avec l’Analytique du responsable de Hub et son design de référence.

1. Sauvegarder les fichiers existants.
2. Remplacer aux mêmes chemins :
   - `hub_manager_analytics.py`
   - `static/hub-manager-analytics.js`
   - `templates/index.html`
3. Redémarrer le service Python/Gunicorn.
4. Recharger sans cache (Ctrl+F5) puis appliquer la période souhaitée dans Analytique.

Cette archive inclut le précédent correctif de reconnaissance des changements de statut : il n’est pas nécessaire de réinstaller son ancienne archive par-dessus celle-ci.

Les trois fichiers de tests fournis servent à la vérification, pas à l’exécution en production. L’archive contient seulement les fichiers modifiés pour ce correctif et cette notice, pas le projet complet.

## Vérification
187 tests Python réussis, dont :
- 4 scans moins 2 récupérations donnent 2 Assignés et 2 dans le tableau quotidien ;
- maintien des Livrés ;
- récupération sans traitement : retrait du périmètre, pas traitement fictif ;
- récupération après la période, reprise après récupération, mauvais livreur et réaffectation ;
- appels HTTP authentifiés de changement de statut puis récupération, sans altérer les données opérationnelles.

Tests JavaScript de l’analytique et de la facturation réussis, syntaxe JavaScript et `git diff --check` validés.

Aucun déploiement, envoi GitHub ni accès à la base réelle du client effectué.
