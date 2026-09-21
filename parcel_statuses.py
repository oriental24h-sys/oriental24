"""Approved parcel states. New open states never enter closed financial ledgers."""
STATUSES = ['Transit','Reporté','Programmé','Réceptionné','Reçu par le livreur','Livré','Refusé','Intéressé',
            'Créé','Ramassé','Au hub','En livraison','Retourné']
STATUS_HELP = {
 'Transit':'Transport entre agences. Aucun encaissement ni livraison au destinataire.',
 'Reporté':'Livraison différée sans rendez-vous fixé. L’ancien rendez-vous est retiré.',
 'Programmé':'Livraison avec un motif et un rendez-vous futur, heure du Maroc.',
 'Réceptionné':'Réception déclarée en agence, pas chez le destinataire. Aucun COD collecté.',
 'Reçu par le livreur':'Le livreur actuellement affecté déclare avoir pris le colis en charge. Ce n’est pas une livraison.',
 'Livré':'Livraison au destinataire et COD déclaré collecté.',
 'Refusé':'Refus du destinataire. Aucun COD livré ; les frais de refus existants restent applicables.',
 'Intéressé':'Destinataire intéressé, sans confirmation de livraison ni encaissement.',
 'Créé':'Colis enregistré.', 'Ramassé':'Ramassage déclaré.', 'Au hub':'Ancien état conservé : colis au hub.',
 'En livraison':'Tournée de livraison au destinataire.', 'Retourné':'Retour déclaré ; les règles financières existantes sont conservées.'}
DRIVER_TRANSITIONS = {
 'Créé':['Ramassé','Intéressé','Reporté','Programmé'],
 'Ramassé':['Au hub','En livraison','Reçu par le livreur','Intéressé','Reporté','Programmé'],
 'Au hub':['En livraison','Reçu par le livreur','Intéressé','Reporté','Programmé'],
 'Transit':[],
 'Réceptionné':['Reçu par le livreur'],
 'Reçu par le livreur':['En livraison','Intéressé','Reporté','Programmé'],
 'En livraison':['Livré','Programmé','Refusé','Retourné','Reporté','Intéressé'],
 'Programmé':['En livraison','Livré','Refusé','Retourné','Reporté','Intéressé'],
 'Reporté':['Ramassé','Reçu par le livreur','En livraison','Programmé','Intéressé'],
 'Intéressé':['Ramassé','Reçu par le livreur','En livraison','Reporté','Programmé'],
 'Refusé':['Retourné'], 'Livré':[], 'Retourné':[]}
ATTEMPT_SOURCES = ['En livraison','Programmé']
ATTEMPT_OUTCOMES = ['Livré','Programmé','Refusé','Retourné','Reporté']
# Contact/deferred states are deliberately not assigned a physical progress rank.
STATUS_RANK = {'Créé':0,'Ramassé':1,'Au hub':2,'Transit':2,'Réceptionné':2,
               'Reçu par le livreur':3,'En livraison':3,'Programmé':3,'Refusé':4,'Livré':4,'Retourné':5}
def policy():
    return dict(driver_transitions=DRIVER_TRANSITIONS,help=STATUS_HELP,rank=STATUS_RANK,
                attempt_sources=ATTEMPT_SOURCES,attempt_outcomes=ATTEMPT_OUTCOMES)
