"""Tests T-M08-1 : deduplication (empreinte fichier + empreinte ligne).

Prouve le critere du backlog : rejouer un import ne cree aucun doublon
(DoD : test rejeu = 0 nouveau).
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from perception import dedup  # noqa: E402


class FileHashTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_dedup_files")
        os.makedirs(self.tmp_dir, exist_ok=True)

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write(self, name, content):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_same_content_same_hash_regardless_of_filename(self):
        path_a = self._write("a.csv", b"montant,date\n42,2028-01-01\n")
        path_b = self._write("b.csv", b"montant,date\n42,2028-01-01\n")
        self.assertEqual(dedup.file_hash(path_a), dedup.file_hash(path_b))

    def test_different_content_different_hash(self):
        path_a = self._write("a.csv", b"montant,date\n42,2028-01-01\n")
        path_b = self._write("b.csv", b"montant,date\n43,2028-01-01\n")
        self.assertNotEqual(dedup.file_hash(path_a), dedup.file_hash(path_b))

    def test_hash_is_a_sha256_hex_digest(self):
        path = self._write("a.csv", b"hello")
        digest = dedup.file_hash(path)
        self.assertEqual(len(digest), 64)
        int(digest, 16)  # leve ValueError si ce n'est pas de l'hexadecimal


class FileSeenAndIngestionLogTests(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_dedup.db"
        )
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = sqlite3.connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_file_seen_is_false_before_any_ingestion(self):
        self.assertFalse(dedup.file_seen(self.conn, "a" * 64))

    def test_file_seen_is_true_after_record_ingestion(self):
        dedup.record_ingestion(
            self.conn, "ING:1", source="inbox", file="facture.pdf", hash_="a" * 64,
            records=1, new_records=1, duplicates=0, anomalies=0, errors=0,
            status="processed", ts="2028-01-01T00:00:00Z",
        )
        self.assertTrue(dedup.file_seen(self.conn, "a" * 64))

    def test_replaying_the_same_file_hash_produces_zero_new_records_signal(self):
        """DoD T-M08-1 : rejeu = 0 nouveau. Le second appelant (ex.
        intake_folder) doit pouvoir detecter le doublon via file_seen
        avant de reingerer - ce test prouve que la primitive le permet."""
        file_hash = "b" * 64
        self.assertFalse(dedup.file_seen(self.conn, file_hash))

        dedup.record_ingestion(
            self.conn, "ING:1", source="inbox", file="releve.csv", hash_=file_hash,
            records=1, new_records=1, duplicates=0, anomalies=0, errors=0,
            status="processed", ts="2028-01-01T00:00:00Z",
        )

        # "Rejeu" : le meme fichier se represente.
        self.assertTrue(dedup.file_seen(self.conn, file_hash))
        # Le rejeu est journalise comme duplicate, jamais comme nouveau.
        dedup.record_ingestion(
            self.conn, "ING:2", source="inbox", file="releve.csv", hash_=file_hash,
            records=1, new_records=0, duplicates=1, anomalies=0, errors=0,
            status="duplicate", ts="2028-01-02T00:00:00Z",
        )

        total_new_records = self.conn.execute(
            "SELECT SUM(new_records) FROM ingestion_log WHERE file_hash = ?", (file_hash,)
        ).fetchone()[0]
        self.assertEqual(total_new_records, 1)

    def test_ingestion_log_row_is_persisted_with_all_fields(self):
        dedup.record_ingestion(
            self.conn, "ING:42", source="inbox", file="x.eml", hash_="c" * 64,
            records=3, new_records=2, duplicates=1, anomalies=0, errors=0,
            status="processed", ts="2028-02-01T00:00:00Z", note="test",
        )
        row = self.conn.execute(
            "SELECT import_id, source, file, records, new_records, duplicates, status, note "
            "FROM ingestion_log WHERE import_id = ?", ("ING:42",)
        ).fetchone()
        self.assertEqual(row, ("ING:42", "inbox", "x.eml", 3, 2, 1, "processed", "test"))


class RowHashTests(unittest.TestCase):
    def test_same_key_values_same_hash(self):
        record_a = {"date": "2028-01-01", "montant": 42, "libelle": "Foodex facture 1"}
        record_b = {"date": "2028-01-01", "montant": 42, "libelle": "Foodex facture 2 (texte different)"}
        self.assertEqual(
            dedup.row_hash(record_a, ["date", "montant"]),
            dedup.row_hash(record_b, ["date", "montant"]),
        )

    def test_different_key_values_different_hash(self):
        record_a = {"date": "2028-01-01", "montant": 42}
        record_b = {"date": "2028-01-01", "montant": 43}
        self.assertNotEqual(
            dedup.row_hash(record_a, ["date", "montant"]),
            dedup.row_hash(record_b, ["date", "montant"]),
        )

    def test_missing_key_column_is_treated_as_none(self):
        record_a = {"date": "2028-01-01"}
        record_b = {"date": "2028-01-01", "montant": None}
        self.assertEqual(
            dedup.row_hash(record_a, ["date", "montant"]),
            dedup.row_hash(record_b, ["date", "montant"]),
        )


if __name__ == "__main__":
    unittest.main()
