# ORIENTAL24 1.4.17 — 21 septembre 2026

- **Audit pilotage complet, sans raccourci** : relecture ligne à ligne de `pilotage.js`/`.css`, des 21 dialogues passant une version figée, des gardes de réception, des 7 rapports QA historiques (tous re-PASS), des fichiers de test (**aucun test ignoré**, 244/244) et du build autonome.
- **403/404 de réception enfin tracés pour TOUS** : toute tentative de « Réception du colis » refusée — client société, **livreur** (nouvellement couvert), agent d'un autre hub — est enregistrée dans l'historique de la palette : qui `(actor_role, actor_hub_id)` et pourquoi (`Réception refusée`, motif exact). Le 404 d'un agent hors hub ne fait **aucune fuite d'existence** ; un compte désactivé est révoqué immédiatement (par rôle).
- **409 « aléatoires » des dialogues corrigés** : nouvel appui partagé `api409` (serveur + HTML) — relit la fiche, remonte la version à jour et **rejoue une seule fois** l'intention déclarée (statut colis, parsemer, ville, contacts support/facture, annonces, barème, fiche/accès livreur, tentatives, dispatch/cancel de documents, dossiers, scans et clôtures de réception). Si le conflit persiste après relecture, l'erreur ressort : le verrou optimiste reste un garde-fou, jamais contourné.
- **Réception en masse** : à un conflit de version sur `receive-all`, la liste **physiquement restante** a pu changer — le dialogue se **recharge avec la liste du moment** (toast explicite) pour re-contrôler les colis réellement restants ; pas de rejeu à l'aveugle d'une liste modifiée.
- **CSS pilotage** confirmé en fichier unique `static/pilotage.css`, consommé tel quel par le serveur et par `offline/build_html.py`; HTML autonome régénéré (2 775 234 octets).
- Preuves : 244 tests unitaires; nouveau QA navigateur `pilotage_1417_workflow` (refus audités, 404 sans fuite, conflit receive-all secouru, autonome embarqué); régressions `pilotage_check`, `partner_palettes_workflow`, `reception_extras_workflow`, `offline_html_check`; zéro erreur JavaScript.

# ORIENTAL24 1.4.16 — 21 septembre 2026

- Incidents de réception sur palettes (manquant libéré et suivi, endommagé avec photo obligatoire et affectation suspendue en base, imprévu sans mutation) : déclaration guidée physiquement, réponse de la société, décision Admin/Agent motivée, historique partagé. Une palette incomplète se clôt **avec écarts** (`Clôturé (écarts)`), jamais comme entièrement reçue.
- Tarifs par client et par ville (Admin) : valeurs 0–10 000 MAD, audit complet, application uniquement aux **nouveaux** colis quelle que soit la source (interface, import, fulfillment, API partenaire). Aucune rétroactivité sur colis, relevés et factures.
- Scan caméra optionnel à la réception (BarcodeDetector natif) : il remplit le tracking et la confirmation physique reste obligatoire. Aucun bouton caméra factice en simulation.
- Unicité du tracking passée à **société+tracking** : mêmes codes possibles entre sociétés, ambiguïtés détectées (409) et désambiguïsées par filtre société au scan. Index `idx_tracking_search` remplace l'ancienne contrainte globale.
- Rôle **Agent réception** : compte borné à un hub actif, sans visibilité colis/finance, reçoit et gère les incidents de son hub, alertes de son hub, audit sous son nom, sessions révoquées à la désactivation.
- Rubrique **Alertes** : palettes annoncées non arrivées, réceptions partielles pendantes, colis réceptionnés non affectés et incidents ouverts. Seuils configurables (0 = désactivé, ≤ 720 h) ; aucun envoi externe.
- **API partenaire** (`/api/partner/v1`, Bearer `O24K-…`) : villes+tarifs de la société incluant ses tarifs personnalisés, création idempotente (clé obligatoire), suivi et liste bornée à la société, 120 req/min, aucune donnée d'autres clients. Clés révocables gérées par Admin (une active par société ; secret affiché une seule fois).
- 239 tests API, licences parcours navigateur dédiées (incidents/agent/tarifs/clé API/alertes + régressions palettes v1.4.15 et HTML autonome) ; zéro erreur JavaScript.

