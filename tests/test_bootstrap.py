"""Tests T-M00-1 : arborescence + DB vide + serveur local qui demarre.

Utilise unittest (stdlib) : le MVP tourne "aujourd'hui, sans aucune API,
sans aucune cle" (Constitution) - zero dependance de test a installer.
"""
import http.client
import os
import sqlite3
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402


class InitDbTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_bootstrap.db"
        )
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_creates_all_tables(self):
        eos_app.init_db(self.db_path)

        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        finally:
            conn.close()

        table_names = {row[0] for row in rows}
        for table in eos_app.ALL_TABLES:
            self.assertIn(table, table_names)

    def test_is_idempotent(self):
        eos_app.init_db(self.db_path)
        eos_app.init_db(self.db_path)  # ne doit pas lever d'erreur

        conn = sqlite3.connect(self.db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, len(eos_app.ALL_TABLES))


class ServerTests(unittest.TestCase):
    def test_server_responds_on_localhost(self):
        server = eos_app.build_server(host="127.0.0.1", port=0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/")
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
