# ORIENTAL24 v1.4.16 — Réception renforcée et intégrations

Cette livraison ajoute sept chantiers demandés ensemble : incidents de réception avec réponse de la société, tarifs par client et par ville, scan caméra dans la réception, cohabitation du même tracking chez plusieurs sociétés, compte Agent de réception, alertes de retard et API partenaire externe.

## 1 · Incidents de réception (manquant / endommagé / imprévu)

Depuis une palette **En transit** ou **Partiellement reçu**, Admin ou l'agent du hub déclare :

- **Colis manquant** : on choisit une ligne attendue. Le colis est *libéré* du manifeste (aucune réception marquée), la palette peut être complétée sans lui, puis **clôturée avec écarts** (`Clôturé (écarts)`) — jamais fermée comme entièrement reçue.
- **Colis endommagé** : photo obligatoire (< 1 Mo, JPG/PNG, ≤ 8 Mpx, convertie et re-photo encodée côté serveur). Le colis est reçu physiquement (**Réceptionné**), mais **son affectation livreur est suspendue** (affectations Admin et scan livreur renvoient 409) jusqu'à décision :
  - *release* — libération documentée, affectation de nouveau possible ;
  - *hold* — blocage conservé (cela peut être revu en release plus tard).
- **Colis imprévu** : tracking libre + note, photo facultative, **aucune mutation d'aucune commande**.

Champs communs : note obligatoire, case « constat physique » obligatoire, `request_key` dédiée (20–80) avec contrôle d'empreinte (409 si la même clé porte une autre saisie, **replay** exact renvoyé avec `replayed: true`). Chaque déclaration est tracée (`ops_audit`) et notifiée à la société.

La **société répond** depuis son espace (`Réponse société`, notifiée aux admins). **Admin/Agent décident** avec une note motivée ; les deux parties voient l'historique complet du dossier. Photo consultable via `GET /api/partner-palette-incidents/<iid>/photo` (Admin ou société propriétaire).

Validation formulaire renforcée côté serveur : 400 si note absente, photo aberrante (base64, format, taille) ou confirmation manquante.

## 2 · Tarifs par client (société ou vendeur), par ville

- `GET /api/clients/<id>/tariffs` (Admin) : tableau de toutes les villes livrables avec défauts, valeur éventuelle déjà personnalisée, métadonnées, + historique complet (qui, quand, avant/après).
- `PUT /api/clients/<id>/tariffs/<city_id>` : valeurs 0..10 000 (MAD, centime sûr) ; 400 si hors plage, 404 si ville/client inconnus. Réponse `changed:false` si identique aux tarifs d'origine.
- `DELETE .../tariffs/<city_id>` : retour au défaut, lui aussi historisé.

**Principe dur** : un tarif s'applique UNIQUEMENT aux colis créés APRÈS (interface classique, import Excel, fulfillment et API partenaire partagent le même calcul `tariff_fees_for`). Les frais enregistrés sur les colis existants, les snapshots factures, les relevés et la facturation des deux côtés ne bougent jamais. Les villes retournent aussi les droits pick-up/delivery inchangés.

## 3 · Scan caméra à la réception

Dans le formulaire de réception d'une palette, un bouton **Caméra** apparaît si `window.BarcodeDetector` et `navigator.mediaDevices` sont disponibles (Chrome/Android, Chrome Mac/Linux desktop ; Safari/Firefox proposent saisie/lecteur USB). La caméra éclaire le champ tracking — **la case de confirmation physique reste obligatoire** : aucune réception automatique. Vidéo arrêtée à la fermeture de la modale ; tout rejet de permission retombe sur une alerte claire et la saisie reste disponible.

Pas de caméra simulée : en situation offline (`opsOffline`) et dans le standalone HTML, aucun bouton caméra factice n'est présenté.

## 4 · Même tracking chez deux sociétés différentes

L'unicité du tracking est désormais la contrainte composite **client+tracking** (suppression de `UNIQUE` global et conversion de la contrainte legacy en index `idx_tracking_search` lors des migrations). Effets :

- Une société refait ses codes sans se soucier des autres ; le duplex mIx-0001/MIX-0001 reste interdit chez **elle**.
- Les vendeurs (O24 automatique) gardent leurs codes O24 sans changement.
- L'ambiguïté est résolue aux scans (`/api/scan`, aperçu de scan livreur) : 409 si plusieurs sociétés ont le même tracking, attribution directe possible via `client_id` sélectionné côté web (les recherches classiques acceptent déjà un filtre société).

## 5 · Compte Agent de réception

