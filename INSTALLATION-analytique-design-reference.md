# Analytique — refonte visuelle selon les captures de référence

Cette mise à jour corrige la présentation de la section Analytique existante. Elle s’applique après `ORIENTAL24-analytique-responsable-hub.zip`, déjà vérifié sur GitHub. Elle ne contient pas le projet complet.

## Installation

1. Sauvegarder les fichiers existants.
2. Copier les fichiers du ZIP dans le projet en conservant les chemins.
3. Nouveau fichier indispensable : `static/hub-manager-analytics.css`.
4. Redéployer / redémarrer le service pour recharger le template, puis effectuer un rechargement navigateur sans cache.

## Présentation

Identité ORIENTAL24 conservée : bleu nuit et orange. La barre principale de navigation, les autres pages et le backend ne sont pas modifiés.

- Titres distincts : Activité des Hubs, Analyse des Livreurs, Activité Quotidienne des Livreurs.
- Filtres regroupés dans un bandeau compact : dates, livreur, actualisation, risque, export et choix de vue ; raccourcis de période sur une deuxième ligne.
- Cartes d’indicateurs avec valeur, sous-texte et pictogramme dans un cercle coloré, disposées comme dans les références.
- Progression globale avec grand pourcentage, fraction traité / assigné et barre traité / non traité.
- Analyse livreurs : second indicateur du taux de livraison, grille de trois cartes sur grand écran, icône de classement, cercle de progression, trois cases Livrés / Retournés / Assignés, zone En attente cliquable et taux en bas de carte.
- Activité Hub : même carte de progression et zone En attente ouvrant les colis concernés.
- Matrice quotidienne : en-têtes jour/date, noms fixes lors du défilement horizontal, badges de jours, intensité orange selon le volume, légende, défilement interne et détails au clic.
- Boutons Cartes / Liste et Matrice / Liste, filtres Jamais travaillé et À risque, CSV conservés.
- Adaptation téléphone : cartes en une colonne, indicateurs sur deux colonnes et défilement de la matrice à l’intérieur de son bloc.

Il ne s’agit pas d’une copie de la marque du site de référence : le logo, la navigation et l’identité ORIENTAL24 sont conservés, conformément au choix demandé.

## Calculs et sécurité inchangés

Aucun changement au backend, aux formules d’assignation/traitement, au périmètre du Hub, aux factures ou aux paiements. Les chiffres affichés proviennent de la même API. Un traitement Reporté/Injoignable ne signifie pas une livraison. Un jour sans affectation ne prouve pas une absence.

## Vérifications locales

- 172 tests Python de régression réussis.
- Tests JavaScript de la nouvelle structure, cercles, cartes, matrice, vue liste, filtres, détails et CSV réussis.
- Régression JavaScript factures et vérification syntaxique réussies ; `git diff --check` réussi.
- Parcours exécuté dans Chromium sur une base locale avec données fictives : les trois vues, ouverture du détail d’un jour, bascule en liste, téléchargement CSV et absence de débordement horizontal de la page sur téléphone 390 px. Aucune erreur JavaScript pendant ce parcours.
- Captures d’aperçu produites avec ces données fictives. Aucun déploiement ni modification de GitHub effectué.
