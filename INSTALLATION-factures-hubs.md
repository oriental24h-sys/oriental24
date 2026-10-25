# Nouveau — modèle PDF unifié

Les factures clients, livreurs et nouvelles factures de commission des Hubs utilisent le même moteur PDF A4 : logo ORIENTAL24, émetteur en haut à droite, numéro/date/destinataire, récapitulatif par statut et tarif exact, COD livré/frais/net, détail des colis, mentions disponibles et numéros de page.

Le modèle s’inspire du PDF fourni, sans copier les données d’Olivraison, ses identifiants légaux ni son délai de paiement de 15 jours. Les soldes et avertissements nécessaires restent propres à chaque registre ; aucun montant n’est recalculé à partir de la facture d’exemple. Les CSV restent inchangés.

**Émetteur :** les prochaines factures livreurs créées par un responsable portent le nom, l’adresse et la ville de son Hub. Aucun ICE/RC/IF de la société n’est attribué au Hub. Les informations absentes ne sont pas inventées. Les factures créées par Admin utilisent le profil ORIENTAL24 existant. Le destinataire est le client, le livreur ou le Hub concerné.

L’identité des nouvelles factures livreurs et Hubs est archivée à l’émission. Les anciennes identités archivées ne sont pas réécrites. Les anciennes factures Hubs sans snapshot d’identité utilisent uniquement leur nom de Hub déjà figé et la marque ORIENTAL24, sans inventer d’adresse historique. Les factures clients conservent la politique existante de coordonnées entreprise actuelles.

Les boutons Imprimer des factures clients, livreurs et Hubs utilisent désormais le même PDF que le téléchargement. Selon le navigateur, si l’impression PDF intégrée est bloquée, télécharger le PDF puis l’imprimer avec le lecteur PDF. La version HTML hors ligne conserve son ancien rendu ; cette modification vise l’application serveur.

Les anciens registres COD historiques ne sont pas convertis dans ce nouveau modèle de commission Hub.

**Contrôle :** 150 tests Python et le test JavaScript réussis. Test PDF de 70 colis : toutes les lignes apparaissent une seule fois, tableaux répartis sur plusieurs pages avec pagination et mentions. Exemple fictif fourni séparément ; aucun client réel dans cet exemple. Pas de déploiement ni test d’impression dans un navigateur réel.

---

# ORIENTAL24 — Factures et barèmes des Hubs

## Installation

Ce ZIP contient uniquement les fichiers concernés par cette modification, et non le projet complet. Il s’applique à la version comprenant les modifications précédemment livrées (barèmes livreurs du responsable Hub, réception/départ et compteurs).

1. Sauvegarder le code actuel et la base SQLite.
2. Copier les fichiers du ZIP à la racine du projet, en conservant leurs chemins. `hub_billing.py` et `static/hub-billing.js` sont de nouveaux fichiers indispensables.
3. Redémarrer le service Python / redéployer. Les nouvelles tables sont créées automatiquement. Aucune suppression des anciennes factures, commandes ou écritures financières.
4. Recharger le navigateur sans cache.

Aucune dépendance Python supplémentaire. Pas de modification de `render.yaml` et pas de deuxième worker Render : le moteur utilise la base SQLite du service web existant.

## Responsable Hub

Menu **Factures** :
- **Mes factures** : uniquement les factures de commission émises par Admin pour son propre Hub ; détail, téléchargement PDF, impression du même PDF et CSV.
- **Factures livreurs** : relevés des livreurs du Hub ; les fonctions déjà livrées de création/configuration restent dans **Livreurs de mon Hub → Facture**.
- Aucun onglet « Paiements vendeurs » ni factures clients dans cet espace. Les fonctions Admin de paiement vendeur sont inchangées.
- Les anciennes factures COD restent consultables via le bouton dédié ; leur registre n’est ni supprimé ni converti.

## Nouveau : factures livreurs chez le responsable Hub

Dans **Factures → Factures livreurs**, le responsable dispose désormais du tableau de facturation : référence, livreur, état, COD, montant net, soldes à recevoir/verser, mise à jour et documents. Filtres, recherche, pagination, PDF et CSV par facture ou export CSV de la liste.

Il peut ouvrir le détail, imprimer et télécharger les documents des seuls relevés de son Hub. Les factures Paid restent dans l’historique.

Selon l’autorisation confirmée pour cette modification, il peut désormais :
- enregistrer une remise COD ou une commission réellement réglée (paiement partiel) ;
- passer à Paid après confirmation des flux réels, référence et date ;
- revenir à Not Paid avec un motif obligatoire : les déclarations actives sont annulées avec trace, sans remboursement automatique ni suppression de l’historique.

Les soldes déterminent le statut. Une relance du même règlement ne le duplique pas ; une version de solde obsolète est refusée. Chaque écriture conserve le responsable auteur. Aucun accès aux factures clients, aux paiements vendeurs ou aux relevés hors Hub. Un Hub inactif est bloqué. Un relevé contenant des lignes attribuées à un autre Hub est exclu de la liste et refusé en accès direct. L’annulation du relevé lui-même reste réservée à Admin.

