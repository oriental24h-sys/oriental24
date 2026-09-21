# ORIENTAL24 — Plateforme de livraison

Version **1.4.17** fonctionnelle de démonstration, réalisée à partir des captures de référence et du logo fourni. Identité bleu nuit / orange. Interface en français, adaptée au mobile. **Cette version n’est pas un déploiement commercial validé.**

## Version 1.4.17 — audit pilotage : refus tracés et dialogues sans 409 « aléatoires »

**[Guide](GUIDE-v1.4.17.md).** Audit complet sans raccourci : tout refus de **« Réception du colis »** — client, livreur ou agent d'un autre hub — est désormais enregistré dans l'historique avec **qui** (`actor_role`, `actor_hub_id`) et **pourquoi** (`Réception refusée` + motif exact), sans fuite d'existence pour un agent hors hub et révocation immédiate du compte désactivé. Les 409 « de nulle part » des dialogues sont secourus : `api409` relit la fiche, remonte la version à jour et **rejoue une fois** l'intention déclarée (21 dialogues) ; à un conflit de **réception en masse**, la liste se recharge pour re-contrôler les colis réellement restants — jamais de rejeu aveugle. `static/pilotage.css` confirmé en fichier unique (serveur + build autonome). **244 tests**, parcours navigateur dédiés et régressions, **zéro test ignoré**, HTML autonome régénéré.

## Version 1.4.16 — réception renforcée et intégrations

