"""Enterprise OS - serveur local + orchestrateur (boucle de synchro).

Sprint 1 / T-M00-1 (amorcage) : arborescence du projet, schema SQLite complet
(les deux patrimoines + toutes les projections du backlog), et un serveur
HTTP local minimal (stdlib uniquement, aucune dependance externe, aucun
appel reseau sortant - conforme a la Constitution : zero API, zero cloud).

La boucle de synchronisation vivante (poll inbox -> pipeline -> graphe ->
calcul -> vues) est batie plus tard (T-M00-3) ; ce fichier ne fait
aujourd'hui que demarrer le socle.
"""
import argparse
import http.server
import os
import sqlite3

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "eos.db")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# Schema complet des deux patrimoines (events, rules) + projections
# reconstructibles (section 1 du backlog). Toutes les tables sont creees des
# T-M00-1 pour que rien n'ait besoin d'etre "retrofit" plus tard (les modules
# qui les remplissent arrivent aux sprints suivants).
SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    ts_record TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    causation_id TEXT,
    correlation_id TEXT,
    rule_version_ref TEXT,
    source TEXT,
    author TEXT,
    hash TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
    rule_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    ts_record TEXT NOT NULL,
    body_json TEXT NOT NULL,
    origin TEXT NOT NULL,
    confidence REAL,
    active INTEGER NOT NULL DEFAULT 1,
    note TEXT,
    PRIMARY KEY (name, version)
);

CREATE TABLE IF NOT EXISTS objects (
    object_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    label TEXT,
    envelope_json TEXT NOT NULL,
    body_json TEXT NOT NULL,
    state TEXT,
    valid_from TEXT,
    valid_to TEXT,
    ts_record TEXT NOT NULL,
    version INTEGER NOT NULL,
    row_hash TEXT
);

CREATE TABLE IF NOT EXISTS links (
    link_id TEXT PRIMARY KEY,
    src TEXT NOT NULL,
    rel TEXT NOT NULL,
    dst TEXT NOT NULL,
    weight REAL,
    envelope_json TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    ts_record TEXT NOT NULL,
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kpi (
    name TEXT NOT NULL,
    key TEXT NOT NULL,
    value REAL,
    unit TEXT,
    nature TEXT,
    confidence REAL,
    rule_version INTEGER,
    computed_at TEXT,
    PRIMARY KEY (name, key)
);

CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    severity TEXT,
    probability REAL,
    impact REAL,
    recommendation TEXT,
    state TEXT,
    created_at TEXT NOT NULL,
    refs_json TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    label TEXT,
    target TEXT,
    acquisition TEXT,
    expected_every_days REAL,
    last_seen TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_log (
    import_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    source TEXT,
    file TEXT,
    file_hash TEXT,
    records INTEGER,
    new_records INTEGER,
    duplicates INTEGER,
    anomalies INTEGER,
    errors INTEGER,
    status TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    as_of_event TEXT,
    state_blob BLOB,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS permissions (
    subject TEXT NOT NULL,
    object_type TEXT NOT NULL,
    max_authority INTEGER NOT NULL,
    PRIMARY KEY (subject, object_type)
);

CREATE TABLE IF NOT EXISTS access_log (
    ts TEXT NOT NULL,
    subject TEXT,
    action TEXT,
    target TEXT
);
"""

ALL_TABLES = (
    "events", "rules", "objects", "links", "kpi", "anomalies",
    "sources", "ingestion_log", "snapshots", "permissions", "access_log",
)


def init_db(db_path=DEFAULT_DB_PATH):
    """Cree (si absent) le fichier eos.db et toutes les tables du schema.

    Idempotent : peut etre appele a chaque demarrage sans effet destructeur
    (CREATE TABLE IF NOT EXISTS), conformement a la loi "on n'ecrase jamais".
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return db_path


class _StatusHandler(http.server.BaseHTTPRequestHandler):
    """Poignee HTTP minimale : prouve que le serveur local repond.

    Sera remplacee/etendue par experience/web aux sprints UI (T-M25-*).
    """

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Enterprise OS - noyau vivant\n")

    def log_message(self, format, *args):
        pass  # silence par defaut : pas de bruit console (regle UX figee)


def build_server(host=DEFAULT_HOST, port=DEFAULT_PORT):
    return http.server.HTTPServer((host, port), _StatusHandler)


def run_server(host=DEFAULT_HOST, port=DEFAULT_PORT):
    server = build_server(host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Enterprise OS - serveur local")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    init_db(args.db)
    print(f"Enterprise OS demarre sur http://{args.host}:{args.port} (DB: {args.db})")
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
