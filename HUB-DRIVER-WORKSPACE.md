# Livreurs de mon Hub — scan, récupération et relevés

Base : `feature/hub-manager-ramassage-palettes`.

## Interface
- Réutilisation du tableau Admin : Équipe, Blacklist, Archives, recherche, actualisation et actions par ligne.
- Création, modification et accès utilisent les routes locales existantes ; le manager ne peut pas changer le Hub ou l’équipe du livreur.
- Remise physique et récupération : lecteur USB/Bluetooth, saisie ou caméra via le scanner existant, validation d’un lot atomique.
- Facture : aperçu, confirmation et impression / enregistrement PDF via le navigateur. Même moteur de relevés que l’Admin, pas de second système financier.
- Consultation ultérieure depuis « Relevés livreurs ».

## Périmètre serveur
- Hub actif obligatoire ; livreur rattaché au Hub du responsable.
- Affectation : colis physiquement présent dans ce Hub. Les nouvelles remises enregistrent le Hub de départ même pour un colis pré-affecté au même livreur.
- Récupération : colis du livreur local présent dans ce Hub ou en tournée avec une dernière affectation tracée depuis ce Hub. Le Hub de retour est imposé côté serveur.
- Refusé/Retourné : résultat et attribution financière conservés. Livré : récupération refusée, comme chez Admin.
- Relevés : uniquement les lignes clôturées attribuables au Hub par la tentative de clôture enregistrée, sinon par la dernière affectation. Les historiques sans preuve de Hub restent à traiter par Admin.
- Accès au détail d’un relevé : snapshot Hub correspondant et aucune ligne étrangère/non attribuable.
- Conservation des contrôles CSRF, versions, transactions atomiques, clés d’idempotence, verrous et journal d’audit.
- Barèmes, annulations de relevés et écritures de paiement restent Admin-only. Générer un relevé n’encaisse pas de COD.

## Vérification
`python -m unittest discover -s tests -q` : 92 tests réussis, dont 23 nouveaux tests HTTP sur base isolée.

Scénario navigateur vérifié : recherche d’un livreur, scan et confirmation, récupération, aperçu et génération de facture, présence de l’impression, absence des actions Admin de règlement/annulation, onglets et affichage mobile. Aucune erreur JavaScript relevée dans ce parcours. Caméra physique et imprimante non testées.

Aucune dépendance applicative ajoutée. Le suivi des retours ajoute automatiquement la colonne nullable `ops_document_lines.return_transit_status` au démarrage (migration idempotente). Redémarrer le serveur après mise à jour. Les données de démonstration locales ne doivent pas remplacer la base de production.

## Modification des situations par le responsable de Hub

- Depuis la liste **Colis reçus au Hub** ou la fiche de la commande : le statut devient un menu de modification.
- Le responsable peut modifier une commande physiquement présente dans son Hub actif, sauf si son état actuel est **Livré** ou **Retourné**.
- Il peut choisir Livré/Retourné pour une commande ouverte ; une confirmation avertit que cette opération devient irréversible pour son rôle. L’Admin conserve ses droits de correction existants.
- Les verrous de facture/relevé/document actif, la version du colis, le CSRF, la programmation avec motif et rendez-vous, et le code client OTP restent contrôlés côté serveur.
- La permission ne donne aucun droit supplémentaire sur le prix, le livreur, le Hub, les coordonnées ou la note de suivi seule. Chaque changement est historisé et ajouté au journal d’audit.
- Le périmètre de visibilité des commandes n’est pas élargi aux colis en transit ou dans un autre Hub.
- Vérification navigateur supplémentaire : modification effective vers Intéressé, absence de bouton sur Livré/Retourné, avertissement avant clôture, fiche et menu mobile, aucune erreur JavaScript relevée.

## Retour scanné vers le Hub Central

- La création de la palette ne change pas la situation du colis.
- Pour `palette_purpose=return_to_central`, chaque **scan de sortie** enregistre `Vers Hub Central` et retire la localisation physique du Hub source.
- Chaque **scan de réception** par Admin ou le manager du Hub destinataire confirme `Retourné` et la présence physique au Hub Central. En réception partielle, seuls les colis réellement scannés changent de situation.
- Une référence hors manifeste, une réception avant départ, un autre Hub ou un état altéré sont refusés. Les scans répétés ne créent pas de doublon.
- Le nouvel état n’est pas sélectionnable manuellement. Une palette active conserve les verrous opérationnels existants.
- Les montants et lignes des factures/relevés déjà émis ne sont pas réécrits. Les futurs relevés utilisent les règles existantes et l’état courant ; un colis `Vers Hub Central` n’est pas un nouveau retour clôturé à facturer.
- Le tri ultérieur Central → Hub d’origine conserve `Retourné`. Les transferts standards gardent `Transit` → `Réceptionné`. Le flux distinct de remise au vendeur n’est pas modifié.
- Les anciens retours déjà en transit, sans marqueur `return_transit_status`, restent réceptionnables ; aucune réécriture automatique de leur historique au démarrage.
- Interface : situation actuelle visible dans le manifeste (en plus du statut initial), messages de scan adaptés et nouveau filtre de statut.
- Parcours navigateur vérifié : départ depuis le compte Hub, lecture de `Vers Hub Central` dans le compte Admin, réception avec le compte Hub Central, affichage de `Retourné`. Aucune erreur JavaScript dans ce parcours.

## Scan de sortie des transferts : contrôle ville / Hub

- Pour un transfert standard sortant vers un Hub secondaire, le serveur vérifie à chaque scan que `cities.hub_id` correspond au Hub destinataire actif.
- Ville sans rattachement, mauvais Hub ou destination inactive : aucune écriture de scan, de statut ou de départ ; message de refus demandant de choisir un autre Hub.
- Un code hors manifeste peut recevoir l’explication de ville seulement si le colis est physiquement au Hub source ; aucun renseignement sur un colis d’un autre Hub.
- Le contrôle couvre également l’ancien départ global Admin. Les retours physiques et le transit entrant vers le Central gardent leurs règles distinctes.
- Deux sons : succès aigu après un nouveau scan confirmé par le serveur ; refus grave pour erreur ou doublon. Notification courte, champ prêt pour le scan suivant et interrupteur sonore. Activation Web Audio dans le geste utilisateur avant l’appel réseau.
- Vérifié : 4 nouveaux tests de périmètre, mauvais rattachement, Hub inactif, idempotence et absence d’écriture sur refus. Parcours navigateur mauvais code puis bon code : notification correcte, signaux `err` puis `ok`, AudioContext actif, aucune erreur JavaScript. Écoute sur matériel réel non effectuée.