# ORIENTAL24 1.4.15 — 20 septembre 2026

- Palettes partenaires : accès sociétés de livraison/Admin, hub partagé avec la logistique, manifeste de 1 à 500 colis existants, référence palette distincte des trackings, recherche et sélection groupée.
- Brouillon réservé, envoi physique déclaré par la société, réception Admin unitaire au tracking ou complète après liste et confirmation. Les manquants restent attendus ; les seuls colis reçus passent Réceptionné au hub destinataire et sont libérés pour affectation.
- Réutilisation des verrous ops_documents/ops_document_lines ; les autres affectations et anciennes portes de réception ne contournent pas ce circuit.
- Annulation motivée de brouillon sans suppression. Historique société, recherche/état/pagination, CSV scoped, manifeste A4 imprimable avec sauvegarde PDF navigateur.
- Clés acteur/contenu et transactions : créations/réceptions rejouables après perte de réponse, doublons sans effet, contrôle des révisions et réception complète atomique.
- HTML autonome : même cycle en simulation, hubs locaux et persistance ; scan clavier/lecteur USB-Bluetooth, sans réception caméra prétendue.
- Deux tables additives partner_palette_meta / partner_palette_keys ; ancien registre conservé séparément. Migration de l’aperçu : 54 tables métier préexistantes inchangées, nouvelles tables vides, intégrité OK.
- 229 tests API et parcours navigateur dédié réussis ; régressions logistique/livreur/facturation/core/types clients/facture/HTML. Modules financiers, politique de tracking et facture identiques à v1.4.14.
- Aucun paiement, entrée stock produit, signature électronique ou synchronisation avec le logiciel partenaire n’est déclenché implicitement.

# ORIENTAL24 1.4.14 — 20 septembre 2026

- Comptes Client : choix Vendeur / Société de livraison dans la création Admin et l’inscription autorisée ; type dans la liste et le profil.
- Vendeur : code O24 généré. Société : tracking fourni et conservé, casse/zéros inclus, utilisé dans tout le parcours existant. Aucun rôle privilégié ni tarif différent implicite.
- Formulaire colis adapté au compte sélectionné ; scanner manuel/caméra accepte les références partenaire dans le même périmètre autorisé ; suppression de la transformation visuelle en majuscules.
- Excel/CSV : reference_externe devient le tracking pour les sociétés seulement ; cellules texte requises sous Excel ; prévisualisation/confirmation et doublons recontrôlés, lot atomique et retries idempotents.
- Préparation stock : tracking société réservé puis conservé à la création physique, sans contournement par un code O24 automatique.
- Migration additive : users.client_type, client_type_audit, index unique tracking COLLATE NOCASE. Type modifiable par Admin avant premières commandes, puis verrouillé ; profil client sans changement de type.
- 211 tests API, parcours UI dédié et sept régressions navigateur réussis. Contrôle réel de migration : 53 tables métier préexistantes, colonnes/valeurs inchangées ; nouveaux types Vendeur, audit vide. Modules financiers et modèle de facture identiques à v1.4.13.
- HTML autonome reconstruit : simulation de saisie/type/duplicats ; import, nouvelles étiquettes et préparation stock restent serveur.
- Limite explicite : le circuit d’envoi/réception des palettes des sociétés n’est pas encore implémenté. Les outils logistiques existants ne sont pas présentés comme ce nouveau circuit.

# ORIENTAL24 1.4.13 — 20 septembre 2026

