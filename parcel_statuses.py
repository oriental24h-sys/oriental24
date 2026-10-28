"""Approved parcel states. New open states never enter closed financial ledgers."""
CENTRAL_RETURN_TRANSIT = 'Vers Hub Central'
STATUSES = [CENTRAL_RETURN_TRANSIT,'Transit','Reporté','Programmé','Réceptionné','Reçu par le livreur','Livré','Refusé','Intéressé',
            'Créé','Confirmé','Ramassé','Au hub','En livraison','Retourné','Annulé']
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
 'Annulé':'Annulation déclarée avec motif (livreur ou admin). Aucun encaissement ; le colis n’entre dans aucun relevé tant qu’il reste annulé. Le livreur peut reprendre cette commande et choisir un autre état autorisé.'}
DRIVER_HUB_ONLY_STATUSES = ('Réceptionné','Retourné')
# Drivers may only move a parcel through operationally valid custody/delivery steps.
# Admin/Hub workflows have their own guarded actions and are not limited by this map.
# In particular, a driver cannot mark a newly created, hub-bound, returned, cancelled,
# or already delivered parcel as delivered without a recorded handoff to the driver.
DRIVER_TRANSITIONS = {
 'Créé': [],
 'Confirmé': ['Ramassé','Annulé'],
 'Ramassé': ['Au hub','Annulé'],
 'Au hub': ['Reçu par le livreur'],
 'Transit': ['Réceptionné'],
 'Réceptionné': ['Reçu par le livreur'],
 'Reçu par le livreur': ['En livraison','Programmé','Reporté','Annulé'],
 'En livraison': ['Livré','Refusé','Intéressé','Programmé','Reporté','Annulé'],
 'Programmé': ['En livraison','Livré','Refusé','Intéressé','Reporté','Annulé'],
 'Reporté': ['Programmé','En livraison','Livré','Refusé','Intéressé','Annulé'],
 'Intéressé': ['Programmé','En livraison','Livré','Refusé','Reporté','Annulé'],
 'Refusé': [],
 'Livré': [],
 'Retourné': [],
 'Annulé': [],
 CENTRAL_RETURN_TRANSIT: [],
}
ATTEMPT_SOURCES = ['En livraison','Programmé']
ATTEMPT_OUTCOMES = ['Livré','Programmé','Refusé','Retourné','Reporté']
# Contact/deferred states are deliberately not assigned a physical progress rank.
STATUS_RANK = {'Créé':0,'Confirmé':0,'Ramassé':1,'Au hub':2,'Transit':2,'Réceptionné':2,
               'Reçu par le livreur':3,'En livraison':3,'Programmé':3,'Refusé':4,'Livré':4,'Retourné':5}
def policy():
    return dict(driver_transitions=DRIVER_TRANSITIONS,help=STATUS_HELP,rank=STATUS_RANK,
                attempt_sources=ATTEMPT_SOURCES,attempt_outcomes=ATTEMPT_OUTCOMES)
