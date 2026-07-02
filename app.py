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
import json
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
    """Serveur local des vues (Sprint 7, T-M25-*) : chaque ecran est
    servi sur ``localhost``, sans aucun appel externe. La racine ``/``
    redirige la lecture vers la Vue Instantanee (10 s), point d'entree
    officiel du dirigeant."""

    db_path = DEFAULT_DB_PATH  # surcharge par build_server(db_path=...)

    def _send(self, body, content_type="text/html; charset=utf-8", status=200):
        payload = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(payload)

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def do_GET(self):
        # Imports locaux : les vues dependent du reste du systeme, alors
        # que init_db/build_server doivent rester importables seuls.
        from urllib.parse import parse_qs, urlparse

        from experience import views
        from intent import conversation, search

        parsed = urlparse(self.path)
        route = parsed.path
        params = parse_qs(parsed.query)

        if route == "/":
            self._send("Enterprise OS - noyau vivant\n",
                       content_type="text/plain; charset=utf-8")
            return
        if route == "/base.css":
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "experience", "web", "base.css"), "rb") as f:
                self._send(f.read(), content_type="text/css; charset=utf-8")
            return

        conn = self._connect()
        try:
            if route == "/instant":
                self._send(views.render_instant(conn))
            elif route == "/daily":
                self._send(views.render_daily(conn))
            elif route == "/detail":
                kpi_name = (params.get("kpi") or [""])[0]
                self._send(views.render_detail(conn, kpi_name))
            elif route == "/inbox":
                self._send(views.render_inbox(conn))
            elif route == "/forms":
                self._send(views.render_forms())
            elif route == "/health":
                self._send(views.render_health(conn))
            elif route == "/search":
                results = search.query(conn, (params.get("q") or [""])[0])
                self._send(json.dumps(results, ensure_ascii=False),
                           content_type="application/json; charset=utf-8")
            elif route == "/ask":
                answer = conversation.ask(conn, (params.get("q") or [""])[0])
                self._send(json.dumps(answer, ensure_ascii=False),
                           content_type="application/json; charset=utf-8")
            else:
                self._send("introuvable", status=404)
        finally:
            conn.close()

    def log_message(self, format, *args):
        pass  # silence par defaut : pas de bruit console (regle UX figee)


def build_server(host=DEFAULT_HOST, port=DEFAULT_PORT, db_path=DEFAULT_DB_PATH):
    handler = type("_BoundHandler", (_StatusHandler,), {"db_path": db_path})
    return http.server.HTTPServer((host, port), handler)


def run_server(host=DEFAULT_HOST, port=DEFAULT_PORT, db_path=DEFAULT_DB_PATH):
    server = build_server(host, port, db_path)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def seed(db_path=DEFAULT_DB_PATH):
    """Amorce les regles seed (T-M02-2) et les profils source (T-M05-2)
    au demarrage. Idempotent : les deux chargeurs ne reseedent jamais une
    regle qui possede deja une version."""
    from core import rules
    from perception.parsers import csv_parser

    conn = sqlite3.connect(db_path)
    try:
        rules.load_seed_rules(conn)
        csv_parser.load_profiles_as_rules(conn)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Enterprise OS - serveur local")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    init_db(args.db)
    seed(args.db)
    print(f"Enterprise OS demarre sur http://{args.host}:{args.port} (DB: {args.db})")
    run_server(args.host, args.port, args.db)


if __name__ == "__main__":
    main()