- Facture Client imprimée harmonisée avec le modèle Livreur : moteur A4/CSS/pagination communs, logo, informations, résumé statut/tarif, COD/frais/net, colis, journal et pied de page.
- Adaptation strictement en lecture seule du modèle financier client existant : frais de service, net client autoritaire, soldes entrants/sortants et états inchangés. Pas de commissions ni de conditions de remise livreur appliquées au client.
- Protection de compte après chargement et avant pagination, texte échappé, HTML autonome reconstruit.
- Aucune migration ; modules comptables et PDF direct serveur inchangés.
- 194 tests API et six parcours navigateur réussis ; 64 colis fictifs sur 4 pages, tableaux métier/CSV inchangés après impression, cas négatif/nul/partiel et rendu Livreur contrôlés.
- Guide v1.4.13 et exemple PDF client entièrement fictif. Simulation locale et relevé interne non fiscal restent explicitement signalés.

# ORIENTAL24 1.4.12 — 20 septembre 2026

- Facturation commune : Clients / Livreurs, factures existantes et nouvelles, filtres/date/état/titulaire, pagination et totaux filtrés.
- Passage à Paid après confirmation de montants réellement reçus/versés ; réutilisation des journaux existants, écriture atomique des deux flux si nécessaire, révision et clés idempotentes. Règlements partiels et correction Not Paid motivée/auditée.
- Colis Paid exclus des listes de service du livreur, sans suppression ni désaffectation ; facture conservée dans Archives Paid. Client : facture et colis conservés. Correction de règlement rétablit la visibilité sauf récupération physique antérieure.
- Téléchargement serveur direct PDF A4 et CSV détaillé, CSV de liste filtré. Accès Admin/compte propriétaire. Polices embarquées et mise en page multipage ; document interne non fiscal.
- Rafraîchissement de fond ciblé sans prolongation de la session inactive ; saisies et fenêtres actives préservées. HTML local actualisé, PDF local via impression.
- 194 tests API réussis, parcours dédié multi-comptes/mobile/HTML, PDFs longs et régressions navigateur. Guide `GUIDE-v1.4.12.md`.

---

# ORIENTAL24 1.4.11 — 20 septembre 2026

- Modèle de facture livreur A4 inspiré du PDF fourni, sous identité ORIENTAL24 : en-tête, prestations par statut/tarif, COD/frais/net, téléphone des colis, pagination et entêtes répétés, journal des règlements.
- Configuration Admin des coordonnées légales et conditions facultatives ; aucun contenu du concurrent ni délai de paiement repris. Coordonnées versionnées et journalisées.
- Métadonnées d’impression immuables ajoutées à l’émission, avec fallback honnête pour les anciens relevés. Pas de nouveau circuit de facturation ni de changement des règles d’éligibilité/montants/paiements.
- Prix unitaires distincts lorsque les barèmes diffèrent ; net arithmétique distingué des deux soldes de règlement. Annulé n’est pas assimilé à Refusé.
- 179 tests API réussis ; PDF de 250 colis fictifs en 12 pages ; stress de 500 longues lignes/plusieurs prix en 65 pages sans débordement ; HTML et six régressions navigateur validés.
- Migration additive documentée dans `GUIDE-v1.4.11.md`.

---

# ORIENTAL24 1.4.10 — 20 septembre 2026

- Correction de l’omission du bouton Facture sur les lignes Livreurs : cercle $ jaune entre informations et blacklist, confirmation nominative et Accepter rouge.
- Aperçu des montants et des colis avant émission ; réutilisation du relevé interne immutable, puis détail et impression/PDF. Aucun nouveau circuit de facturation ni paiement automatique.
- Barème manquant et absence de colis traités sans émission ; changement concurrent bloqué, double clic neutralisé, réponse perdue reprise avec le même jeton, réponse tardive ignorée après fermeture du dialogue.
- Admin uniquement, comptes archivés/blocages compatibles avec le règlement historique, HTML simulé actualisé.
- 173 tests API, parcours dédié serveur/mobile/HTML et quatre régressions navigateur réussis. Guide `GUIDE-v1.4.10.md`.

---

# ORIENTAL24 1.4.9 — 20 septembre 2026

