"""Passerelle de perception - dossier surveille (T-M04-1, T-M04-2).

Detecte tout fichier depose dans ``data/inbox/``, le route selon son
extension, l'emballe en un evenement ``PERCEPTION.DocumentReceived`` avec
enveloppe complete - ou le met en quarantaine si son extension n'est pas
reconnue -, puis l'archive dans ``data/archive/``. Deduplique par
empreinte de contenu (``perception.dedup``) : rejouer le meme fichier ne
cree jamais de doublon.

Ne calcule rien, ne decide rien (Conception, frontiere M04) : le contenu
du fichier n'est pas interprete ici - seuls les parseurs specialises
(Sprint 3 : email/CSV/XLSX/PDF/OCR) l'extrairont en champs structures.
"""
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from core import event_store
from core.envelope import make_envelope
from perception import dedup

# Extension -> route (categorie de traitement). Toute extension absente de
# cette table est un format non reconnu -> quarantaine (jamais d'invention
# d'une route).
ROUTES = {
    ".eml": "email",
    ".pdf": "pdf",
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
}

DEFAULT_AUTHOR = "agent:perception"


def route_for(filename):
    """Route (categorie) d'un fichier d'apres son extension, ou ``None``
    si l'extension n'est pas reconnue."""
    _, ext = os.path.splitext(filename)
    return ROUTES.get(ext.lower())


def scan_inbox(inbox_dir):
    """Liste, dans un ordre determiste, les fichiers presents dans
    ``inbox_dir`` (les entrees cachees comme ``.gitkeep`` et les
    sous-dossiers sont ignores)."""
    if not os.path.isdir(inbox_dir):
        return []
    names = [
        name
        for name in os.listdir(inbox_dir)
        if not name.startswith(".") and os.path.isfile(os.path.join(inbox_dir, name))
    ]
    return sorted(names)


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _archive_file(inbox_dir, archive_dir, filename, hash_):
    """Deplace le fichier traite vers l'archive. Prefixe par les 8
    premiers caracteres de son empreinte pour ne jamais ecraser un fichier
    homonyme deja archive."""
    os.makedirs(archive_dir, exist_ok=True)
    source_path = os.path.join(inbox_dir, filename)
    destination_path = os.path.join(archive_dir, f"{hash_[:8]}_{filename}")
    os.replace(source_path, destination_path)
    return destination_path


def _write_quarantine_event(conn, filename, hash_, reason, now):
    envelope = make_envelope(
        id=f"EVT:{uuid4().hex}",
        type_="SYSTEM.Quarantine",
        label=f"Fichier en quarantaine : {filename}",
        source=f"inbox/{filename}",
        author=DEFAULT_AUTHOR,
        valid_from=now,
        ts_record=now,
        nature="fait",
        score=1.0,
        owner="system",
        visibility="interne",
        authority=1,
    )
    _, event_id = event_store.append(
        conn, envelope, payload={"filename": filename, "file_hash": hash_, "reason": reason}
    )

    anomaly_id = f"ANOM:{uuid4().hex}"
    conn.execute(
        """
        INSERT INTO anomalies (
            anomaly_id, type, severity, probability, impact, recommendation,
            state, created_at, refs_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            anomaly_id,
            "perception/unrouted-file",
            "moyenne",
            1.0,
            None,
            "Deposer le fichier dans un format reconnu (.eml/.pdf/.csv/.xlsx/.png/.jpg) "
            "ou saisir la donnee manuellement.",
            "ouverte",
            now,
            json.dumps({"event_id": event_id, "reason": reason}, ensure_ascii=False),
        ),
    )
    conn.commit()
    return event_id, anomaly_id


def _write_document_received_event(conn, filename, route, hash_, size_bytes, now):
    envelope = make_envelope(
        id=f"EVT:{uuid4().hex}",
        type_="PERCEPTION.DocumentReceived",
        label=f"Document recu : {filename}",
        source=f"inbox/{filename}",
        author=DEFAULT_AUTHOR,
        valid_from=now,
        ts_record=now,
        nature="fait",
        score=1.0,
        owner="system",
        visibility="interne",
        authority=1,
    )
    payload = {
        "filename": filename,
        "route": route,
        "file_hash": hash_,
        "size_bytes": size_bytes,
    }
    return event_store.append(conn, envelope, payload=payload)


def process_file(conn, inbox_dir, archive_dir, filename):
    """Traite un fichier depose : deduplication -> routage ->
    normalisation en evenement (ou quarantaine) -> archivage ->
    journalisation de l'ingestion.

    Args:
        conn: connexion SQLite ouverte (voir ``core.event_store.connect``).
        inbox_dir: dossier surveille (``data/inbox``).
        archive_dir: dossier d'archive (``data/archive``).
        filename: nom du fichier a traiter, doit exister dans ``inbox_dir``.

    Returns:
        dict decrivant l'issue :
        ``{"status": "duplicate"|"quarantined"|"processed", "filename":
        ..., "import_id": ..., "route": ..., "event_id": ...,
        "anomaly_id": ...}`` (les cles non pertinentes selon le statut
        sont omises).
    """
    source_path = os.path.join(inbox_dir, filename)
    hash_ = dedup.file_hash(source_path)
    size_bytes = os.path.getsize(source_path)
    now = _now_iso()
    import_id = f"ING:{uuid4().hex}"

    if dedup.file_seen(conn, hash_):
        _archive_file(inbox_dir, archive_dir, filename, hash_)
        dedup.record_ingestion(
            conn, import_id, source="inbox", file=filename, hash_=hash_,
            records=1, new_records=0, duplicates=1, anomalies=0, errors=0,
            status="duplicate", ts=now,
        )
        return {"status": "duplicate", "filename": filename, "import_id": import_id}

    route = route_for(filename)

    if route is None:
        event_id, anomaly_id = _write_quarantine_event(
            conn, filename, hash_, reason="extension non reconnue", now=now
        )
        _archive_file(inbox_dir, archive_dir, filename, hash_)
        dedup.record_ingestion(
            conn, import_id, source="inbox", file=filename, hash_=hash_,
            records=1, new_records=0, duplicates=0, anomalies=1, errors=0,
            status="quarantined", ts=now,
        )
        return {
            "status": "quarantined",
            "filename": filename,
            "import_id": import_id,
            "event_id": event_id,
            "anomaly_id": anomaly_id,
        }

    _, event_id = _write_document_received_event(conn, filename, route, hash_, size_bytes, now)
    _archive_file(inbox_dir, archive_dir, filename, hash_)
    dedup.record_ingestion(
        conn, import_id, source="inbox", file=filename, hash_=hash_,
        records=1, new_records=1, duplicates=0, anomalies=0, errors=0,
        status="processed", ts=now,
    )
    return {
        "status": "processed",
        "filename": filename,
        "route": route,
        "import_id": import_id,
        "event_id": event_id,
    }


def process_inbox(conn, inbox_dir, archive_dir):
    """Traite tous les fichiers actuellement presents dans ``inbox_dir``,
    dans un ordre determiste (ordre alphabetique des noms).

    Returns:
        list[dict]: une issue (voir ``process_file``) par fichier traite.
    """
    return [
        process_file(conn, inbox_dir, archive_dir, filename)
        for filename in scan_inbox(inbox_dir)
    ]