Cette autorisation concerne uniquement les factures **livreurs**, pas les nouvelles factures de commission **des Hubs**, qui restent des documents sans enregistrement de paiement dans ce module.

## Configuration Admin

L’accès Admin est désormais intégré à la section Facturation, dans un onglet commun. L’entrée séparée Factures des Hubs est masquée chez Admin. L’espace responsable Hub reste inchangé.

Dans **Facturation → Factures des Hubs**, à côté de **Factures clients**, **Factures livreurs** et **Paiements vendeurs** :
1. **Barèmes des Hubs** : configurer chaque Hub actif avec ses commissions par commande **Livré / Retourné / Refusé** en MAD. Saisir explicitement zéro pour un état non rémunéré. Aucun tarif par défaut n’est inventé.
2. Choisir la méthode :
   - **Net** : commission retenue sur le COD livré, jusqu’à concurrence du COD ; l’éventuel complément de commission est affiché séparément.
   - **Intégral** : COD à remettre et commissions à verser sont séparés.
3. **Génération automatique** : sélectionner l’heure souhaitée, activer et enregistrer. L’heure est interprétée dans **Africa/Casablanca**, indépendamment du fuseau du navigateur. Aucun horaire n’est imposé : la planification est désactivée initialement et Admin l’active à l’heure qu’il choisit.
4. Contrôler la prochaine exécution et le compte rendu du dernier passage. Une prévisualisation / génération immédiate est également disponible.

## Règles financières et attribution

- Une facture par Hub ayant un barème, un Hub actif et au moins une commande éligible non encore facturée, à chaque passage. Pas de facture vide.
- Les commandes prises en compte sont celles actuellement Livré / Retourné / Refusé, clôturées avant l’heure limite. Le premier passage peut inclure l’historique éligible non encore facturé dans ce nouveau registre : vérifier avec la prévisualisation avant activation.
- COD uniquement pour Livré ; Retourné / Refusé contribuent à la commission, pas à un encaissement fictif.
- Attribution par Hub enregistré lors de la tentative de clôture, sinon par affectation du livreur, comme dans la finance livreurs. Ni ville de destination ni localisation physique ne suffisent. Les commandes sans preuve d’attribution ou sans Hub actif sont signalées et ignorées ; les Hubs sans barème sont également signalés.
- Chaque commande ne peut figurer qu’une seule fois dans ce registre. Les relances, générations manuelles et passages simultanés ne la refacturent pas.
- Les montants, statuts facturés et noms de Hub sont figés à l’émission. Modifier ensuite un barème ne recalcule pas les documents existants. Les changements de barème et de planning sont journalisés.
- Ce sont des relevés internes de commission, distincts des anciennes factures COD, des factures clients et des relevés livreurs. Ne pas additionner les deux registres comme deux créances COD distinctes pour une même opération.
- Aucun paiement, rapprochement, virement ou statut Paid n’est créé automatiquement. Ces documents ne constituent pas une attestation de règlement ni une facture fiscale.

## Fonctionnement du moteur quotidien

- En production (`PRODUCTION_MODE`), le moteur démarre automatiquement dans le service web et contrôle le planning toutes les 30 secondes. Il fonctionne sans navigateur ouvert. L’exécution peut donc avoir quelques secondes de décalage et dépend de la disponibilité du service.
- Le service doit rester actif, avec sa base SQLite persistante. Le déploiement Render Starter existant convient ; un service dormant ne garantit pas l’heure demandée.
- Le prochain passage est conservé en base. Après une interruption, les échéances en retard sont traitées au redémarrage, une échéance par contrôle. La déduplication reste applicable.
- `ORIENTAL24_HUB_BILLING_SCHEDULER=0` désactive explicitement le moteur ; `=1` l’active, y compris en démo. Redémarrer après changement. En démo, le moteur est désactivé par défaut et l’interface le signale.
- Si l’Admin ayant enregistré le planning devient inactif, les générations sont bloquées et un autre Admin actif doit réenregistrer le planning.

## Vérifications locales

150 tests Python réussis, dont les accès réels/CSRF, cloisonnement Hub, trois commissions, versions figées, absence de double facturation, concurrence du moteur, contrôle de l’heure, reprise des échéances, rejet des prévisualisations obsolètes et préservation des registres COD/livreurs.

Test JavaScript de la nouvelle interface réussi ; vérification syntaxique des scripts et `git diff --check` réussis. Pas de validation visuelle dans un navigateur réel, ni déploiement effectué.

Commande Python :

```sh
PYTHONPATH=.:tests python -m unittest tests.test_hub_billing tests.test_hub_driver_workspace tests.test_hub_access tests.test_reception_collection tests.test_dispatch_collection tests.test_hub_palette_flow tests.test_hub_invoices tests.test_hub_cod tests.test_sidebar_counts -q
```

Commande JavaScript : `node tests/frontend/test_hub_billing.cjs`.