Nouveau rôle `agent`, lié à UN hub actif (`users.agent_hub_id`, à la création et à l'édition Admin) :

- Home renvoyé automatiquement sur **Palettes partenaires** (menus sensibles cachés : colis, impression, finance, documents logistiques, analytics…). Il ne voit plus aucune donnée de facturation.
- Sur les palettes : réception (unitaire, complète), incidents (déclaration + décision), alertes du hub. Aucune création, envoi ni annulation.
- Localisation stricte : ses requêtes et ses alertes sont bornées à son hub ; une palette d'un autre hub répond 404. Chaque action figure dans `ops_audit` sous son nom.
- Désactivation du compte → révocation immédiate de toutes ses sessions (sécurité existante), passage en 401 dès la prochaine requête.
- Compte de démo facultatif : `ORIENTAL24_DEMO_AGENT=1` au démarrage sème le hub Oujda démo + `agent@oriental24.ma` (uniquement si manquants, uniquement en mode démo). Le HTML autonome l'embarque d'office (bouton Agent).

## 6 · Alertes de retard (à visualiser, pas d'envoi externe)

Rubrique **Alertes** (menu Admin + Agent) avec quatre groupes recalculés à la demande, seuils réglables dans **Paramètres → Seuils des alertes (heures)** :

- `alert_transit_hours` (défaut 48) : palettes envoyées pas encore arrivées ;
- `alert_partial_hours` (défaut 24) : réceptions partielles non soldées ;
- `alert_unassigned_hours` (défaut 24) : colis **Réceptionné** non affectés à un livreur (annonce ouverte dans le fil par colis).

`0` désactive la catégorie ; plage stricte 0..720 en PATCH (400 sinon). L'agent ne voit que son hub. Les liens mènent droit à la palette concernée ou au colis à affecter. Aucun e-mail ni SMS n'est envoyé : c'est un outil de pilotage interne.

## 7 · API partenaire externe

### Clés (Admin uniquement, dans Clients → Clé API partenaire)

- Création : une seule clé active par société de livraison ; le secret complet **n'est renvoyé qu'une fois** (`O24K-…` + 32 hex) — stocké en SHA-256, jamais en clair.
- Révocation : réponse `changed:true/false`, la clé cesse immédiatement de fonctionner ; une nouvelle clé peut être émise ensuite.

### Endpoints publiés (pas de session, pas de CSRF)

- `GET /api/partner/v1/cities` — villes livrables + frais **applicables à votre contrat** (défauts ou tarifs de la société) ;
- `POST /api/partner/v1/parcels` — création (tracking société, destinataire, téléphone, ville, adresse, COD, produit, note). Rates : 120 req/minute à 403. **`Idempotency-Key` obligatoire** (20–80 `[A-Za-z0-9_-]`) : replay exact rend le même résultat avec `replayed:true`, empreinte différente → 409, duplication de tracking chez vous → 409 avec message explicite (autorisé ailleurs) ;
- `GET /api/partner/v1/parcels/<tracking>` — détail + historique des événements ;
- `GET /api/partner/v1/parcels?updated_since=<ISO>&page=<n>&size=50|100` — liste bornée à la société, `Cache-Control: private, no-store`, updated_since validé strictement (400 si mal formée).

Limites annoncées et imposées : accès à **ses seuls colis**, aucune facturation, aucun accès financier, aucune donnée des autres clients. Les erreurs sont homogènes (`{"error": "…"}`) avec statuts adaptés (401/403/400/404/409).

## Sécurité et intégrité retenues

- 400 JSON partout où la saisie est invalide ; 409 partout où l'état ou l'exclusivité prime (clés d'idempotence, doublons, sessions révoquées, hub inactive pour Agent…).
- Rien n'est supprimé : photos en base avec hash SHA-256 + conversion, dossiers d'incidents, audit de chaque action sous chaque nom.
- Aucune promesse d'intégration bancaire, aucun envoi externe, aucune signature électronique factice.
- Migration additive uniquement ; base existante conservée (revoir `RELEASE-NOTES.md` et les fiches de migration précédentes).

## Validation

- **239 tests Python** (dont `test_reception_extras.py` ×7 et `test_partner_api.py` ×3) : incidents complets, agent/permissions, seuils, tarifs non rétroactifs, clés, idempotence, pagination rapide (filtrage ISO).
- QA navigateur (`qa/reception_extras_workflow.py`) : rôle Agent, déclarations + photos, réponse société, décision endommagé, tarifs et clé API visuels avec appel réel, rubrique Alertes, HTML autonome. Rétro-compatibilité : flux palettes v1.4.15 PASS, HTML standalone PASS.
