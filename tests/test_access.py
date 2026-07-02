"""Tests T-M29-1 : journal d'acces (governance.identity_access).

Critere backlog : chaque action sensible laisse une trace
(qui/quoi/quand). DoD : test presence de trace.
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from governance import identity_access  # noqa: E402


class AccessLogTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_access.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_log_access_leaves_a_who_what_when_trace(self):
        """DoD : presence de trace - qui, quoi, quand, sur quoi."""
        ts = identity_access.log_access(
            self.conn, "human:pierre", "manual-entry", "EVT:123")

        row = self.conn.execute(
            "SELECT ts, subject, action, target FROM access_log").fetchone()
        self.assertEqual(row, (ts, "human:pierre", "manual-entry", "EVT:123"))
        self.assertTrue(ts)  # le "quand" est toujours renseigne

    def test_explicit_timestamp_is_respected(self):
        identity_access.log_access(self.conn, "human:pierre", "lecture",
                                   "OBJ:1", ts="2028-04-01T00:00:00Z")
        (ts,) = self.conn.execute("SELECT ts FROM access_log").fetchone()
        self.assertEqual(ts, "2028-04-01T00:00:00Z")

    def test_recent_returns_most_recent_first(self):
        identity_access.log_access(self.conn, "human:pierre", "a", "T1",
                                   ts="2028-04-01T00:00:00Z")
        identity_access.log_access(self.conn, "agent:x", "b", "T2",
                                   ts="2028-04-02T00:00:00Z")

        traces = identity_access.recent(self.conn)
        self.assertEqual([t["target"] for t in traces], ["T2", "T1"])

    def test_recent_filters_by_subject_and_action(self):
        identity_access.log_access(self.conn, "human:pierre", "a", "T1")
        identity_access.log_access(self.conn, "agent:x", "b", "T2")

        only_pierre = identity_access.recent(self.conn, subject="human:pierre")
        self.assertEqual(len(only_pierre), 1)
        self.assertEqual(only_pierre[0]["target"], "T1")

        only_b = identity_access.recent(self.conn, action="b")
        self.assertEqual(len(only_b), 1)
        self.assertEqual(only_b[0]["subject"], "agent:x")

    def test_every_sensitive_operation_of_the_mvp_is_wired(self):
        """Verification structurelle : la saisie manuelle (T-M25-5) et la
        confirmation OCR (T-M06-2) appellent bien le journal d'acces."""
        views_src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "experience", "views.py"), encoding="utf-8").read()
        ocr_src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "perception", "parsers", "image_ocr.py"),
            encoding="utf-8").read()
        self.assertIn("identity_access.log_access", views_src)
        self.assertIn("identity_access.log_access", ocr_src)


if __name__ == "__main__":
    unittest.main()
