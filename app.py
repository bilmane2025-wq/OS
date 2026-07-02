"""Enterprise OS - serveur local + orchestrateur (boucle de synchro).

Sprint 1 / T-M00-1 (amorcage) : arborescence du projet, schema SQLite complet
(les deux patrimoines + toutes les projections du backlog), et un serveur
HTTP local minimal (stdlib uniquement, aucune dependance externe, aucun
appel reseau sortant - conforme a la Constitution : zero API, zero cloud).

La boucle de synchronisation vivante (T-M00-3) fait vivre le systeme
sans humain : poll de l'inbox a cadence configurable -> pipeline
d'ingestion (12 etapes, modules Sprints 2-3) -> repli incremental dans le
graphe -> recalcul cible des KPI (DAG M12) -> reconciliation -> watchdog
des sources -> alertes groupees sous budget d'attention. Le serveur local
sert les vues pendant que la boucle tourne en arriere-plan.
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


DEFAULT_INBOX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "inbox")
DEFAULT_ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "archive")
DEFAULT_INTERVAL_SECONDS = 5.0


def _ingest_with_parser(conn, inbox_dir, archive_dir, filename, parse_outcome, hash_, now):
    """Tronc commun de la boucle pour un fichier traite par un parseur
    specialise : archivage + journalisation de l'ingestion (memes
    garanties que ``intake_folder.process_file``)."""
    from uuid import uuid4

    from perception import dedup, intake_folder

    import_id = f"ING:{uuid4().hex}"
    appended = parse_outcome.get("appended", [])
    if "event_id" in parse_outcome:
        appended = appended + [parse_outcome["event_id"]]
    quarantined = parse_outcome.get("quarantined", [])
    anomaly_count = len(quarantined) + (1 if parse_outcome.get("anomaly_id") else 0)

    intake_folder.archive_file(inbox_dir, archive_dir, filename, hash_)
    dedup.record_ingestion(
        conn, import_id, source="inbox", file=filename, hash_=hash_,
        records=parse_outcome.get("records", 1), new_records=len(appended),
        duplicates=parse_outcome.get("duplicates", 0), anomalies=anomaly_count,
        errors=0, status=parse_outcome.get("status", "parsed"), ts=now,
    )
    return {"status": parse_outcome.get("status"), "filename": filename,
            "import_id": import_id, "event_ids": appended}


def _ingest_one(conn, inbox_dir, archive_dir, filename):
    """Pipeline d'ingestion d'un fichier depose (les 12 etapes de la
    Conception 8.3, incarnees par les modules Sprints 2-3) : detection ->
    integrite/dedup fichier -> routage -> extraction par le parseur
    specialise quand un profil/une regle existe -> validation M07 ->
    normalisation M04 -> dedup ligne M08 -> journalisation -> archivage.
    Sans profil ni parseur applicable, le fichier suit la voie generique
    de ``process_file`` (DocumentReceived ou quarantaine) - jamais une
    interpretation devinee."""
    from datetime import datetime, timezone

    from perception import dedup, intake_folder
    from perception.parsers import csv_parser, pdf_parser, xlsx_parser

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    path = os.path.join(inbox_dir, filename)
    route = intake_folder.route_for(filename)
    hash_ = dedup.file_hash(path)

    if dedup.file_seen(conn, hash_) or route not in ("csv", "xlsx", "pdf"):
        # Doublon de fichier, email, image ou format inconnu : la voie
        # generique porte deja toutes les garanties (dedup, quarantaine,
        # extraction recursive des PJ d'email, archivage, journal).
        outcome = intake_folder.process_file(conn, inbox_dir, archive_dir, filename)
        event_ids = [outcome["event_id"]] if "event_id" in outcome else []
        for attachment in outcome.get("attachment_outcomes", []):
            if "event_id" in attachment:
                event_ids.append(attachment["event_id"])
        outcome["event_ids"] = event_ids
        return outcome

    profile = csv_parser.find_profile(conn, filename)
    if route == "csv" and profile is not None:
        parsed = csv_parser.parse(conn, path, profile=profile)
    elif route == "xlsx" and profile is not None:
        parsed = xlsx_parser.parse(conn, path, profile=profile)
    elif route == "pdf":
        parsed = pdf_parser.parse(conn, path)
    else:
        # csv/xlsx sans profil : anomalie « profil manquant », le fichier
        # est archive sans jamais etre interprete.
        parsed = csv_parser.parse(conn, path, profile=None)

    outcome = _ingest_with_parser(conn, inbox_dir, archive_dir, filename, parsed, hash_, now)
    if profile is not None and parsed.get("status") == "parsed":
        from governance import observability
        # La source attendue vient d'etre recue : sa fraicheur est mise a
        # jour si elle est declaree au registre des sources (M33).
        source_id = profile["name"].split("/", 1)[1]
        row = conn.execute("SELECT 1 FROM sources WHERE source_id = ?",
                           (source_id,)).fetchone()
        if row is not None:
            observability.mark_seen(conn, source_id, now)
    return outcome


def sync_cycle(conn, inbox_dir=DEFAULT_INBOX_DIR, archive_dir=DEFAULT_ARCHIVE_DIR):
    """Un cycle de la boucle vivante (T-M00-3) : inbox -> evenements ->
    graphe -> recalcul **incremental** -> reconciliation -> watchdog ->
    alertes groupees sous budget d'attention.

    Jamais de recalcul global : seuls les evenements nouvellement ingeres
    sont replies dans le graphe, et seules les derivations dependantes de
    leurs types sont recalculees (DAG M12).

    Returns:
        dict: ``{"ingested": [...], "new_events": n, "recomputed": [...],
        "reconciliation": ... , "watchdog": [...], "attention": {...}}``.
    """
    from calc import derivation, kpi_catalog
    from core import event_store
    from experience import attention, proactivity
    from governance import audit, observability
    from graph import graph_engine
    from perception import intake_folder

    kpi_catalog.register_derivations()  # idempotent

    ingested = [
        _ingest_one(conn, inbox_dir, archive_dir, filename)
        for filename in intake_folder.scan_inbox(inbox_dir)
    ]

    new_event_ids = {eid for outcome in ingested for eid in outcome.get("event_ids", [])}
    new_events = [e for e in event_store.read(conn) if e["event_id"] in new_event_ids]

    recomputed = []
    for event in new_events:
        graph_engine.apply(conn, event)
        recomputed.extend(derivation.on_event(conn, event).keys())

    reconciliation = None
    if new_events:
        already_open = conn.execute(
            "SELECT 1 FROM anomalies WHERE type = 'reconciliation/ecart-encaissement-vente' "
            "AND state = 'ouverte'").fetchone()
        if already_open is None:
            reconciliation = audit.reconcile_collections_vs_sales(conn)

    watchdog_alerts = observability.watchdog(conn)

    grouped = proactivity.group_alerts(proactivity.collect_alerts(conn))
    budgeted = attention.budget(grouped)

    return {
        "ingested": ingested,
        "new_events": len(new_events),
        "recomputed": sorted(set(recomputed)),
        "reconciliation": reconciliation,
        "watchdog": watchdog_alerts,
        "attention": budgeted,
    }


def run_loop(db_path=DEFAULT_DB_PATH, inbox_dir=DEFAULT_INBOX_DIR,
             archive_dir=DEFAULT_ARCHIVE_DIR, interval_seconds=DEFAULT_INTERVAL_SECONDS,
             cycles=None, stop_event=None):
    """Boucle de synchronisation permanente : poll de l'inbox a cadence
    configurable. ``cycles`` limite le nombre de tours (tests) ;
    ``stop_event`` (threading.Event) arrete proprement."""
    import threading
    import time

    stop_event = stop_event or threading.Event()
    completed = 0
    while not stop_event.is_set():
        conn = sqlite3.connect(db_path)
        try:
            sync_cycle(conn, inbox_dir, archive_dir)
        finally:
            conn.close()
        completed += 1
        if cycles is not None and completed >= cycles:
            break
        stop_event.wait(interval_seconds)
    return completed


def main():
    parser = argparse.ArgumentParser(description="Enterprise OS - serveur local")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS,
                        help="cadence (secondes) de la boucle de synchronisation")
    parser.add_argument("--no-loop", action="store_true",
                        help="demarrer le serveur sans la boucle vivante")
    args = parser.parse_args()

    init_db(args.db)
    seed(args.db)

    if not args.no_loop:
        import threading
        poller = threading.Thread(
            target=run_loop,
            kwargs={"db_path": args.db, "interval_seconds": args.interval},
            daemon=True, name="eos-sync-loop")
        poller.start()

    print(f"Enterprise OS demarre sur http://{args.host}:{args.port} (DB: {args.db})")
    run_server(args.host, args.port, args.db)


if __name__ == "__main__":
    main()
