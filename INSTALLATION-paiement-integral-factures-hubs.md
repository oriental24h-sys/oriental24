# Factures des Hubs — réception intégrale et état Paid

## Installation

Cette mise à jour s’applique après le ZIP des deux modifications précédentes (factures livreurs du responsable + PDF unifié). Elle ne contient que les fichiers concernés par l’ajout du paiement intégral des factures Hubs, pas le projet complet.

1. Sauvegarder le code et la base SQLite.
2. Copier les fichiers à la racine du projet en conservant les chemins.
3. Redémarrer le service Python. La table des reçus est créée automatiquement ; aucune facture existante n’est supprimée ou recalculée.
4. Recharger le navigateur sans cache.

Les instructions de cette notice remplacent la restriction précédente indiquant que les factures Hubs n’avaient pas d’enregistrement de réception.

## Utilisation Admin

Dans **Facturation → Factures des Hubs → Factures émises**, la colonne **État / réception** affiche l’état et le montant restant à remettre.

- Cliquer sur **Confirmer reçu / Paid**, depuis le tableau ou le détail.
- Le montant est le montant intégral **à remettre par le Hub** inscrit à l’émission : COD moins retenue autorisée en méthode Net, COD intégral en méthode Intégral.
- Indiquer le mode de règlement, la référence du reçu et la date effective ; cocher la confirmation de réception réelle.
- Après confirmation, la facture passe à **Paid**, avec un reste à remettre égal à zéro. L’état est visible dans la liste et le détail chez Admin et chez le responsable du Hub, ainsi que dans le PDF et le CSV. Si la page du responsable est déjà ouverte, utiliser Actualiser pour recharger l’état.

**Aucun paiement partiel :** montant inférieur ou supérieur au montant exact refusé. Les montants et lignes d’origine restent immuables. Le reçu est ajouté séparément et conserve l’Admin auteur, la date de saisie, la date effective, la référence et le mode.

**Périmètre de Paid :** réception intégrale des fonds dus par le Hub à Admin. Une éventuelle commission encore à verser au Hub reste affichée séparément ; elle n’est pas déclarée payée automatiquement. Aucun virement n’est exécuté. Aucun reçu fictif n’est créé pour une facture sans montant à recevoir : elle affiche **Solde nul**.

Les factures déjà émises sont initialement Not Paid si elles ont un montant à recevoir. Aucun règlement ancien n’est déduit automatiquement d’un autre registre. Ne confirmer que les fonds réellement reçus pour cette facture et ne pas déclarer deux fois une même remise dans des registres différents.

## Protections

- Admin uniquement pour confirmer la réception ; le responsable peut consulter uniquement son propre Hub.
- CSRF obligatoire dans l’application réelle.
- Confirmation explicite, référence et date requises ; dates futures refusées.
- Clé d’idempotence et transaction SQLite : réessayer la même confirmation ne double pas le reçu. Une autre tentative sur une facture déjà Paid est refusée.
- Le reçu et le journal d’audit sont enregistrés dans la même transaction. Reçus non modifiables et non supprimables. Aucun bouton de retour à Not Paid ni d’annulation de reçu n’est ajouté par cette modification.
- Pas de changement des autorisations, des paiements clients/livreurs ou de la planification automatique des factures.

## Vérification

**158 tests Python réussis**, dont réception intégrale Net/Intégral, refus des montants partiels ou excessifs, deux requêtes simultanées, répétition idempotente, CSRF réel, audit, PDF/CSV et visibilité propre au Hub. Test JavaScript des états et actions Admin réussi ; vérification syntaxique et `git diff --check` réussis.

Pas de déploiement ni test visuel dans un navigateur réel effectué.
