"""Tests T-CONN-1 : modules connecteurs inertes.

Critere backlog : appeler un connecteur desactive ne produit jamais de
fausse donnee ; il demande un fichier/depot a la place. DoD : test
prouve l'inertie (aucune donnee simulee).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
import sqlite3  # noqa: E402
from connectors_disabled import (  # noqa: E402
    ConnectorDisabledError, accounting_api, bank_api, deliveroo_api,
    meta_api, uber_eats_api,
)

ALL_CONNECTORS = (bank_api, uber_eats_api, deliveroo_api, meta_api, accounting_api)


class DisabledConnectorsTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_disabled.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_every_connector_is_disabled(self):
        for connector in ALL_CONNECTORS:
            with self.subTest(connector=connector.CONNECTOR_NAME):
                self.assertFalse(connector.is_enabled())

    def test_fetch_raises_connecteur_non_active(self):
        for connector in ALL_CONNECTORS:
            with self.subTest(connector=connector.CONNECTOR_NAME):
                with self.assertRaises(ConnectorDisabledError) as ctx:
                    connector.fetch(self.conn)
                self.assertIn("connecteur non activé", str(ctx.exception))

    def test_the_error_asks_for_a_file_deposit_instead(self):
        """Critere backlog : il demande un fichier/depot a la place."""
        for connector in ALL_CONNECTORS:
            with self.subTest(connector=connector.CONNECTOR_NAME):
                with self.assertRaises(ConnectorDisabledError) as ctx:
                    connector.fetch(self.conn)
                message = str(ctx.exception)
                self.assertIn("data/inbox/", message)
                self.assertIn("Déposez", message)

    def test_calling_a_disabled_connector_never_produces_any_data(self):
        """DoD : inertie prouvee - aucune donnee simulee, aucune ecriture
        nulle part (journal, anomalies, ingestion, sources)."""
        for connector in ALL_CONNECTORS:
            try:
                connector.fetch(self.conn)
            except ConnectorDisabledError:
                pass

        for table in ("events", "anomalies", "ingestion_log", "objects",
                      "links", "kpi", "sources"):
            with self.subTest(table=table):
                count = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                self.assertEqual(count, 0)

    def test_each_connector_declares_its_future_ingestion_contract(self):
        """L'activation future = brancher le module sur la passerelle M04
        sans rien changer d'autre : le contrat (type d'evenement produit)
        est deja declare."""
        for connector in ALL_CONNECTORS:
            with self.subTest(connector=connector.CONNECTOR_NAME):
                self.assertTrue(connector.EVENT_TYPE.startswith("PERCEPTION."))

    def test_connectors_import_no_network_module(self):
        """Zero appel reseau, meme accidentel : aucun module reseau n'est
        importe par le paquet."""
        base = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "connectors_disabled")
        for name in sorted(os.listdir(base)):
            if not name.endswith(".py"):
                continue
            source = open(os.path.join(base, name), encoding="utf-8").read()
            for forbidden in ("urllib", "http.client", "requests", "socket"):
                self.assertNotIn(forbidden, source,
                                 f"{name} importe un module reseau interdit")


if __name__ == "__main__":
    unittest.main()
