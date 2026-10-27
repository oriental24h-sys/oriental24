"""Status for a company's first physical handover to ORIENTAL24.

Only partner-intake paths use this rule. Inter-Hub transfers and seller pickup
flows keep their existing statuses and physical-custody checks.
"""
from ramassage_tracking import central_id


def partner_intake_status(c, parcel_id, hub_id):
    if type(hub_id) is not int or hub_id <= 0 or hub_id != central_id(c):
        return 'Réceptionné'
    company_intake = c.execute('''SELECT 1 FROM parcels p
        JOIN users client ON client.id=p.client_id
        JOIN ops_hubs h ON h.id=? AND h.active=1
        WHERE p.id=? AND client.role='client' AND client.client_type='societe_livraison'
        ''', (hub_id, parcel_id)).fetchone()
    return 'Ramassé' if company_intake else 'Réceptionné'