- Les cinq actions Livreurs demandées : informations en panneau latéral, blacklist, assigner, recevoir/récupérer, archiver. Historique, filtres Équipe/Blacklist/Archives et recherche.
- Cycle confirmé : remise du matin au livreur, récupération physique des non-livrés le soir, Livré non récupérable par ce parcours. Scans séquentiels vérifiés/confirmés, versions, transaction et reprise idempotente.
- Refusé/Retourné quittent la tournée sans effacer leur attribution financière ni modifier les montants/date de clôture ou les lignes de relevé. Les ouverts récupérés passent à Réceptionné sans livreur ; historique conservé.
- Blocage/archive révoquent les sessions et interdisent l’affectation. Archive refusée tant que non-livrés ou documents actifs subsistent. Soldes et règlements historiques Admin conservés, même compte inactif.
- Champs et tables additifs ; aucune réaffectation automatique des colis existants. HTML simulé mis à jour ; pas de nouvelle intégration externe.
- 173 tests API, parcours dédié et régressions validés. Guide `GUIDE-v1.4.9.md`.

---

# ORIENTAL24 1.4.8 — 20 septembre 2026

- Barre de navigation repliée en icônes au repos, élargie au survol, repliée en quittant la zone. Pas de bouton sur ordinateur ; libellés accessibles au clavier, menu tactile conservé.
- Strips d’annonces FR/AR, liens et grand bandeau configurable. Administration par style, audience, ordre et activation ; aucune publicité ou consigne du concurrent reprise.
- API filtrée selon le rôle, brouillons Admin seulement, CSRF, révision transactionnelle, audit, limites et liens HTTPS vérifiés. Téléchargement du modèle Excel actuel selon les droits existants.
- HTML local : annonces d’exemple explicitement fictives, gestion persistée si stockage disponible, aucune publication serveur ; modèle Excel actualisé signalé comme fonction serveur.
- Schéma additif sans modification des opérations existantes. 161 tests API et parcours navigateur/régressions validés. Guide `GUIDE-v1.4.8.md`.

---

# ORIENTAL24 1.4.7 — 20 septembre 2026

- Icône circulaire de réclamation à côté du crayon, ouvrant la fenêtre demandée : sujet, catégorie, commande fixée, description, pièces jointes, Annuler/Créer.
- Réutilise les tickets liés et leurs droits : Admin et auteur, commande revérifiée à l’envoi ; aucun changement de ville/statut/montant ni des verrous financiers.
- Fichiers privés PDF/JPG/PNG, 3 fichiers et 1 Mo total ; validation serveur, images réencodées, téléchargement autorisé sans cache. Pas d’antivirus garanti.
- Création atomique et clé contre les doublons lors d’une reprise réseau ; schéma additif `claim_attachments` et `claim_requests`.
- HTML local avec réclamations liées et fichiers, mobile et téléchargement ; simulation sans envoi au support ni sécurité réelle.
- 154 tests API réussis, parcours dédié et régressions validés. Voir `GUIDE-v1.4.7.md`.

---

# ORIENTAL24 1.4.6 — 20 septembre 2026

- Crayon Admin à droite de la commande ; panneau latéral « Modifier la ville », sélection actuelle, annulation, actualisation, confirmation, mobile.
- Endpoint Admin+CSRF transactionnel avec révision et couverture actives ; états clôturés, factures, relevés financiers et documents actifs protégés.
- Correction de destination uniquement : COD, frais enregistrés, adresse, livreur, état, motif et rendez-vous conservés. Historique ancienne/nouvelle ville ; aucun effet lors d’une annulation avant soumission ou d’un no-op valide.
- HTML local équivalent ; pas de migration, de recalcul massif ou de nouvelles données métier sur la base existante.
- 147 tests API réussis ; parcours dédié desktop/mobile/HTML et régressions réussis. Guide `GUIDE-v1.4.6.md`.

---

# ORIENTAL24 1.4.5 — 20 septembre 2026

