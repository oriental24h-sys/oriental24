# Barèmes de commission par ville et par Hub

## Résultat

Dans **Facturation → Barèmes des Hubs**, chaque Hub affiche ses villes rattachées. **Configurer le barème** ouvre un formulaire comportant, pour chaque ville, trois montants en MAD : colis Livré, Retourné et Refusé. La méthode de règlement (Net ou COD intégral / commission séparée) reste commune au Hub.

À la prévisualisation et à l’émission, chaque colis clôturé utilise le tarif correspondant à **son Hub opérationnel attesté et à sa ville**. Le tarif est figé sur chaque ligne de facture. Les factures déjà émises ne sont pas modifiées.

## Règles de transition et villes sans tarif

- Les anciens barèmes communs du Hub continuent de s’appliquer tant que l’administrateur n’a pas enregistré son premier barème par ville. Cela évite de changer le calcul existant pendant la transition.
- Le premier enregistrement en mode par ville exige un tarif explicite pour **chaque ville actuellement rattachée** au Hub. `0` est un tarif explicite valable.
- Après activation du mode par ville, une nouvelle ville sans barème (ou une commande sans ville) est signalée dans l’aperçu et le résultat de génération. Les commandes correspondantes sont laissées hors facture — elles ne reçoivent pas un prix implicite et restent éligibles à une prochaine génération après configuration.
- Une ville réaffectée à un autre Hub est vérifiée contre le rattachement actuel au moment de l’enregistrement; le formulaire périmé est rejeté. Une nouvelle génération utilise les tarifs actuels; les documents déjà émis gardent leur instantané.
- La ville de destination ne détermine jamais le Hub financeur : les règles existantes de preuve du Hub opérationnel sont inchangées.

## Fichiers de cette modification

- `hub_billing.py` — tables additives pour le mode par ville, validation de la liste des villes, tarification par ligne, avertissements de prévisualisation et sauvegarde dans le résultat des exécutions.
- `static/hub-billing.js` — formulaire par ville dans la section existante, compteur des barèmes, avertissements.
- `templates/index.html` — cache-buster du JavaScript.
- `tests/test_hub_billing.py` et `tests/frontend/test_hub_billing.cjs` — tests backend et interface.

Aucune migration manuelle n’est nécessaire : les nouvelles tables sont créées de manière additive lors de l’initialisation du module. La colonne `cities.hub_id` doit toutefois être présente et correctement renseignée par la fonction de gestion des villes/Hubs déjà déployée. Vérifier les rattachements dans l’administration avant de saisir les montants.

## Installation / vérification

1. Sauvegarder la base et déployer les fichiers inclus dans l’archive à la place des versions correspondantes.
2. Redémarrer l’application, puis actualiser le navigateur sans cache.
3. Ouvrir **Facturation → Barèmes des Hubs**. Vérifier qu’un Hub de test affiche toutes ses villes correctes.
4. Pour un Hub pilote, renseigner ses montants pour les trois états et la méthode Net/Intégral, puis enregistrer.
5. Prévisualiser une prochaine émission et confirmer que les commissions correspondent aux villes respectives; vérifier également qu’une ville non configurée apparaît dans l’avertissement et que ses colis ne sont pas émis.
6. Les tests automatisés locaux ont été exécutés; aucun déploiement en production ni contrôle des rattachements réels n’a été effectué dans le cadre de cette livraison.

## Tests

`PYTHONPATH=.:tests .venv/bin/python -m unittest tests.test_hub_billing -q`

`node tests/frontend/test_hub_billing.cjs`
