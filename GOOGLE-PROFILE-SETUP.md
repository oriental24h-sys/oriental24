# Profil clients — configuration et déploiement

## Fonctionnalités locales

- Profils Vendeur et Société : banque/RIB/logo existants réutilisés, sans duplication.
- CIN, ville, site web ; adresse et ICE/identifiant légal reliés au dossier administratif existant. Toute modification de ces deux derniers champs remet le dossier en brouillon.
- Langue FR/EN/AR persistée par compte.
- Préférences effectives des notifications internes de statut et de règlement. Aucun SMS, WhatsApp ou e-mail n'est envoyé. Les alertes de sécurité et les autres types de notifications restent actifs.
- Solde calculé à partir des factures et des règlements réels du compte, avec séparation des montants à verser et à payer. Aucune taxe estimée inventée.
- Contacts issus uniquement des paramètres publics de l'administration. Les informations des captures de référence ne sont pas utilisées.

## Google : configuration obligatoire avant activation

Les boutons restent désactivés tant que les trois variables ci-dessous ne sont pas configurées. Aucun secret ne doit être placé dans GitHub, dans un ZIP, dans le navigateur ou dans une conversation.

1. Dans Google Cloud, choisir/créer un projet et activer **Google Sheets API**.
2. Configurer l'écran de consentement OAuth et ses utilisateurs de test, si le projet est en mode test. Pour un accès public, suivre les exigences de publication/vérification de Google.
3. Créer un client OAuth de type **Application Web**.
4. Ajouter l'URI de redirection autorisé exact :
   `https://VOTRE-DOMAINE/google/callback`
   Exemple pour le domaine montré dans la capture :
   `https://web-production-a3fb6.up.railway.app/google/callback`
   Vérifier que ce domaine est toujours celui du service déployé.
5. Dans **Railway → Variables** du service, définir :
   - `GOOGLE_CLIENT_ID` : identifiant du client OAuth Web.
   - `GOOGLE_CLIENT_SECRET` : secret du client OAuth, uniquement côté serveur.
   - `GOOGLE_REDIRECT_URI` : exactement la même URL HTTPS que celle déclarée dans Google Cloud.
6. Conserver le `SECRET_KEY` de production stable : les jetons Google persistés sont chiffrés avec une clé dérivée de cette clé serveur. Une rotation nécessite de réassocier les comptes Google.
7. Déployer tous les fichiers du ZIP, notamment `requirements.txt`, puis vérifier le démarrage du service.

## Utilisation

1. Se connecter normalement à ORIENTAL24 avec son mot de passe.
2. Ouvrir **Mon profil → Compte Google → Associer mon compte Google**.
3. Confirmer son mot de passe ORIENTAL24 puis donner son consentement sur Google.
4. Les permissions demandées sont `openid`, `email` et `spreadsheets.readonly`. Aucune écriture dans les feuilles.
5. La connexion Google ultérieure est autorisée **uniquement pour un compte déjà associé**. Aucun compte ORIENTAL24 n'est créé et aucune liaison n'est faite par simple correspondance d'e-mail.
6. Pour importer : utiliser les en-têtes du modèle ORIENTAL24 disponible sur le profil. Mettre les téléphones et trackings au format texte pour conserver les zéros.
7. Donner accès en lecture à la feuille au compte Google associé (ou utiliser sa propre feuille). Aucun compte de service tiers ni publication publique n'est requis.
8. Saisir l'ID/URL et le nom exact de l'onglet, puis **Prévisualiser depuis Google Sheets**. La prévisualisation utilise les mêmes contrôles que l'import CSV/Excel, puis la confirmation habituelle. Limite 500 commandes / 2 Mo. Les doublons et le périmètre du compte restent contrôlés.
9. Dissocier efface les jetons conservés par ORIENTAL24 et empêche les futures connexions Google. Le mot de passe continue de fonctionner. Pour retirer également le consentement Google, utiliser les paramètres de sécurité du compte Google.

## Tests et limites de validation

Les parcours locaux ont été testés pour les deux types de clients et sur mobile. Les échanges OAuth/Sheets ont été testés avec des réponses Google simulées : état/nonce, comptes associés, chiffrement, limites, périmètre et import sans création avant confirmation.
**Aucun échange Google réel n'a été effectué sans vos identifiants OAuth et votre consentement.** Après configuration, tester une petite feuille privée (1 ou 2 commandes fictives) avant tout import réel.

Les sessions et données restent dans la base SQLite persistante existante. Sauvegarder le volume/base avant le déploiement, sans le remplacer par une base de démonstration.
