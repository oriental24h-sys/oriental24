# ORIENTAL24 v1.4.17 — Audit pilotage demandé : 409 des dialogues, blocage des réceptions, CSS partagé

> **Demande utilisateur** : audit complet du module pilotage, sans raccourci —
> corriger les erreurs **409 « aléatoires »** dans les dialogues, couvrir le blocage
> **Réception du colis** pour **tous les utilisateurs** avec enregistrement du **qui/pourquoi**,
> et vérifier que le CSS pilotage est bien un **fichier partagé** (`static/pilotage.css`)
> utilisé de façon identique par le serveur et par la démo HTML.
>
> Tout est **en place, testé et vérifié en navigateur** : 244 tests unitaires + 5 scripts QA navigateur, zéro erreur JS.

---

## 1 · Périmètre de l’audit (tout, sans exception)

| Zone auditée | Fichiers | Résultat |
|---|---|---|
| File & filtres pilotage | `static/pilotage.js` (354 lignes relues) | Files par rôle, filtres combinés, pagination, chips, CSV formules-safe : **conformes** |
| Styles pilotage | `static/pilotage.css` (322 lignes) | **Fichier réel partagé** : charge par `templates/index.html` ET injecté par `offline/build_html.py` — mêmes styles des deux côtés ✔ |
| Dialogues & verrous de version | `app.js`, `parcel-state.js`, `parcel-city.js`, `parcel-contacts.js`, `driver-workspace.js`, `driver-finance.js`, `driver-invoice-print.js`, `workspace-ui.js`, `logistics.js`, `partner-palettes.js`, `reception-extras.js`, `offline/adapter.js` | **21 appels passant un `revision` figé** identifiés (cf. §2) |
| Réceptions physiques & blocages | `partner_palettes.py`, `offline/partner_palettes.js`, `security.py`, `app.py` (`user()`), `auth()` | Voir §3 |
| QA historique pilotage | `qa/pilotage_check.py` + 7 rapports `*-pilotage-*.txt` | Tous **PASS** re-vérifiés ce jour |
| Tests ignorés | recherche exhaustive `skip`/`skipTest` dans les 21 fichiers de test | **Aucun test ignoré** ; 239 + 5 = **244 tests** |
| Build hors-ligne | `offline/build_html.py` (54 lignes) | Régénéré : 2 775 234 octets, mêmes fichiers `static/*.css`/`*.js` |

## 2 · Les 409 « aléatoires » des dialogues — cause racine et correctif

**Cause racine.** Chaque dialogue capturait le `revision` (ou `ops_revision`, `driver_revision`…) **au moment de son ouverture**, posé dans le formulaire. Entre-temps, **toute autre écriture légitime** — un scan par un agent, une affectation, une annonce vue ailleurs, la même fiche ouverte dans un deuxième onglet — incrémentait le compteur côté serveur. Le POSTParti avec l’ancienne version recevait donc un **409 « modifiée/changée »** qui « tombait de nulle part » du point de vue de l’utilisateur, et la saisie du dialogue était perdue.

**Correctif — `api409(send, fetchFresh)`** (dans `app.js`, ~15 lignes, partagé serveur + HTML autonome) :
1. le premier envoi part avec la version courante ;
2. si le serveur répond un **conflit de version** (messages `modifié/changé/Actualisez/Rechargez/Rouvrez/Recréez/Version invalide`), `api409` **relit la fiche**, remonte la version à jour et **renvoie une fois** l’intention déclarée ;
3. l’utilisateur est informé (« données actualisées, enregistrement repris ») ; si le conflit persiste **après** la relecture, l’erreur originale est affichée — le verrou optimiste reste un garde-fou, on ne contourne jamais un vrai conflit.

Appliqué aux 21 dialogues concernés : statut colis `changeStatus`, parsemer d’état (`parcel-state`, les 3 chemins), menu motif, changement de ville, contact support + affectation support, annonces, barème livreur, coordonnées facture, fiche & accès livreur (`driver-workspace`), tentatives `opsAttemptForm`, dispatch/cancel de documents (`opsDocAction`), dossiers administratifs (2 dialogues), réception scan par scan et dispatch/cancel de palettes, clôture avec écarts.

