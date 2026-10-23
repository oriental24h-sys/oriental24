# Correction GPS — Tour de contrôle / Ramassage

## Cause vérifiée
Sur le site publié, la réponse /app portait :
Permissions-Policy: geolocation=(), microphone=(), camera=(self)

geolocation=() interdit la géolocalisation même si Android et le navigateur ont reçu l’autorisation. Le serveur refuse donc l’usage du GPS avant toute transmission des coordonnées.

## Correction
security.py autorise désormais uniquement la géolocalisation de même origine :
Permissions-Policy: geolocation=(self), microphone=(), camera=(self)

Cela ne donne aucune permission à la place de l’utilisateur, n’active pas automatiquement le suivi, n’ouvre pas le microphone et ne change pas les droits de l’API.

## Installation
Base : branche feature/hub-manager-ramassage-palettes, commit 52abbba.
Remplacer uniquement security.py à la racine du dépôt puis redéployer Railway. Les deux fichiers tests sont facultatifs pour l’exécution, utiles pour les régressions.
Compatible avec le ZIP visuel commandes-sans-scroll-horizontal.zip ; aucun de ses fichiers n’est remplacé ici.

Après déploiement :
1. Fermer/réouvrir l’application Livreur, ou recharger sa page afin de recevoir le nouvel en-tête.
2. Garder Position autorisée et la localisation du téléphone active.
3. Dans Présence · Ramassage / véhicule, activer GPS. Si l’interface indique déjà Arrêter GPS, arrêter puis réactiver une fois.
4. Garder l’application ouverte au premier plan. Une transmission réussie affiche « Position GPS réelle transmise » lors de l’activation manuelle.
5. Actualiser Tour de contrôle et utiliser le cadrage des positions si nécessaire.

La permission Android seule ne suffit pas : il faut aussi activer le suivi dans l’application. Le suivi web existant transmet environ toutes les dix secondes tant que l’application reste visible ; ce correctif ne promet pas un suivi en arrière-plan ou écran verrouillé. Sans position reçue, aucun emplacement n’est inventé. Les filtres, les périmètres Hub et les règles d’ancienneté des positions restent inchangés.

## Tests
176 tests Python réussis, incluant réponse Permissions-Policy, publication authentifiée d’une position fictive sur une base temporaire, contrôles session/CSRF et présence du livreur dans map-data Admin.
Chromium : avec permission accordée et coordonnées simulées, l’ancien en-tête bloque effectivement la localisation ; le nouvel en-tête lu depuis l’application la permet.
Aucun point GPS de production n’a été créé/modifié pour ces tests. Aucun test matériel Android réel n’a été exécuté.

Ce ZIP n’a pas été poussé sur GitHub ni déployé sur Railway par l’assistant.
