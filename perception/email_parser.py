"""Parseur email .eml (T-M05-1).

Decompose un email depose dans ``data/inbox/`` : metadonnees
(expediteur, sujet, date), corps, et pieces jointes. Les pieces jointes
sont extraites vers ``data/inbox/`` elles-memes (recursif) puis
immediatement traitees par la passerelle de perception
(``perception.intake_folder``, T-M04-1/T-M04-2) - chacune produit son
propre evenement (ou sa propre quarantaine si son extension n'est pas
reconnue), exactement comme n'importe quel fichier depose directement.
L'email lui-meme produit un evenement ``PERCEPTION.EmailReceived``.

Ne calcule rien, n'interprete rien au-dela des en-tetes structurels de
l'email et de l'identification des pieces jointes (Conception, frontiere
M04/M05) : le corps et les en-tetes sont captures verbatim, jamais
categorises ni resumes.
"""
import email
import email.policy
import email.utils
import os
from datetime import datetime, timezone
from uuid import uuid4

from core import event_store
from core.envelope import make_envelope
from perception import dedup, intake_folder

DEFAULT_AUTHOR = "agent:perception"


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_email_date(raw_date):
    """Convertit l'en-tete ``Date`` (RFC 2822) en ISO-8601 avec fuseau
    horaire explicite. ``None`` si absent, illisible, ou sans fuseau -
    jamais une date inventee."""
    if not raw_date:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(raw_date)
    except (TypeError, ValueError):
        return None
    if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def _decode_part_text(part):
    try:
        content = part.get_content()
    except Exception:
        raw = part.get_payload(decode=True)
        if raw is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        try:
            return raw.decode(charset, errors="replace")
        except (LookupError, TypeError):
            return raw.decode("utf-8", errors="replace")
    return content if isinstance(content, str) else str(content)


def _extract_body(message):
    """Corps textuel de l'email : privilegie text/plain, replie sur
    text/html si c'est la seule partie textuelle disponible."""
    if not message.is_multipart():
        return _decode_part_text(message)

    html_fallback = None
    for part in message.walk():
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        if part.get_content_type() == "text/plain":
            return _decode_part_text(part)
        if part.get_content_type() == "text/html" and html_fallback is None:
            html_fallback = part

    return _decode_part_text(html_fallback) if html_fallback is not None else ""


def _unique_attachment_path(inbox_dir, filename):
    base_name = os.path.basename(filename) or "piece-jointe"
    candidate = os.path.join(inbox_dir, base_name)
    if not os.path.exists(candidate):
        return candidate
    stem, ext = os.path.splitext(base_name)
    return os.path.join(inbox_dir, f"{stem}-{uuid4().hex[:8]}{ext}")


def _extract_attachments(message, inbox_dir):
    """Ecrit chaque piece jointe dans ``inbox_dir`` et renvoie la liste
    des noms de fichiers ecrits (recursif : elles seront traitees comme
    n'importe quel depot par ``intake_folder.process_file``)."""
    if not message.is_multipart():
        return []

    os.makedirs(inbox_dir, exist_ok=True)
    attachment_filenames = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue

        destination = _unique_attachment_path(inbox_dir, filename)
        with open(destination, "wb") as handle:
            handle.write(payload)
        attachment_filenames.append(os.path.basename(destination))

    return attachment_filenames


def _email_label(subject, filename):
    if subject and subject.strip():
        return subject.strip()
    return f"Email recu : {filename}"


def _write_email_received_event(
    conn, filename, sender, subject, date_iso, body, attachment_filenames, hash_, now
):
    envelope = make_envelope(
        id=f"EVT:{uuid4().hex}",
        type_="PERCEPTION.EmailReceived",
        label=_email_label(subject, filename),
        source=f"inbox/{filename}",
        author=DEFAULT_AUTHOR,
        valid_from=date_iso or now,
        ts_record=now,
        nature="fait",
        score=1.0,
        owner="system",
        visibility="interne",
        authority=1,
    )
    payload = {
        "filename": filename,
        "sender": sender,
        "subject": subject,
        "date": date_iso,
        "body": body,
        "attachments": attachment_filenames,
        "file_hash": hash_,
    }
    return event_store.append(conn, envelope, payload=payload)


def parse(conn, inbox_dir, archive_dir, filename):
    """Traite un email ``.eml`` depose.

    Pipeline : deduplication -> lecture (expediteur/sujet/date/corps) ->
    extraction des pieces jointes vers ``inbox_dir`` -> evenement
    ``PERCEPTION.EmailReceived`` -> traitement recursif de chaque piece
    jointe via ``intake_folder.process_file`` -> archivage de l'email ->
    journalisation de l'ingestion.

    Args:
        conn: connexion SQLite ouverte.
        inbox_dir: dossier surveille (``data/inbox``).
        archive_dir: dossier d'archive (``data/archive``).
        filename: nom du fichier ``.eml`` a traiter, doit exister dans
            ``inbox_dir``.

    Returns:
        dict: meme contrat que ``intake_folder.process_file``
        (``status``, ``filename``, ``import_id``, et selon le cas
        ``route``/``event_id``), augmente de ``attachment_outcomes``
        (liste des issues de traitement de chaque piece jointe, meme
        format que ``process_file``).
    """
    source_path = os.path.join(inbox_dir, filename)
    hash_ = dedup.file_hash(source_path)
    now = _now_iso()
    import_id = f"ING:{uuid4().hex}"

    if dedup.file_seen(conn, hash_):
        intake_folder.archive_file(inbox_dir, archive_dir, filename, hash_)
        dedup.record_ingestion(
            conn, import_id, source="inbox", file=filename, hash_=hash_,
            records=1, new_records=0, duplicates=1, anomalies=0, errors=0,
            status="duplicate", ts=now,
        )
        return {"status": "duplicate", "filename": filename, "import_id": import_id}

    with open(source_path, "rb") as handle:
        message = email.message_from_binary_file(handle, policy=email.policy.default)

    sender = message.get("From")
    subject = message.get("Subject")
    date_iso = _parse_email_date(message.get("Date"))
    body = _extract_body(message)
    attachment_filenames = _extract_attachments(message, inbox_dir)

    _, event_id = _write_email_received_event(
        conn, filename, sender, subject, date_iso, body, attachment_filenames, hash_, now
    )

    attachment_outcomes = [
        intake_folder.process_file(conn, inbox_dir, archive_dir, attachment_filename)
        for attachment_filename in attachment_filenames
    ]

    intake_folder.archive_file(inbox_dir, archive_dir, filename, hash_)
    dedup.record_ingestion(
        conn, import_id, source="inbox", file=filename, hash_=hash_,
        records=1, new_records=1, duplicates=0, anomalies=0, errors=0,
        status="processed", ts=now,
    )

    return {
        "status": "processed",
        "filename": filename,
        "route": "email",
        "import_id": import_id,
        "event_id": event_id,
        "attachment_outcomes": attachment_outcomes,
    }