**Cas traité à part** — `receive-all` (réception en masse) : la liste confirmée *physiquement* peut changer pendant que la fenêtre est ouverte (un autre scan, un écart déclaré). On ne rejoue **pas** à l’aveugle : le dialogue **se recharge avec la liste du moment** (toast « la liste a changé »), l’utilisateur re-contrôle **les colis réellement restants** avant de reconfirmer. Vérifié en navigateur (capture `qa/v1417-receiveall-conflict.png`).

## 3 · Blocage « Réception du colis » pour TOUS — avec qui/pourquoi enregistrés

Le garde physique d’une palette était déjà correct côté Admin/agent du bon hub ; mais les **autres refus** étaient des rejets « mornes » : 403 pour un rôle non physique, 404 pour un agent d’un autre hub — sans trace de qui avait tenté. Désormais, **toute tentative de réception refusée est enregistrée** dans l’historique `ops_audit` de la palette, avec l’acteur et la raison exacte :

| Utilisateur | Réponse (inchangée) | Enregistrement nouveau |
|---|---|---|
| **Client société propriétaire** | 403 « Réception physique réservée à Admin et aux agents de réception. » | `Réception refusée` · reason `Rôle non autorisé à la réception physique`, `actor_role:client` |
| **Livreur** | 403 idem (nouvellement couvert par le garde) | `Réception refusée` · `actor_role:livreur` |
| **Agent d’un autre hub** | 404 « Palette introuvable pour votre hub. » — **aucune fuite d’existence** (le GET reste 404 dès la liste) | `Réception refusée` · reason `Agent rattaché à un autre hub`, `actor_hub_id`, `palette_hub_id` |
| **Agent de bon hub** | 200, réception normale | historique inchangé |
| Document inexistant | 404 — **aucune ligne orpheline** dans l’audit | — |
| Compte désactivé (tout rôle) | session **révoquée immédiatement** (`security_revoke_user`) → 401 global | système global, déjà en place |

Points techniques : le refus est enregistré **hors transaction qui va échouer** (sinon le rollback supprimerait la trace), **avant** toute fuite d’information (l’agent hors hub ne voit jamais la palette — vérifié), et l’adapter hors-ligne (`offline/partner_palettes.js`) produit les **mêmes messages + mêmes lignes d’audit** : l’autonome HTML reste à parité (*« HTML li tajriba »*).

## 4 · CSS partagé — confirmé, pas déplacé

`static/pilotage.css` est déjà **la seule source** des styles pilotage :
* serveur : `<link rel="stylesheet" href="/static/pilotage.css" />` (templates/index.html) ;
* autonome : `offline/build_html.py` lit **le même fichier** et l’injecte dans le HTML unique.
Il n’y a donc rien à « extraire » : la duplication qu’on craignait n’existe pas. L’audit l’a confirmé ligne à ligne (322 lignes, médias 1100/720 px), et les vues serveur/HTML passent le même `pilotage_check`.

## 5 · Preuves

| Vérification | Résultat |
|---|---|
| Suite unitaire complète | **244 tests, OK** (239 précédents + `test_reception_guard_audit`, 5 nouveaux) |
| `qa/pilotage_1417_workflow.py` (nouveau) | PASS — refus rôle/hub enregistrés, 404 sans fuite, conflit receive-all secouru en navigateur, autonome embarqué, **zéro erreur JS** |
| `qa/pilotage_check.py` | PASS (files rôles, filtres combinés, CSV formule, accent insensible, mobile) |
| `qa/partner_palettes_workflow.py` | PASS |
| `qa/reception_extras_workflow.py` | PASS |
| `qa/offline_html_check.py` | PASS (fichier autonome régénéré) |
| Tests ignorant | **0** — `grep -r skip/skipTest` sur les 21 fichiers de test |
