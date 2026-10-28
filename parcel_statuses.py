"""Approved parcel states. New open states never enter closed financial ledgers."""
CENTRAL_RETURN_TRANSIT = 'Vers Hub Central'
# Commande avec échange : reprise automatique du colis chez le destinataire.
EXCHANGE_TO_RECOVER = 'Échange à récupérer'
EXCHANGE_RECEIVED = 'Échange Réceptionné'
EXCHANGE_STATUSES = (EXCHANGE_TO_RECOVER, EXCHANGE_RECEIVED)
STATUSES = [CENTRAL_RETURN_TRANSIT,'Transit','Reporté','Programmé','Réceptionné','Reçu par le livreur','Livré','Refusé','Intéressé',
            'Créé','Confirmé','Ramassé','Au hub','En livraison','Retourné','Annulé',
            EXCHANGE_TO_RECOVER, EXCHANGE_RECEIVED]
STATUS_HELP = {
 CENTRAL_RETURN_TRANSIT:'État de transit d’un retour (obsolète, conservé pour l’historique). Les retours ne modifient plus le statut de la commande ; leur état (envoyé / reçu en entrepôt) est suivi séparément.',
 'Transit':'Transport entre agences. Aucun encaissement ni livraison au destinataire.',
 'Reporté':'Livraison différée, avec une date de report facultative. Sans date de report, l’ancien rendez-vous est retiré.',
 'Programmé':'Livraison avec un motif et un rendez-vous futur, heure du Maroc.',
 'Réceptionné':'Réception déclarée en agence, pas chez le destinataire. Aucun COD collecté.',
 'Reçu par le livreur':'Le livreur actuellement affecté déclare avoir pris le colis en charge. Ce n’est pas une livraison.',
 'Livré':'Livraison au destinataire et COD déclaré collecté.',
 'Refusé':'Refus du destinataire. Aucun COD livré ; les frais de refus existants restent applicables.',
 'Intéressé':'Destinataire intéressé, sans confirmation de livraison ni encaissement.',
 'Créé':'Colis enregistré.',
 'Confirmé':'Demande de ramassage validée par le client ; le colis attend son enlèvement puis sa réception scannée au Hub.',
 'Ramassé':'Ramassage déclaré.', 'Au hub':'Ancien état conservé : colis au hub.',
 'En livraison':'Tournée de livraison au destinataire.', 'Retourné':'Retour déclaré ; les règles financières existantes sont conservées.',
 EXCHANGE_TO_RECOVER:'Commande de reprise créée automatiquement après une livraison avec échange. Le livreur doit récupérer l’ancien article chez le destinataire et le remettre au Hub. Aucun COD.',
 EXCHANGE_RECEIVED:'Colis de reprise physiquement réceptionné au Hub par le responsable. Il ne dépend plus du livreur et repart par le circuit retour vers le vendeur.',
 'Annulé':'Annulation déclarée avec motif (livreur ou admin). Aucun encaissement ; le colis n’entre dans aucun relevé tant qu’il reste annulé. Le livreur peut reprendre cette commande et choisir un autre état autorisé.'}
DRIVER_HUB_ONLY_STATUSES = ('Réceptionné','Retourné')
# Courier choices are independent of the previous state. Delivered alone is terminal.
# Keep the existing courier vocabulary (not creation/confirmation/internal transit states).
DRIVER_STATUS_TARGETS = ['Reporté','Programmé','Reçu par le livreur','Livré','Refusé',
                         'Intéressé','Ramassé','Au hub','En livraison','Annulé']
DRIVER_TRANSITIONS = {source:[] if source=='Livré' else [s for s in DRIVER_STATUS_TARGETS if s!=source]
                      for source in STATUSES}
# La reprise après échange n'est jamais pilotée par le livreur : il la remet au Hub.
for _exchange_status in EXCHANGE_STATUSES:
    DRIVER_TRANSITIONS[_exchange_status] = []
ATTEMPT_SOURCES = ['En livraison','Programmé']
ATTEMPT_OUTCOMES = ['Livré','Programmé','Refusé','Retourné','Reporté']
# Contact/deferred states are deliberately not assigned a physical progress rank.
STATUS_RANK = {'Créé':0,'Confirmé':0,'Ramassé':1,'Au hub':2,'Transit':2,'Réceptionné':2,
               'Reçu par le livreur':3,'En livraison':3,'Programmé':3,'Refusé':4,'Livré':4,'Retourné':5,
               EXCHANGE_TO_RECOVER:1,EXCHANGE_RECEIVED:5}
def policy():
    return dict(driver_transitions=DRIVER_TRANSITIONS,help=STATUS_HELP,rank=STATUS_RANK,
                attempt_sources=ATTEMPT_SOURCES,attempt_outcomes=ATTEMPT_OUTCOMES)
