"""Passerelle de perception - dossier surveille (T-M04-1, T-M04-2).

Detecte tout fichier depose dans ``data/inbox/``, le route selon son
extension, l'emballe en un evenement ``PERCEPTION.DocumentReceived`` avec
enveloppe complete - ou le met en quarantaine si son extension n'est pas
reconnue -, puis l'archive dans ``data/archive/``. Deduplique par
empreinte de contenu (``perception.dedup``) : rejouer le meme fichier ne
cree jamais de doublon.

Ne calcule rien, ne decide rien (Conception, frontiere M04) : le contenu
du fichier n'est pas interprete ici au-dela du routage - seuls les
parseurs specialises (Sprint 3 : email/CSV/XLSX/PDF/OCR) l'extrairont en
champs structures. La route ``"email"`` delegue deja a
``perception.email_parser`` (T-M05-1) ; les autres routes restent
generiques (``PERCEPTION.DocumentReceived``) en attendant leurs parseurs
dedies.
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


def archive_file(inbox_dir, archive_dir, filename, hash_):
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
        archive_file(inbox_dir, archive_dir, filename, hash_)
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
        archive_file(inbox_dir, archive_dir, filename, hash_)
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

    if route == "email":
        # Import differe : perception.email_parser (T-M05-1) reutilise
        # process_file/archive_file pour traiter les pieces jointes et
        # archiver l'email lui-meme - un import en tete de module creerait
        # une dependance circulaire entre les deux fichiers.
        from perception import email_parser

        return email_parser.parse(conn, inbox_dir, archive_dir, filename)

    _, event_id = _write_document_received_event(conn, filename, route, hash_, size_bytes, now)
    archive_file(inbox_dir, archive_dir, filename, hash_)
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


def normalize_records(conn, records, event_type, source, keycols, nature="fait", score=1.0,
                      valid_from_field=None):
    """Emballe des enregistrements bruts (sortie d'un parseur) en
    evenements ``PERCEPTION.*`` avec enveloppe complete (T-M04-2).

    C'est le contrat M04 du backlog : « chaque parseur renvoie des
    enregistrements bruts ; M04 les emballe en evenements ». Ne calcule
    rien, ne decide rien : chaque enregistrement devient un evenement
    verbatim, deduplique par empreinte de ligne (``dedup.row_hash`` sur
    ``keycols``, T-M08-1) - rejouer le meme lot ne cree aucun doublon.

    Args:
        conn: connexion SQLite ouverte.
        records: liste de dicts (enregistrements bruts mappes).
        event_type: type d'evenement produit (ex.
            ``"PERCEPTION.StatementLine"``).
        source: provenance (ex. ``"inbox/releve.csv"``).
        keycols: colonnes-cles pour l'empreinte de ligne.
        nature: nature de confiance des evenements produits.
        score: score de confiance.
        valid_from_field: champ de l'enregistrement portant la date de
            validite (temps du monde) ; repli sur "maintenant" si absent
            ou invalide - jamais une date inventee.

    Returns:
        dict: ``{"appended": [event_id...], "duplicates": int}``.
    """
    now = _now_iso()
    appended, duplicates = [], 0
    for record in records:
        row_hash = dedup.row_hash(record, keycols)
        # Dedup par empreinte de ligne (T-M08-1) : la meme ligne metier
        # (memes colonnes-cles) deja emballee en evenement - meme lors
        # d'un import anterieur, donc avec un ts_record different - n'est
        # jamais reinseree. payload_json est du JSON canonique
        # (sort_keys), le motif recherche est donc deterministe.
        already = conn.execute(
            "SELECT event_id FROM events WHERE type = ? AND payload_json LIKE ?",
            (event_type, f'%"row_hash": "{row_hash}"%'),
        ).fetchone()
        if already is not None:
            duplicates += 1
            continue
        valid_from = now
        if valid_from_field and record.get(valid_from_field):
            candidate = str(record[valid_from_field])
            try:
                parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
                if parsed.tzinfo is not None and parsed.utcoffset() is not None:
                    valid_from = candidate
            except ValueError:
                pass  # date illisible -> repli sur maintenant, sans invention

        envelope = make_envelope(
            id=f"EVT:{uuid4().hex}",
            type_=event_type,
            label=f"{event_type} ({source})",
            source=source,
            author=DEFAULT_AUTHOR,
            valid_from=valid_from,
            ts_record=now,
            nature=nature,
            score=score,
            owner="system",
            visibility="interne",
            authority=1,
        )
        status, event_id = event_store.append(
            conn, envelope, payload={"record": record, "row_hash": row_hash}
        )
        if status == event_store.DUPLICATE:
            duplicates += 1
        else:
            appended.append(event_id)
    return {"appended": appended, "duplicates": duplicates}


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