- Icône Copier placée avant le destinataire, également sur la fiche et les cartes Livreur mobiles.
- Référence, nom, téléphone, adresse, ville, produit, montant et état copiés depuis un détail fraîchement autorisé ; pas d’annuaire, données financières internes ou contacts du personnel.
- Retour de succès après confirmation du navigateur seulement ; si refus/indisponibilité, texte sélectionnable et nouvelle tentative explicite. Aucune lecture du presse-papiers par l’application.
- Aucun effet sur statut, sélection de ligne, expansion ou données métier. Droits conservés après réaffectation. HTML autonome mis à jour.
- 139 tests API réussis ; test réel Chromium de presse-papiers, permissions refusées, caractères spéciaux, mobile, HTML et régressions pertinentes réussis. Guide `GUIDE-v1.4.5.md`.

---

# ORIENTAL24 1.4.4 — 20 septembre 2026

- Catalogue demandé ajouté sans supprimer les anciens états : 13 états distincts, dont cinq nouveaux états ouverts.
- `parcel_statuses.py` centralise transitions, significations et parcours de tentative ; politique transmise au serveur/UI/HTML.
- Reporté distinct de Programmé : report sans date et, pour la tentative Livreur, motif historisé sans COD déclaré. Intéressé n’est pas une livraison.
- Prise en charge exigeant un livreur actif affecté ; réaffectation simple/groupée ne conserve pas une prise en charge mensongère du nouveau livreur.
- Départ des documents de transfert → Transit ; réception partielle/complète → Réceptionné, hub de destination, versions/verrous et idempotence conservés. Ramassages et retours gardent leurs parcours antérieurs.
- Aucun nouveau statut dans les factures de colis clôturés ou commissions ; seul Livré compte le COD livré. Aucune modification de tarifs ni migration/reclassification des colis existants.
- 139 tests API réussis (9 nouveaux), parcours catalogue réel multi-rôles/HTML/mobile et régressions des modules précédents. Guide `GUIDE-v1.4.4.md`.

---

# ORIENTAL24 1.4.3 — 20 septembre 2026

Correction du parcours demandé : l’état courant ouvre une liste directement dans la ligne, à côté de Note, au lieu d’une fenêtre de formulaire générique. État actuel désactivé, étapes simples directes, confirmations et saisies complémentaires dans la même liste. Transitions selon rôle, appel au parcours de tentative Livreur pour les résultats finaux, contrôle de COD et rendez-vous conservés. Révision capturée à l’ouverture pour refuser les écrasements concurrents. Le HTML simule ces choix localement ; pas de preuve ou tentative serveur fictive.

130 tests API réussis. Nouveau test `qa/status_dropdown_workflow.py` et régressions notes/contacts/core/imports/finances/logistique/sécurité/pilotage/HTML réussis, dont mobile. Aucun changement de schéma ni de tarifs. Voir `GUIDE-v1.4.3.md` ; restrictions et limites de démonstration inchangées.

---

# ORIENTAL24 1.4.2 — 20 septembre 2026

- Boutons Statut / Note dans la liste et motif dans le détail ; Note sur les cartes mobiles Livreur.
- 17 motifs de suivi ajoutés au catalogue existant, sélection recherchable, suppression explicite et administration dans Hubs & motifs.
- Mutation distincte du statut, horodatages financiers inchangés, pas de rendez-vous ou tentative implicite. Acteur et motif figés dans la chronologie.
- Droits Admin / livreur actuellement affecté, clients en lecture seule, verrous transport/finances, contrôle CSRF et révisions. Formulaire de statut présélectionné sur l’état actuel lorsqu’autorisé, avec version opérationnelle.
- Filtre par motif, export filtré enrichi ; HTML autonome avec simulation locale/persistance du motif.
- 130 tests API réussis et parcours navigateur dédiés/régressions multi-rôles/mobiles/HTML réussis. Menu repositionné au redimensionnement sans fermeture intempestive ; pas d’ouverture automatique du clavier sur petit écran.

