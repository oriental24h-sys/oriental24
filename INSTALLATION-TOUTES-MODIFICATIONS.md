# ORIENTAL24 — ZIP cumulatif des modifications récentes

## Cible et contenu
Dépôt : oriental24h-sys/oriental24
Branche : feature/hub-manager-ramassage-palettes
Base utilisée : commit 0a5ba46 (réceptions unifiées déjà intégrées).

Ce ZIP contient les fichiers modifiés/ajoutés depuis cette base, PAS le dépôt complet. Il rassemble les dernières versions des fichiers des livraisons successives. Il remplace les ZIP suivants :
- envoi-palettes-scan-tous-dashboards.zip
- palettes-destination-selection-transit-update.zip
- admin-mots-de-passe-securises-update.zip
- retrait-sections-admin-hub.zip
- pagination-tous-dashboards-update.zip
- commandes-dernier-etat-en-premier.zip

Il suffit d’appliquer CE ZIP, sans réappliquer ces anciens ZIP après lui. Les modifications plus anciennes déjà présentes dans la base du dépôt restent conservées.

## Installation
1. Sauvegarder la base de données persistante et les fichiers actuels.
2. Ouvrir la branche cible, pas la branche par défaut.
3. Extraire le ZIP À LA RACINE du dépôt : app.py au même niveau que l’app.py existant ; fichiers static/ dans static/, templates/ dans templates/. Accepter le remplacement des fichiers concernés ; conserver tous les autres fichiers du dépôt.
4. Si des modifications indépendantes ont été faites depuis la base indiquée, comparer/fusionner avant remplacement pour ne pas les écraser.
5. Enregistrer les fichiers sur cette branche, puis redéployer le service Railway correspondant.
6. Conserver les variables d’environnement et le volume/base de production. Aucune base de données, aucun secret ni aucune nouvelle dépendance n’est fourni dans ce ZIP.
7. Attendre le redémarrage complet puis recharger le navigateur. Les scripts modifiés ont des versions de cache actualisées.

Les mises à niveau prévues par l’application s’exécutent au démarrage, notamment le remplacement du déclencheur de date de changement de statut. Ne pas remplacer la base de production par une base de test.

## Modifications réunies
### Envoi des palettes par scan
Collecte des scans puis confirmation finale pour transferts inter-hubs, palettes Société et retours. Aucun envoi partiel silencieux pendant la collecte : validation finale atomique, contrôle de l’ensemble attendu et conservation des droits existants. Les réceptions unifiées déjà intégrées restent présentes ; la démonstration HTML autonome n’est pas la cible de cette livraison.

### Destination et transit
Au départ du Hub Central, sélection limitée aux villes affectées au Hub destinataire. Sélectionner/désélectionner tout avec compteur ; limite de création existante de 100 colis maintenue. Les changements de trajet réinitialisent la sélection et les réponses tardives ne remplacent pas le trajet courant.
La colonne Livreur / Agence identifie le transit selon le transfert réel : vers Hub Central ou vers la ville de destination.

### Mots de passe Admin
Création des clients Vendeur/Société, livreurs, Support et Responsables Hub : mot de passe aléatoire affiché une seule fois avec bouton Copier.
Réinitialisation ultérieure avec confirmation et mot de passe de l’Admin ; ancien mot de passe remplacé et anciennes sessions révoquées. Les comptes Admin restent exclus de cette gestion. Stockage par hash, sans consultation ultérieure du mot de passe personnel.
La fenêtre se ferme après cinq minutes ; cela n’expire pas le mot de passe. Changement dans le profil recommandé, pas imposé à la première connexion. Le presse-papiers copié volontairement reste sous le contrôle de l’utilisateur.

### Sections retirées uniquement Admin / Responsable Hub
Sécurité & sessions et Contacts support retirés de la navigation et leurs raccourcis retirés du profil/des fiches. Les protections de sécurité, expirations et journaux restent actifs. Les contacts existants ne sont pas effacés. Les autres rôles restent inchangés.

### Nombre d’éléments par page
Choix 10, 20, 30, 50, 80, 100, 200 ou 500, mémorisé par compte dans le navigateur. Exemple : 123 commandes avec 50 par page = 50 / 50 / 23.
Colis, suivi Support, factures, relevés, imports, palettes et tableaux généraux non déjà paginés. Palettes/retours/factures transmettent la taille au serveur ; les autres tableaux affichent les données renvoyées par leur API. Les plafonds historiques des vues ne sont pas supprimés.
Les formulaires éditables, fenêtres de scan/confirmation, statistiques, aperçus courts et documents d’impression ne sont pas transformés en listes exhaustives. La taille de page ne change pas les limites d’opérations, dont les palettes limitées à 100 colis.

### Commandes : dernier état modifié en premier
Tri par dernier changement réel de statut avant pagination, y compris interface Livreur, liste des commandes ramassées et dossier livreur Hub. Une simple note ou modification de prix ne fait pas remonter une commande. Repli sur la création si l’horodatage de statut est absent ; identifiant décroissant à date égale.
Après actualisation, la détection d’un changement de statut dans les commandes déjà chargées ramène les listes Colis / Support à la première page. Les filtres et périmètres sont conservés. Pas de nouveau rafraîchissement temps réel entre appareils.

### Numéros à risque
AUCUNE modification du calcul ni des badges : conservés tels quels, conformément à la dernière décision.

## Vérifications
- 175 tests Python relancés avec succès sur la source correspondant exactement aux fichiers du ZIP.
- Tests Node de retrait des sections et de tri des commandes relancés avec succès.
- Lors des étapes précédentes : Chromium pagination 50 / 50 / 23, démarrage complet Colis/Facturation, fenêtre de mots de passe, sélection par destination, scénarios d’envoi/réception au scan.
- Les fichiers cumulés ont été comparés aux sources finales : aucune différence.

Après déploiement, vérifier connexion, création/réinitialisation d’un compte de test, menus Admin/Hub, taille de page, tri après changement réel de statut et envoi/réception d’une palette de test.

## Déploiement
Cette livraison est un ZIP préparé et testé localement. Aucun push GitHub ni déploiement Railway n’a été exécuté pour ce paquet. Le fonctionnement du matériel caméra et des services externes en production n’est pas certifié par ces tests.
