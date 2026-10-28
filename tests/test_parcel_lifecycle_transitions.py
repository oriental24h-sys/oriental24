import unittest

from parcel_statuses import DRIVER_TRANSITIONS


class DriverParcelLifecycleTests(unittest.TestCase):
    def test_new_or_closed_parcels_cannot_be_marked_delivered_by_driver(self):
        for status in ('Créé', 'Confirmé', 'Ramassé', 'Au hub', 'Transit',
                       'Réceptionné', 'Refusé', 'Retourné', 'Annulé', 'Livré'):
            with self.subTest(status=status):
                self.assertNotIn('Livré', DRIVER_TRANSITIONS[status])

    def test_delivery_requires_driver_custody_or_active_delivery_attempt(self):
        for status in ('En livraison', 'Programmé', 'Reporté', 'Intéressé'):
            with self.subTest(status=status):
                self.assertIn('Livré', DRIVER_TRANSITIONS[status])

    def test_driver_cannot_skip_hub_intake_or_handoff(self):
        self.assertEqual(DRIVER_TRANSITIONS['Créé'], [])
        self.assertNotIn('Reçu par le livreur', DRIVER_TRANSITIONS['Créé'])
        self.assertEqual(DRIVER_TRANSITIONS['Au hub'], ['Reçu par le livreur'])
        self.assertEqual(DRIVER_TRANSITIONS['Livré'], [])