Voir `GUIDE-v1.4.2.md`. Les limites de démonstration et de sécurité antérieures restent applicables. Aucun numéro personnel, tarif ou changement de statut n’est importé de la capture.

---

# ORIENTAL24 1.4.1 — 20 septembre 2026

## Commande et contacts
- Détail dépliable sous la ligne, fenêtre sur clic de référence et présentation mobile.
- Informations et contacts à gauche ; chronologie enregistrée avec acteurs/dates à droite.
- Nom/téléphone du livreur actuellement affecté, lus sur le serveur à l’ouverture/actualisation.
- Annuaire Support professionnel Admin, affectation/retrait par commande, modifications versionnées et états inactifs explicites. Aucun contact prérempli et aucun nouveau rôle utilisateur.
- Coordonnées accessibles seulement aux lecteurs autorisés de la commande, liens d’appel contrôlés, aucune exposition de l’annuaire aux clients/livreurs.
- Migrations additives ; aucun changement des montants, statuts, livreurs, dates financières ou verrous lors d’une affectation Support.

## Vérification
122 tests API réussis (115 existants + 7 contacts). Parcours dédié contacts et régressions core/imports/finances/logistique/sécurité/filtres/HTML, dont mobile, sans erreur JavaScript. Le test financier a révélé une différence de libellé du verrou : texte clarifié en « Colis verrouillé dans un relevé financier », puis test relancé avec succès. Voir `GUIDE-v1.4.1.md`.

HTML autonome reconstruit : contacts livreurs fictifs seulement, administration Support sur serveur. Pas de temps réel, GPS ou téléphonie intégrée. Les limites de sécurité/exploitation de 1.4 restent applicables.

---

# ORIENTAL24 1.4 — 20 septembre 2026

## Livré
- Sessions serveur révocables, jetons aléatoires stockés hachés, maximum 10 actives ; 30 min d’inactivité / 12 h absolues par défaut.
- Interface privée Sécurité & sessions, fermeture unitaire ou des autres sessions avec confirmation du mot de passe ; historique et réseaux masqués.
- Logout, reset, changement de mot de passe et désactivation invalident les sessions concernées. Une ancienne cookie ne suffit plus ; la session actuelle est renouvelée après changement du mot de passe.
- Limites SQLite transactionnelles avant vérification de mot de passe, protection contre dépassement concurrent, Retry-After, origine et CSRF explicite. Exception strictement limitée à l’origine HTTPS du même hôte en mode aperçu demo.
- Configuration production séparée : aucun seed demo, refus des bases demo, dossier de base privé, clé explicite, trusted hosts, HTTPS/Secure, HSTS, anti-iframe et CSP partielle. Les secrets ne sont pas exposés dans l’UI.
- Outils locaux de premier Admin et récupération manuelle ; backup SQLite/WAL cohérent, vérification, restauration vers fichier neuf, révocation des sessions restaurées et purge explicite à 90 jours.

## Validation et limites
115 tests automatisés (91 du socle, 24 de sécurité/configuration/exploitation), parcours navigateur multi-contextes, mobile et régressions métiers réussis. Aucun échec JavaScript dans les parcours vérifiés. Journaux `qa/v14-*-results.txt`.

L’aperçu reste demo. Reconnexion requise après migration. Aucune modification des barèmes ni suppression de données métier. Pas d’envoi externe, de MFA, de récupération autonome par e-mail, d’antivirus PDF, de chiffrement de backup ni de certification de production. CSP non stricte pour les scripts ; isolation du backend et configuration du proxy à assurer au déploiement. HTML autonome limité, sans simulation de ces protections. Voir `GUIDE-v1.4.md`.

---

# ORIENTAL24 1.3 — 20 septembre 2026

