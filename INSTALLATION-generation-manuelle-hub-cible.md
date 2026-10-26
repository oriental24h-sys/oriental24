# Génération manuelle des factures pour un Hub précis

## Fonction

Dans **Facturation des Hubs**, le bouton **Prévisualiser / générer maintenant** demande maintenant le périmètre :

- **Tous les Hubs** : conserve la génération groupée existante.
- **Un seul Hub** : prévisualise uniquement les commandes facturables de ce Hub et, après confirmation, émet uniquement sa facture.

La génération automatique quotidienne reste inchangée et continue de traiter tous les Hubs éligibles. Le choix manuel n’émet pas de paiement et ne modifie ni le barème ni les factures déjà créées. Les commandes non encore facturées des autres Hubs restent disponibles pour une génération future.

La prévisualisation et la confirmation sont toutes deux filtrées côté serveur par le Hub actif sélectionné; le serveur recalcule et valide l’instantané avant émission. Les factures déjà facturées restent exclues par les règles existantes.

## Fichiers

- `hub_billing.py`
- `static/hub-billing.js`
- `templates/index.html`
- `tests/test_hub_billing.py`
- `tests/frontend/test_hub_billing.cjs`

## Installation et vérification

Remplacer les fichiers correspondants, redémarrer l’application et faire un rechargement forcé du navigateur. Aucune migration de base n’est nécessaire.

Vérifier avec **Prévisualiser / générer maintenant → Un seul Hub**, contrôler que le récapitulatif ne liste que ce Hub, puis confirmer sur un cas de test. Vérifier que les colis d’un autre Hub restent disponibles ensuite. Les tests automatisés locaux ont été exécutés; aucune installation ni génération de facture en production n’a été effectuée ici.

Commandes :

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest tests.test_hub_billing -q
node tests/frontend/test_hub_billing.cjs
```