**[Guide](GUIDE-v1.4.16.md).** Réception renforcée et intégrations — sept chantiers : incidents de réception (manquant sans fausse réception, endommagé avec photo obligatoire et affectation suspendue jusqu'à décision, imprévu sans mutation ; réponse de la société et décision Admin avec historique partagé ; clôture **avec écarts**, jamais comme entièrement reçue) · tarifs par client et ville appliqués aux seuls nouveaux colis (audit complet, zéro rétroactivité) · scan caméra optionnel à la réception (remplit le code, confirmation obligatoire) · unicité du tracking par **société+tracking** avec désambiguïsation 409· rôle **Agent réception** borné à un hub (reçoit les palettes de son hub, alertes, pas de vue sur colis/finance, audit nominal) · rubrique **Alertes** de retard avec seuils réglables · **API partenaire** Bearer avec clés révocables, idempotence stricte et accès borné à la propre société. **239 tests API**, parcours navigateur dédiés, régressions palettes v1.4.15 et HTML autonome. Aucun envoi externe ni fausse intégration.

## Version 1.4.15 — palettes partenaires et réception ORIENTAL24

**[Guide](RELEASE-NOTES.md).** Les sociétés préparent un manifeste de leurs commandes, sélectionnent un hub puis confirment l’envoi. Admin réceptionne par tracking original ou confirme tous les restants après contrôle physique. Réception partielle, manquants visibles, déverrouillage des seuls colis reçus pour la suite de livraison, historique, manifeste imprimable/PDF et CSV. Les anciens registres et transferts restent distincts. **229 tests API**, parcours société/Admin/mobile/HTML, rejeu après perte de réponse et régressions validés. **54 tables métier existantes inchangées à la migration**. Aucun tracking, COD, frais ni journal financier modifié par la réception. Le HTML simule désormais aussi ce circuit ; il ne synchronise pas le serveur.

## Version 1.4.14 — deux types de clients et tracking partenaire

**[Guide](RELEASE-NOTES.md).** À la création d’un client : **Vendeur** (tracking ORIENTAL24 automatique) ou **Société de livraison** (son propre tracking obligatoire, conservé dans le suivi, les scans, les étiquettes et les factures). Saisie, import Excel/CSV et préparation stock cohérents ; doublons globaux insensibles à la casse, contrôles transactionnels et accès client inchangés. Migration additive, anciens comptes Vendeur, aucun ancien colis renommé. **211 tests API** et parcours navigateur/mobile/HTML validés. Les calculs et factures ne changent pas. **Le nouveau circuit palettes société → réception ORIENTAL24 reste à implémenter séparément.**

## Version 1.4.13 — Facture Client : même structure visuelle que Livreur

**[Guide](RELEASE-NOTES.md).** Le bouton client **Imprimer / PDF** réutilise désormais le modèle A4 livreur : logo, identité, récapitulatif par statut/tarif, COD/frais/net, détail des colis et pages numérotées. **Changement de présentation uniquement** : frais client, net, journaux, Paid et visibilité inchangés ; aucune commission ou condition livreur copiée. Serveur et HTML autonome validés, 64 colis fictifs sur 4 pages, **194 tests API réussis**. Modules comptables et PDF direct serveur identiques à v1.4.12.

## Version 1.4.12 — Facturation Clients / Livreurs et Paid

**[Guide](RELEASE-NOTES.md).** Une page Facturation avec onglets Clients/Livreurs, filtres, pagination, statuts **Not Paid / Partiel / Paid** modifiables par Admin via règlements réels déclarés. Paid retire les colis des listes de service du livreur, mais conserve sa facture dans Archives Paid ; côté client, facture et colis restent visibles. Correction motivée réversible sans suppression. **Vrais téléchargements PDF et CSV**, accès par compte, PDF A4 avec polices embarquées. Simulation HTML correspondante (PDF via impression locale). **194 tests API**, parcours multi-comptes/mobile/HTML, PDFs longs et régressions validés. L’actualisation de fond ne prolonge pas la session inactive. Installer les dépendances actualisées avant redémarrage.

## Version 1.4.11 — modèle de facture livreur A4

**[Guide](RELEASE-NOTES.md).** Mise en page inspirée du PDF fourni : logo ORIENTAL24, coordonnées configurables, numéro/date/livreur, prestations par statut et tarif exact, COD / frais / net, liste des colis avec téléphone, pages A4 numérotées et entêtes répétés. Coordonnées et COD nominal archivés à l’émission ; pas de données du concurrent, de tarifs ni d’échéance imposés. Ancien relevé sans coordonnées : valeurs manquantes explicites. Le document reste un relevé interne, pas une facture fiscale. **179 tests API**, PDF de 250 colis fictifs, stress de 500 lignes et régressions validés. HTML autonome mis à jour.

## Version 1.4.10 — bouton Facture livreur

**[Guide](RELEASE-NOTES.md).** Bouton **$ jaune** entre informations et blacklist, confirmation **Facture** avec le nom et les montants du livreur, **Accepter** rouge puis détail et **Imprimer / PDF**. Réutilise les relevés internes existants : pas de doublon de facturation, pas de tarif inventé ni de paiement automatique. Aperçu/annulation, contrôle des modifications, reprise après réponse perdue, mobile et HTML local validés. **173 tests API**, parcours dédié et quatre régressions navigateur réussis. Aucune nouvelle table.

## Version 1.4.9 — actions Livreurs et cycle matin/soir

**[Guide](RELEASE-NOTES.md).** Fiche du livreur à droite, blacklist réversible avec sessions révoquées, remise des colis le matin, récupération des non-livrés le soir, archivage sans suppression. Scan/saisie → vérification → confirmation physique, état Reçu par le livreur au départ ; les Livrés restent associés, les autres quittent la tournée après récupération. Refus/retours conservent leur attribution financière et commissions. Règlement historique Admin possible après blocage/archive. **173 tests API**, parcours navigateur/mobile/HTML et régressions validés. Caméra selon support/permission du navigateur ; HTML en simulation locale.

## Version 1.4.8 — barre au survol et annonces

**[Guide](RELEASE-NOTES.md).** Barre latérale compacte avec icônes, expansion automatique au passage de la souris et repli à sa sortie : **aucun bouton de pliage sur ordinateur**. Navigation clavier et menu tactile conservés. Annonces et liens au-dessus des pages, bandeau ORIENTAL24, gestion Admin par audience/ordre/publication, brouillons privés et révisions. Modèle Excel serveur réellement actualisé ; HTML local honnête sur cette limite. **161 tests API**, parcours dédié et régressions navigateur validés. Aucune annonce commerciale de la référence publiée automatiquement.

## Version 1.4.7 — réclamation depuis la ligne commande

**[Guide](RELEASE-NOTES.md).** Bouton circulaire après le crayon ouvrant « Créer une réclamation » : sujet, catégorie, colis fixe, description et pièces jointes PDF/JPG/PNG (3 fichiers, 1 Mo total). Ticket lié, création atomique, reprise idempotente, téléchargements privés auteur/Admin. Droits de commande revérifiés ; aucun changement des données du colis, même facturé. Mobile et HTML local mis à jour ; HTML sans envoi au support. **154 tests API**, parcours navigateur dédié et régressions validés. Aucun antivirus garanti.

## Version 1.4.6 — modifier la ville, Admin seulement

**[Guide](RELEASE-NOTES.md).** Crayon circulaire à droite de chaque ligne et panneau latéral « Modifier la ville », avec ville présélectionnée, Annuler/Enregistrer et adaptation mobile. Mutation Admin+CSRF, transaction et révision ; couverture relue, historique ancienne/nouvelle ville, verrous financiers/logistiques et colis clôturés respectés. Adresse, livreur, état, COD et frais enregistrés restent inchangés. Simulation HTML correspondante. **147 tests API**, parcours dédié et régressions navigateur validés.

## Version 1.4.5 — copier une commande

**[Guide](RELEASE-NOTES.md).** Icône de copie avant le nom du destinataire dans la ligne, le détail et les cartes mobiles. Copie de huit informations utiles depuis la fiche autorisée relue au clic. Aucun changement métier ; pas d’annuaire ni de données internes copiés. Confirmation de succès réelle, et texte sélectionnable si le navigateur/iframe bloque le presse-papiers. Disponible aussi dans le HTML local. 139 tests API et parcours navigateur de copie/régressions validés.

## Version 1.4.4 — catalogue d’états validé

**[Guide des états](RELEASE-NOTES.md).** Ajout de Transit, Reporté, Réceptionné, Reçu par le livreur et Intéressé ; les huit anciens états restent disponibles, soit 13 au total. Transitions centralisées, distinction réception agence / prise en charge livreur / livraison finale, report sans rendez-vous, programme avec date, synchronisation des nouveaux départs/réceptions de transfert. Les nouveaux états restent exclus des relevés financiers clôturés et du COD livré. Pas de faux accusé de réception lors d’une réaffectation. Filtres, historique, HTML et mobile mis à jour ; **139 tests API** et parcours navigateur/régressions réussis.

## Version 1.4.3 — liste déroulante de changement d’état

**[Guide](RELEASE-NOTES.md).** La valeur de l’état dans la ligne ouvre désormais une vraie liste déroulante, à côté de Note. Étapes simples enregistrées directement ; programmation, clôture et correction administrative confirmées dans la liste elle-même. Tentatives Livreur, COD exact, verrous et versions restent appliqués. Cartes mobiles et HTML mis à jour. Les états métier restent ceux d’ORIENTAL24 ; aucun nouveau statut financier n’est déduit de la capture. 130 tests API et parcours navigateur/régressions validés.

## Version 1.4.2 — état et menu Note

**[Guide rapide](RELEASE-NOTES.md).** Boutons Statut et Note directement dans la ligne, motifs recherchables et configurables par Admin, affichage du motif courant, filtre et export enrichi. Le motif est distinct du statut : aucun rendez-vous, retour physique ou changement financier implicite. Historique daté, version contre les écrasements concurrents, portée du livreur et verrous conservés. Les clients consultent sans modifier. HTML : même menu en simulation locale, sans sécurité ni synchronisation serveur.

**130 tests API réussis**, parcours Note desktop/mobile/HTML et régressions des modules précédents validés.

## Version 1.4.1 — détail commande et contacts actuels

**[Guide rapide](RELEASE-NOTES.md).** Flèche pour déplier la commande sous sa ligne, ou référence pour ouvrir le détail. Informations à gauche, chronologie à droite, nom/téléphone du livreur actuellement affecté et contact Support par commande. Numéros cliquables, états manquants/inactifs explicites et bouton Actualiser. L’Admin gère les contacts Support professionnels et leur affectation ; ce ne sont pas de nouveaux comptes de connexion. Aucune donnée Support n’est préremplie.

Lecture des coordonnées via l’API détail autorisée, sans exposer l’annuaire aux autres rôles. Les affectations Support ne modifient ni tarifs, ni statuts, ni dates financières. **122 tests API** et parcours navigateur/mobiles/régressions validés. Le HTML montre le nouveau détail avec ses livreurs fictifs ; la gestion Support nécessite le serveur. Ce n’est pas du temps réel ni une intégration téléphonique.

## Version 1.4 — sessions et préparation d’exploitation

**Nouveau guide : [GUIDE-v1.4.md](RELEASE-NOTES.md).** Sessions révocables côté serveur, expiration par inactivité et durée absolue, fermeture des autres sessions, rotation après changement de mot de passe et révocation après désactivation/reset administratif. Historique privé des connexions, réseau masqué, contrôle d’origine et limites de tentatives partagées entre workers.

Le mode explicite `ORIENTAL24_MODE=production` refuse les bases demo, n’ajoute aucun compte/colis/ville fictif, exige une clé indépendante, une base privée séparée, des hôtes autorisés et HTTPS ; inscription publique fermée par défaut. **L’aperçu reste en mode démo. Le mode production n’est pas une certification de sécurité.**

`manage.py` fournit initialisation du premier Admin, reset local de mot de passe, sauvegarde cohérente, contrôle d’intégrité, restauration vers un nouveau fichier avec révocation des sessions et nettoyage explicite des traces. Mots de passe saisis au terminal, jamais dans les arguments ; sauvegardes privées mais non chiffrées.

**115 tests automatisés** et régressions navigateur validés. Reconnexion obligatoire après mise à jour depuis une version sans sessions serveur. Voir les limites, variables et procédures dans le guide 1.4 ; `.env.production.example` n’est pas chargé automatiquement.

## Version 1.3 — workflows issus de la revue Olivraison

**Guide de prise en main et matrice de couverture : [GUIDE-v1.3.md](RELEASE-NOTES.md).**

Ajouts serveur : motifs et rendez-vous structurés ; tentatives historisées ; hubs ; documents ramassage/retour/transfert avec colis rattachés et réceptions partielles ; affectation groupée transactionnelle ; analyses historiques livreurs/hubs et CSV ; tickets liés et notifications internes ; commandes de stock avec réservation/préparation/retour contrôlé et analyse produits ; règlements clients partiels en centimes ; dossiers privés de comptes et revue administrative.

Aucun hub fictif ni barème de commission n’est activé automatiquement. L’historique opérationnel commence à la migration, sans reconstitution inventée. Les 91 tests API et les parcours navigateur vérifient ce périmètre ; ils ne constituent pas un audit de production.

**Les nouveaux modules nécessitent le serveur. Le HTML autonome conserve une simulation limitée des anciens parcours.** Google, WhatsApp, SMTP et la banque restent explicitement non connectés. Préparation/retour partiels de produits, inventaire par emplacement, KYC officiel, applications natives, GPS et POD signé/photographié ne sont pas fournis. Les PDF déposés n’ont pas d’analyse antivirus : documents fictifs seulement.

## Historique : révision UX après audit Olivraison — 20 septembre 2026

Sur le socle 1.2, une révision d’interface ajoute :
- Files opérationnelles cliquables du dashboard, adaptées au rôle.
- Correction de l’onglet « Tous les colis » et de la remise à zéro de la pagination.
- Filtres combinables par date de création, statut, ville, client, livreur actuel et facturation/rapprochement.
- Filtres actifs retirables, recherche tolérante aux accents et bouton d’actualisation.
- Export CSV de **tous les résultats filtrés**, sur plusieurs pages, avec neutralisation des formules.

`static/pilotage.js` et `static/pilotage.css` sont chargés après les modules précédents. La révision UX seule ne modifiait aucun schéma, tarif ou calcul financier ; la version 1.3 ajoute les modules et migrations décrits dans [RELEASE-NOTES.md](RELEASE-NOTES.md) (historique complet).

Le code de `offline/` génère une **simulation HTML autonome**, distincte du serveur :

```bash
python offline/build_html.py
```

Le fichier `ORIENTAL24-demo.html` est écrit dans le dossier parent du projet. Il contient uniquement une base fictive fraîche, les images et les scripts intégrés. Les modifications sont enregistrées dans le stockage local si le navigateur l’autorise, sinon en mémoire dans l’onglet. Ce HTML n’est pas une authentification sécurisée et ne synchronise rien avec le serveur. Import Excel/CSV, caméra et génération des codes des nouveaux colis nécessitent le serveur ; les codes des 48 colis initiaux sont intégrés.

Tests complémentaires : `python qa/pilotage_check.py` (serveur isolé + HTML) et `python qa/offline_html_check.py` (HTML, stockage local et iframe à origine opaque). Générer le HTML avant ces tests.

## Démarrer

Prérequis : Python 3.11 ou supérieur.

```bash
cd oriental24
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Ouvrir `http://localhost:3000`. Le serveur écoute sur `0.0.0.0` et utilise des URL relatives, compatibles avec un aperçu proxifié.

Pour le serveur WSGI de démonstration sous Linux :

```bash
gunicorn --bind 0.0.0.0:3000 --workers 1 --threads 4 --timeout 60 app:app
```

**Déploiement production sur Render** : blueprint `render.yaml` + `Procfile` + `/healthz` prêts — voir **[GUIDE-DEPLOIEMENT-RENDER.md](GUIDE-DEPLOIEMENT-RENDER.md)** (étapes, variables auto, création du premier Admin, limites du plan).

La base SQLite `oriental24.sqlite` est créée automatiquement lors du premier lancement, avec des données fictives. Les modifications restent enregistrées après rechargement et redémarrage. Les fichiers du logo sont locaux : aucune API externe ni CDN n’est nécessaire pour afficher le site.

## Comptes de démonstration

Sur la page de connexion, les boutons **Admin**, **Client** et **Livreur** permettent d’ouvrir directement chaque espace.

| Rôle | E-mail | Mot de passe |
|---|---|---|
| Administrateur | admin@oriental24.ma | Oriental24!Demo |
| Client | client@oriental24.ma | Oriental24!Demo |
| Livreur | livreur@oriental24.ma | Oriental24!Demo |

Ces accès sont publics et réservés à la démonstration. Ne saisissez pas de données personnelles réelles. Les autres noms, téléphones, adresses, montants et colis préchargés sont fictifs.

## Couverture géographique : le réglage central

**Admin → Paramètres → Villes & couverture**

- Ajouter une ville dans n’importe quelle région du Maroc, sans modifier le code.
- Modifier son nom, sa région, ses frais de livraison et ses frais de retour.
- Activer ou désactiver **indépendamment** livraison et ramassage.
- Seules les villes actives en livraison apparaissent dans le formulaire de colis et sur le site public.
- Seules les villes actives en ramassage sont proposées dans les demandes de ramassage.
- Les frais sont copiés sur le colis à sa création : modifier une ville ne recalcule pas l’historique.
- Une ville désactivée conserve ses colis existants et leur suivi.

**Les huit villes de l’Oriental et les tarifs préchargés sont des exemples à valider, pas une affirmation de couverture réelle.** Les délais ne sont pas garantis par l’interface.

## Fonctions opérationnelles incluses

### Site public
- Landing page ORIENTAL24 utilisant votre logo, vos couleurs et l’illustration du véhicule extraite de votre logo.
- Services, FAQ, couverture et tarifs issus de la base de données.
- Création de compte client et connexion.

### Administration
- Tableau de bord et statistiques calculées à partir des colis enregistrés.
- Création de colis pour un client, recherche, filtres par ville / statut, pagination, export CSV.
- Affectation à un livreur, changement de statut et historique daté avec auteur.
- Création / modification / désactivation des comptes client et livreur.
- Gestion des villes, tarifs, couverture et annonce du tableau de bord.
- Traitement des demandes de prix avec historique.
- Demandes de ramassage et mise à jour de leur statut.
- Palettes simplifiées : création d’un transfert et confirmation de réception.
- Produits et mouvements de stock avec contrôle empêchant un stock négatif.
- Demandes client d’entrée/sortie de stock, approbation transactionnelle par admin, refus et annulation.
- Réclamations, échanges et résolution.
- Génération de relevés client, détail des frais, impression et enregistrement manuel des règlements.
- Barèmes de commission par livreur et ville, relevés livreurs, caisse COD, paiements partiels et journal des corrections.

### Client
- Accès uniquement à ses propres colis, demandes, factures, produits et réclamations.
- Ajout de colis, suivi détaillé, demande de changement de prix avant clôture.
- Demande de ramassage dans une ville disponible.
- Consultation de stock, création de fiches produit et demandes d’entrée/sortie ; validation des mouvements physiques réservée à l’administration.
- Impression d’étiquettes QR / Code 128, import Excel/CSV avec prévisualisation et export CSV.

### Livreur
- Accès uniquement aux colis qui lui sont affectés.
- Mise à jour des statuts selon un parcours autorisé.
- Vue mobile avec cartes de livraison et bouton d’appel.
- Tableau de bord des colis et du COD collecté, réclamations, demandes de prix et profil.
- Consultation de sa caisse, de ses commissions, de ses relevés et de leurs règlements ; impression/PDF et export CSV. Écritures réservées à l’administration.

### Profil & sessions
- Modification des coordonnées.
- Changement de mot de passe avec vérification du mot de passe actuel.
- Mots de passe hachés, sessions signées, jeton CSRF pour les mutations authentifiées.
- Contrôles de rôle et de périmètre côté serveur ; comptes désactivés bloqués.

## Règles de facturation de cette version

Les relevés regroupent les colis **Livré**, **Retourné** ou **Refusé** non encore facturés, pour un client donné.

- COD = somme des montants des colis livrés uniquement.
- Frais = frais de livraison pour les colis livrés + frais de retour pour les colis retournés/refusés.
- Net = COD − frais. Un net négatif correspond à une somme due par le client.
- Un colis facturé est verrouillé pour les changements de statut, affectation et prix.
- La génération est transactionnelle et évite d’inclure deux fois les mêmes colis.
- « Enregistrer le règlement » est une confirmation manuelle ; aucun virement n’est exécuté.

**Cette convention de frais est une hypothèse métier à confirmer avec ORIENTAL24.** Les relevés imprimés sont des documents de démonstration, sans coordonnées légales ni fiscales complètes. Les commissions et relevés livreurs sont traités séparément dans **Caisse livreurs** (voir ci-dessous) ; ce ne sont pas des factures fiscales.

## Nouveautés 1.2 — caisse & commissions livreurs

**Admin → Caisse livreurs → Barèmes & méthodes** (raccourci également dans Paramètres).

### 1. Configurer les règles

Aucune commission ni méthode de règlement n’est préchargée. Pour chaque livreur, choisir explicitement :
- La commission par colis **Livré**, **Retourné** et **Refusé**, en MAD, avec deux décimales maximum. Un zéro doit être saisi explicitement ; plafond de 10 000 MAD par commission.
- Facultativement, un barème complet par ville qui remplace les trois montants par défaut. Une ville désactivée reste configurable pour ses colis historiques.
- **COD net** : retenue autorisée = minimum entre COD livré et commissions. Le livreur remet le reste ; un éventuel excédent de commission reste dû par ORIENTAL24.
- **COD intégral** : tout le COD doit être remis ; les commissions sont payées séparément. Les deux soldes sont suivis indépendamment.

Ces frais sont distincts des frais facturés au client. Chaque sauvegarde crée une version avec auteur et historique ; les modifications concurrentes obsolètes sont refusées. **Le barème en vigueur au moment de l’émission s’applique, même aux anciens colis non rapprochés.** Les relevés déjà émis ne sont pas recalculés.

### 2. Émettre un relevé

**Nouveau relevé → livreur → période facultative → Vérifier les montants → Émettre le relevé**.

- Seuls les colis actuellement assignés au livreur et au statut Livré, Retourné ou Refusé sont retenus. Le COD est compté uniquement pour les colis livrés ; aucune commission n’est comptée deux fois sur des relevés actifs.
- La période porte sur la **date de dernière mise à jour enregistrée du colis**, pas sur une preuve physique de livraison. Sans dates, tous les colis éligibles sont proposés. Maximum 500 colis ; au-delà, réduire la période.
- L’aperçu est privé à l’admin qui l’a créé, valide 30 minutes et ne modifie aucun colis. La confirmation revalide les données et le barème sous transaction ; la répétition d’une confirmation retourne le même relevé.
- Les montants, villes, références, statuts, nom du livreur et version du barème sont figés à l’émission. Les montants financiers sont stockés en **centimes entiers**.
- Le colis devient verrouillé contre les changements de statut et d’affectation. Le relevé client reste indépendant et peut être émis séparément.

### 3. Enregistrer les remises et paiements

Ouvrir un relevé → **Enregistrer une remise** (livreur vers ORIENTAL24) ou **Enregistrer un paiement** (ORIENTAL24 vers livreur).

Saisir le montant effectivement reçu/versé, le mode (Espèces, Virement ou Chèque), une référence, la date et éventuellement une note. Les paiements partiels sont possibles. Les montants non positifs, avec plus de deux décimales, supérieurs au solde, ou datés dans le futur sont refusés. La référence est unique, sans distinction de casse, pour chaque couple relevé/flux parmi les écritures actives. Une répétition réseau avec la même clé ne recrée pas le paiement.

Les statuts **À régler**, **Partiel**, **Soldé** et **Annulé** sont calculés côté serveur. En méthode nette, la retenue est autorisée par le relevé : il n’y a pas de paiement supplémentaire à enregistrer pour cette part.

### 4. Corriger sans effacer l’historique

- **Annuler une écriture** exige un motif, conserve le mouvement et réouvre son solde. Cela ne rembourse ni n’annule un transfert réel : la correction des fonds réels reste une procédure externe.
- **Annuler ce relevé** exige un motif et l’absence d’écritures actives. Le relevé reste consultable, ses montants sont exclus des totaux et ses colis redeviennent éligibles. Une facture client existante continue de verrouiller le colis.
- Un ancien aperçu confirmé ne sert jamais à recréer un relevé, même après annulation. Utiliser un nouvel aperçu pour réémettre.
- Le journal affiche les 500 dernières écritures ; le détail d’un relevé conserve son historique complet. L’historique de barème affiche les 100 dernières versions.

### Consultation et documents

L’admin voit tous les relevés ; le livreur uniquement les siens. Les clients n’accèdent pas à ce module. Recherche, filtres livreur/statut, CSV de tous les relevés du périmètre et impression/PDF A4 sont disponibles. Le CSV ne dépend pas des filtres à l’écran. Les totaux de la page portent sur tous les relevés non annulés du périmètre.

**Ce module est un suivi déclaratif interne, pas un rapprochement bancaire ni une facture fiscale.** Aucune banque n’est connectée et aucun virement n’est déclenché. Les pièces de règlement ne sont pas téléversées. Les corrections sont auditées dans la base applicative, pas dans un registre externe inviolable. Faire valider les barèmes, règles de net, procédures de contrôle et documents avant une utilisation commerciale.

### Mise à jour depuis 1.0 / 1.1

Sauvegarder la base et `.session-key`, remplacer les sources, installer les dépendances puis redémarrer. Les modules opérations et caisse ajoutent leurs tables sans effacer les données existantes. Ne pas remplacer votre base par une base de démonstration. Les premiers barèmes restent à configurer après migration.

## Nouveautés 1.1 — modes d’emploi

### Importer des colis Excel ou CSV

**Colis → Importer** (admin et client).

1. Télécharger le modèle Excel actualisé, ou le modèle CSV UTF-8.
2. Remplacer la ligne d’exemple ; conserver les en-têtes. Les colonnes requises sont `reference_externe`, `destinataire`, `telephone`, `adresse`, `ville`, `montant`. `produit` et `note` sont facultatifs.
3. Choisir le client si vous êtes admin, puis déposer le fichier. Limites : **500 lignes**, fichier **inférieur à 2 Mo**, contenu XLSX décompressé limité à 20 Mo. Pas de macros, de fichier .xls, ni de formules.
4. Vérifier l’aperçu. Les erreurs sont indiquées ligne par ligne et peuvent être téléchargées en CSV. **Aucun colis n’est créé à cette étape.**
5. Corriger le fichier si nécessaire. Quand toutes les lignes sont valides, confirmer la création du lot.

Les références externes sont uniques **par client**, sans distinction de casse. Réenvoyer un lot confirmé est sans effet ; importer de nouveau les mêmes références est bloqué. Une erreur à la confirmation annule le lot entier. La couverture, le nom de la ville et les frais sont revérifiés pour éviter de confirmer une prévisualisation obsolète. Elle expire après 30 minutes.

Les 20 derniers lots de l’utilisateur sont accessibles dans la fenêtre d’import. Les fichiers bruts ne sont pas conservés : le nom, une empreinte, les lignes analysées, les erreurs et les références créées le sont. Une politique de purge reste à définir avant l’usage commercial. Les imports ne sont pas reliés à Google Sheets : ce dernier reste une intégration distincte.

### Étiquettes et scan

**Colis ou Impression → sélectionner les colis → Étiquettes**.

- Génération réelle de QR codes et codes-barres **Code 128**, avec prévisualisation.
- Lots de 1 à 50 colis ; formats **A6 105×148 mm**, **thermique 100×150 mm**, ou **A4** pour les textes longs.
- Seule la référence de suivi est encodée : aucune adresse ni donnée personnelle dans le QR.
- Le serveur vérifie l’accès à chaque colis avant de produire les étiquettes.
- Choisir « Enregistrer au format PDF » dans l’impression du navigateur. Imprimer à 100 %, sans en-têtes ni pieds de page du navigateur. Pour les textes longs, le format A4 est imposé afin de ne pas masquer les informations.

**Colis → Scanner** retrouve le colis sans modifier son état :

- Saisie du code ou lecteur USB/Bluetooth simulant un clavier, puis Entrée.
- Caméra facultative via `BarcodeDetector` natif, sur navigateur compatible, contexte sécurisé et avec permission caméra. Certains aperçus embarqués bloquent la caméra : ouvrir alors la plateforme dans un nouvel onglet ou utiliser la saisie.
- Le client ne retrouve que ses colis et le livreur ceux qui lui sont affectés.
- La caméra est arrêtée à la fermeture de la fenêtre ou après un scan valide.

Les images QR et Code 128 ont été décodées par un lecteur indépendant dans les tests. La pagination PDF A6 et A4 est testée avec Chromium. Le cycle de fermeture de caméra est testé sur un flux simulé, **pas sur une caméra ou une imprimante physique**. Il faut valider la lecture sur vos équipements avant l’exploitation.

### Demandes de stock

**Stock & produits → Demande de stock**.

- Le client sélectionne un produit, une entrée ou sortie, une quantité et un motif.
- Le stock ne change pas et n’est pas réservé pendant l’attente.
- L’admin consulte **Demandes de stock → Traiter**, contrôle physiquement la quantité, puis valide ou refuse. Le refus exige un commentaire.
- Une validation crée exactement un mouvement lié à la demande. La disponibilité est contrôlée sous verrou transactionnel : deux sorties concurrentes ne peuvent pas rendre le stock négatif.
- Le client peut annuler sa demande tant qu’elle est en attente.
- L’onglet Historique montre les 500 derniers mouvements de son périmètre, avec auteur et motif. Les ajustements directs par admin restent disponibles et tracés.

### Mise à jour d’une version 1.0 existante

Sauvegarder `oriental24.sqlite` et la clé locale avant toute mise à jour. Remplacer les fichiers applicatifs, installer le nouveau `requirements.txt`, puis redémarrer. Le module opérations ajoute ses tables avec `CREATE TABLE IF NOT EXISTS` ; il ne supprime ni ne réinitialise les colis, villes et comptes existants. Ne copiez pas une base de démonstration par-dessus votre base de travail.

## Ce qui reste à ajouter / connecter

- SMTP et récupération de mot de passe par e-mail, vérification d’e-mail.
- Authentification Google et synchronisation Google Sheets.
- API officielle WhatsApp Business et notifications automatiques.
- KYC officiel / vérification d’identité et de coordonnées bancaires. Le dépôt privé de documents et une revue administrative manuelle existent désormais ; ils ne sont pas une certification.
- Preuve de livraison avec signature/photo ; lecteur caméra universel pour les navigateurs sans BarcodeDetector natif.
- Gestion avancée des emplacements, des quais et des autorisations par hub. Les transferts reliés aux colis, départs/réceptions et statistiques historiques existent désormais ; les anciennes palettes simplifiées restent archivées.
- Factures fiscales des livreurs, rapprochement bancaire automatisé, avoirs et comptabilité générale.
- Permissions plus fines, rôle Super Admin / responsable de hub, restrictions par territoire.
- Traduction arabe et mode RTL.
- Planification automatisée, GPS, application native et fonctionnement hors ligne.

Les intégrations externes sont présentées comme **non connectées** dans les paramètres, pas comme des fonctions actives.

## Parcours conseillé pour essayer

1. Se connecter comme **Admin**.
2. Dans Paramètres, ajouter une ville hors de l’Oriental pour vérifier la possibilité d’expansion. Modifier son tarif et les deux interrupteurs de couverture.
3. Créer un colis pour Maison Zina. L’affecter au livreur Amine El Idrissi.
4. Se connecter comme **Livreur** et le passer successivement à Ramassé, Au hub, En livraison, puis Livré.
5. Revenir comme **Admin**, générer le relevé de Maison Zina dans Facturation, vérifier les calculs et imprimer.
6. Ouvrir le même relevé depuis le compte **Client**.
7. Créer une réclamation depuis le client, répondre et la résoudre depuis l’administration.

Sur mobile, le menu est accessible en haut à gauche. Les tableaux larges défilent horizontalement. Les étiquettes et relevés utilisent l’impression du navigateur ; choisir « Enregistrer au format PDF » pour obtenir un fichier.

## Tests

```bash
python -m unittest test_app test_operations test_driver_finance test_logistics test_client_finance test_accounts test_security -v
```

115 tests fonctionnels isolés vérifient les permissions, les périmètres, la conservation des tarifs, la facturation, les imports transactionnels, les doublons, les fichiers Excel, les demandes de stock et la génération de codes. Les tests de caisse couvrent aussi les centimes, les commissions par ville, les écritures partielles, les annulations, les réexécutions sans doublon et les courses concurrentes entre émission, affectation et paiement. Ils n’utilisent pas la base de démonstration.

Pour le contrôle visuel et le parcours de lecture avec Chromium, serveur démarré :

```bash
pip install -r requirements-qa.txt
python -m playwright install --with-deps chromium
python qa/browser_check.py
python offline/build_html.py
python qa/pilotage_check.py
python qa/pilotage_1417_workflow.py
python qa/partner_palettes_workflow.py
python qa/reception_extras_workflow.py
python qa/offline_html_check.py
```

Les captures produites sont des fichiers de contrôle qualité, pas des données métier.

## Architecture

- `app.py` : API Flask, contrôle d’accès, schéma SQLite, initialisation de démonstration.
- `operations.py` : imports, étiquettes, recherche par scan et validation de stock.
- `driver_finance.py` : barèmes, relevés livreurs, rapprochement manuel et audit.
- `logistics.py` : hubs, motifs, tentatives, documents, affectations, notifications et activité historique.
- `fulfillment.py` : réservations, préparation, retour contrôlé et analyses de stock.
- `client_finance.py` : règlements clients partiels, centimes, idempotence et annulations tracées.
- `accounts.py` : dossiers administratifs, pièces privées, téléchargement contrôlé et revue manuelle.
- `runtime.py`, `security.py`, `static/security.js` : configuration, sessions serveur, limites et interface de sécurité.
- `manage.py` : opérations locales d’administration et sauvegarde/restauration.
- `static/logistics.js/.css` : interface de ces nouveaux parcours, chargée après pilotage. Le module sécurité vient ensuite et effectue le seul démarrage SPA.
- `static/app.js`, `static/operations.js` et `static/driver-finance.js` : interface JavaScript sans framework.
- `static/style.css`, `static/operations.css` et `static/driver-finance.css` : styles adaptatifs et impression.
- `templates/index.html` : document de base.
- `static/logo.png`, `wordmark.png`, `van.png` : votre logo et ses déclinaisons recadrées.
- `test_app.py`, `test_operations.py` et `test_driver_finance.py` : tests API isolés.

Variables disponibles : `PORT`, `DB_PATH`, `SECRET_KEY`, `PREVIEW_COOKIES`. Pour un aperçu HTTPS embarqué dans une iframe, lancer le serveur avec `PREVIEW_COOKIES=1` active des cookies Secure, SameSite=None et Partitioned. Laisser cette variable absente pour le développement local standard. À défaut, une clé locale est créée dans `.session-key`. Elle doit rester privée. La distribution source ne contient pas cette clé ni la base de travail.

## Avant une mise en production

Cette démo contient volontairement des comptes et des boutons d’accès publics. **Ne la publiez pas telle quelle avec des données réelles.**

Prévoir au minimum :

1. Utiliser le mode production sur une base séparée, créer le premier Admin via CLI, protéger et renouveler les secrets. Le mode demo conserve volontairement ses accès publics.
2. Validation des villes, frais, contrats, règles de retour, commissions et documents légaux d’ORIENTAL24.
3. Installer et vérifier le HTTPS et le proxy réels ; les sessions serveur, cookies de production et limites de tentatives existent. Compléter avec protection anti-abus réseau, supervision et test de charge.
4. Authentification renforcée de l’administration, vérification d’e-mail et récupération de compte sécurisée.
5. Revue de sécurité, tests de charge, pagination serveur et base adaptée au volume réel (par exemple PostgreSQL).
6. Généralisation des montants entiers/décimaux à la facturation client et au COD source (encore stockés en REAL dans le socle historique). Les caisses livreurs et règlements clients utilisent désormais des centimes entiers ; valider les règles comptables, la conservation et la clôture des journaux avec le responsable comptable.
7. Analyse antivirus des documents déposés, politique de rétention, sauvegardes chiffrées, restauration testée, supervision, gestion des erreurs et procédures d’exploitation.
8. Configuration des prestataires externes, consentement aux notifications et respect de la réglementation applicable aux données personnelles.

La démonstration sert à valider les écrans et les flux avec votre équipe avant cette phase.
