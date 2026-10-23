# Réceptions unifiées — collecte puis validation finale

Branche : `feature/hub-manager-ramassage-palettes` du dépôt oriental24h-sys/oriental24.
Base distante vérifiée : `6906a02`.

## Écrans couverts
- Réception des transferts inter-hubs, y compris les trajets de retour Central/origine.
- Palettes Société : Admin et Responsable du Hub destinataire.
- Ramassages Vendeur : interface de collecte livrée précédemment, conservée.
- Palettes retour au vendeur : comptes autorisés par les règles existantes, dont le vendeur propriétaire.
- Packs Fusion et réception tardive d'un colis précédemment déclaré manquant.
- Entrées depuis les listes, la console Palettes et les fiches : même écran de collecte. La fiche détaillée et les incidents restent accessibles sans formulaire de réception unitaire.

Cette mise à jour concerne les réceptions physiques de colis/documents. Les encaissements COD, factures et remises d'argent ne sont pas des réceptions de colis et ne sont pas modifiés. Le mode démonstration HTML autonome hors serveur n'est pas le déploiement cible : la réception unifiée exige le serveur connecté.

## Fonctionnement
Compteur, liste des scans, clavier/lecteur USB, caméra sur appareil compatible, son activé/coupé, retrait d'un scan, remise à zéro et bouton final.

**Aucune écriture de réception pendant la collecte.** La validation finale exige tous les colis encore attendus du manifeste. Un colis déjà reçu n'est pas exigé à nouveau. Les lignes officiellement retirées du manifeste ou déclarées manquantes restent dans le circuit d'incident ; elles ne sont jamais reçues automatiquement.

- Ajout : son de succès.
- Répétition : son grave et « DOUBLE — commande déjà scannée / réceptionnée », compteur inchangé.
- Erreur : trois bips courts, sans ajout.
- Transfert : les scans de sortie restent obligatoires. Les colis non partis sont indiqués « Départ non scanné » ; attendre les départs puis rouvrir/actualiser avant validation.
- Un changement de manifeste/commande pendant la collecte provoque un refus : rouvrir et contrôler les scans.
- Un échec annule toute la transaction. Une réponse réseau perdue peut être réessayée avec la même confirmation sans doubler les réceptions ou événements.
- Retours : statuts et montants suivent les règles existantes ; aucun paiement automatique.
- Le Hub ne reçoit pas les informations personnelles des colis qui ne sont pas encore physiquement chez lui : le manifeste de scan fournit les références nécessaires, pas leurs coordonnées.

## Installation
Ce ZIP contient seulement les fichiers modifiés/ajoutés depuis la base distante indiquée. Il inclut les dernières modifications : **Les CMD ramassées**, les sons DOUBLE, la collecte ramassages et le titre **Bon d’envoi · transfert inter-hubs**.

1. Sauvegarder la base persistante et vérifier la branche. Si des changements ont été ajoutés après `6906a02`, fusionner les modifications au lieu de les écraser.
2. Copier **tous** les fichiers à leurs chemins. Ne pas mettre les JS/CSS à la racine : ils vont dans `static/`.
3. Nouveaux fichiers de production indispensables : `reception_collection.py`, `ramassage_tracking.py`, `static/reception-collection.js`.
4. Redéployer/redémarrer le serveur. Les tables techniques additives sont créées automatiquement (`reception_collection_keys`, ainsi que les tables de suivi de ramassage si elles n'existent pas).
5. Recharger les navigateurs. Les versions des scripts modifiés sont incrémentées.
6. Tester un transfert, une palette Société, un ramassage et un retour avec leurs comptes autorisés. Vérifier que les scans seuls ne changent pas les statuts et que le bouton final le fait en une seule transaction.

Aucune base de données, clé, donnée de test ni dépendance installée n'est incluse. Les anciens endpoints unitaires restent compatibles ; les interfaces de production utilisent désormais les validations de collecte.

## Vérifications locales
- **155 tests Python réussis**, dont les transferts et retours réels via Flask/SQLite, les autorisations, snapshots périmés, transactions annulées, clés de répétition, Fusion, réception tardive et notifications non dupliquées.
- Chromium : 7 parcours de la nouvelle interface (transfert Admin/Hub, Société Admin/Hub, retour Vendeur/Hub, Fusion Hub), avec clavier, doublon, son/silence, retrait/reset, mobile, validation et reprise après réponse réseau perdue.
- Régressions Chromium des ramassages et de « Les CMD ramassées » réussies.
- Démarrage complet de l'application vérifié avec une base de test isolée ; accès anonyme refusé (401).
- Caméra : callback simulé dans les tests. Vérifier permissions et lecture réelle sur le téléphone en HTTPS.

```
python -m unittest discover -s tests
node tests/js/test_reception_double.cjs
python tests/browser/test_unified_reception.py
python tests/browser/test_ramassage_collect.py
python tests/browser/test_collected_orders.py
```
Les tests navigateur requièrent Playwright + Chromium, uniquement pour les tests.

**Préparé et testé localement. Aucun push GitHub ni déploiement Railway effectué.**