## Livré sur le serveur
- Exécution : motifs, rendez-vous, tentatives idempotentes, destinataire et COD déclarés ; aucune signature/photo certifiée.
- Hubs et documents avec colis rattachés, départ, annulation avant départ, réception partielle, contrôle des doublons, QR vérifié et impression A4/PDF.
- Affectation groupée avec aperçu et revalidation atomique ; protection des colis liés aux documents/finances.
- Affectations et tentatives quotidiennes ; mouvements historiques de hubs et situations actuelles distinctes ; CSV sans formules actives.
- Réclamations liées aux colis, priorité, responsable, première réponse et notifications internes privées.
- Stock : réservation atomique, disponibilité distincte, préparation physique vers colis au hub, annulation avant préparation et retour intégral contrôlé. Mouvements et analyse produits datés.
- Facturation clients : règlements partiels, soldes en centimes, sens des flux, références actives uniques, rejouabilité et annulations motivées.
- Dossiers de comptes : informations, documents privés, retrait avec suppression du contenu et trace, soumission et décision administrative. Pas un KYC, ni une activation automatique.
- Correction d’un autofocus différé susceptible de voler le focus pendant la saisie rapide.

## Migration / limites
Migrations additives, données de travail préservées. Aucun hub ni tarif livreur activé automatiquement. Les anciens règlements clients marqués réglés sont étiquetés « Historique importé », sans preuve bancaire inventée. Aucune reconstruction des affectations historiques. Les anciennes palettes déclaratives restent archivées.

Les nouveaux parcours ne sont pas simulés dans le HTML autonome. Intégrations officielles, KYC, durcissement de production, antivirus PDF, permissions par hub, inventory par emplacement, expéditions/retours partiels, applications natives et POD restent hors de cette livraison. Voir `GUIDE-v1.3.md` pour le périmètre détaillé.

## Validation
**91 tests API réussis.** Parcours navigateur de base, opérations/imports, caisse livreurs, nouveau flux logistique/stock/comptes/finances clients, filtres et HTML relancés. QR du document décodé indépendamment ; PDF contrôlé. Huit vues nouvelles ou enrichies vérifiées à 390px ; aucun échec JavaScript dans les parcours testés. Journaux : `qa/v13-*-results.txt`.

---

# Révision UX sur ORIENTAL24 1.2 — 20 septembre 2026

Audit des pages publiques Olivraison, des notes officielles d’applications et des captures fournies. Accès authentifié concurrent non réalisé. Le rapport distingue preuves visuelles, fonctionnalités annoncées et propositions.

**Livré :** raccourcis opérationnels par rôle, correction Tous les colis, dates inclusives et filtres combinés, chips de filtres, pagination compacte, recherche sans accents, actualisation et export CSV filtré sur toutes les pages. Ces ajouts ne changent pas les tables ou règles financières. Inclus également : générateur HTML autonome de démonstration et tests du fichier en iframe sans stockage autorisé.

**Non livré par cette révision :** motifs structurés, reprogrammation datée, documents de ramassage/retour, hubs reliés aux colis, analyse historique d’affectation, notifications externes ou preuves de livraison (livrés par les versions 1.3 à 1.4.16 ci-dessus). Priorités et critères d’acceptation : audit de référence archivé dans cet historique.

**Validation :** 48 tests API du socle passent ; parcours précédents colis, caisse, import, scan et stock relancés sans erreur JavaScript. Nouveau parcours UX sur serveur et HTML : files, dates, rôles, export filtré, actualisation et mobile.

---

# ORIENTAL24 1.2 — 20 septembre 2026

## Caisse & commissions livreurs
- Barèmes explicites par livreur, trois statuts et exceptions par ville, sans montant financier préchargé.
- Remise COD nette ou intégrale ; traitement des commissions supérieures au COD sans solde négatif.
- Prévisualisation / confirmation, tarifs figés, unicité des colis actifs et verrouillage des changements.
- Encaissements COD et paiements de commission partiels, deux soldes, références et protection contre les réexécutions.
- Annulations avec motif, audit des versions et des écritures, réémission après libération contrôlée des colis.
- Vue Admin et Livreur cloisonnée, journal, recherche/filtres, CSV, impression/PDF A4 et mise en page mobile.
- Aucun transfert bancaire automatique, aucune facture fiscale certifiée ; documents internes de démonstration.

## Validation
48 tests API isolés passent, dont 17 nouveaux tests financiers. Les essais concurrents couvrent émission répétée, paiement excédentaire et réaffectation face à une émission. Les parcours navigateur couvrent les trois phases : barèmes, exceptions, caisse, corrections, rôles, mobile, CSV/PDF, ainsi que les régressions colis, facturation client, import, codes et stock. Aucune erreur JavaScript dans ces parcours.

## Migration et limites
Les tables sont ajoutées automatiquement au démarrage. Sauvegarder la base et la clé avant mise à jour ; aucun tarif de commission n’est injecté. Le détail des règles, plafonds, périodes, retenues et précautions figure dans README.md. La caisse utilise des centimes entiers ; les anciens modules de COD et de facturation client restent à migrer d’un stockage REAL. Les intégrations externes et le durcissement de production restent hors de cette livraison.

---

# ORIENTAL24 1.1 — 20 septembre 2026

## Ajouts livrés

### Import Excel / CSV
- Modèles téléchargeables et liste dynamique des villes ouvertes.
- Prévisualisation et rapport des erreurs, sans création avant confirmation.
- 500 lignes maximum, fichiers inférieurs à 2 Mo.
- Import transactionnel tout ou rien, références externes uniques par client.
- Confirmation réexécutable sans doublons, revalidation des tarifs et de la couverture.
- Historique privé des 20 derniers lots, prévisualisations valables 30 minutes.

### Étiquettes et scan
- Vrais QR codes et codes-barres Code 128 générés côté serveur.
- Prévisualisation paginée, lots de 50 maximum, impression/PDF via le navigateur.
- A6 (105 × 148 mm), thermique (100 × 150 mm), A4 pour les textes longs.
- Recherche par référence et lecteur clavier ; caméra native si prise en charge par le navigateur.
- Contrôle d’accès sur la génération et la recherche, caméra arrêtée à la fermeture.

### Demandes de stock
- Demandes d’entrée et de sortie par client ou administrateur.
- Validation physique par admin, refus motivé, annulation avant traitement.
- Stock revérifié lors de l’approbation, un seul mouvement par validation.
- Historique et filtres ; aucune réservation implicite de stock en attente.

## Vérification

- **31 tests API distincts** : droits, isolation des comptes, imports, erreurs, doublons, expiration, tarifs modifiés, fichiers XLSX, facturation et stock.
- Parcours navigateur v1 conservé : création de ville, colis, affectation, étapes livreur, facture, règlement, stock, ticket et réponse.
- Parcours navigateur v1.1 : import invalide/valide, rapport CSV, doublons, étiquettes, recherche par référence, demande client et validation admin.
- Décodage indépendant des images QR et Code 128 par ZXing-C++.
- Vérification PDF Chromium : deux colis donnent deux pages A6 ; un texte long reste complet sur une page A4.
- Fermeture de caméra vérifiée sur un flux vidéo simulé ; pas d’essai de caméra ou imprimante physique.
- Contrôle d’affichage à 1440 px et 390 px, sans erreur JavaScript dans les parcours testés.

## Mise à jour

Installer `requirements.txt` puis redémarrer le serveur. Les nouvelles tables sont ajoutées sans réinitialisation des données existantes. Sauvegarder la base et la clé avant toute mise à jour. Le ZIP ne contient ni base de travail ni clé de session.

## Limites toujours présentes

Version de démonstration, non homologuée pour l’exploitation commerciale. Les accès de démo restent publics. Google, WhatsApp et SMTP ne sont pas connectés. Vérification documentaire client, commissions / factures livreur, preuve de livraison et gestion avancée des palettes restent à développer. Les règles financières, la sécurité opérationnelle, les sauvegardes et les données légales sont à valider avant production. Voir README.md pour le périmètre complet.
