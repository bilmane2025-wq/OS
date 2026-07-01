"""Controle qualite d'entree - validation & quarantaine (T-M07-1).

``validate`` est une fonction pure : elle controle un enregistrement brut
face a un profil (champs requis, champs numeriques, champs date, periode
attendue) et renvoie le verdict - jamais d'effet de bord, jamais
d'interpretation au-dela de ce que le profil demande (Conception,
frontiere M07 : "integrer une donnee douteuse en silence" est interdit).

``quarantine`` trace la decision : elle ecrit un evenement
``SYSTEM.Quarantine`` immuable dans le journal et une ``anomalie``
associee - une ligne invalide n'entre **jamais** dans le journal comme un
fait, mais son rejet, lui, est toujours prouve et retrouvable.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

from core import event_store
from core.envelope import make_envelope

DEFAULT_AUTHOR = "system:quality"


def _parse_timestamp_or_none(value):
    if not isinstance(value, str) or value.strip() == "":
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate(record, profile):
    """Controle ``record`` face a ``profile``.

    Le profil decrit ce qui est attendu :
        - ``required``: liste de champs qui doivent etre presents et non
          vides.
        - ``numeric``: liste de champs qui doivent etre un nombre (ou une
          chaine convertible en nombre).
        - ``date``: liste de champs qui doivent etre une date/heure
          ISO-8601 avec fuseau horaire explicite.
        - ``period_field`` + ``period``: le champ de date a verifier par
          rapport a une periode ``{"since": ..., "until": ...}`` (bornes
          ISO-8601, ``until`` exclue).

    Args:
        record: dict brut a valider (une ligne de CSV/XLSX, un champ
            extrait d'un PDF, etc.).
        profile: dict decrivant les attentes (voir ci-dessus). Toutes les
            cles sont optionnelles ; un profil vide n'impose rien.

    Returns:
        dict: ``{"valid": bool, "errors": list[str]}``. Jamais d'exception
        levee pour une donnee simplement invalide - c'est le role normal
        de cette fonction de le detecter, pas un cas d'erreur.
    """
    errors = []
    profile = profile or {}

    for field in profile.get("required", []):
        if field not in record or record[field] in (None, ""):
            errors.append(f"champ requis manquant ou vide : {field}")

    for field in profile.get("numeric", []):
        if field not in record or record[field] in (None, ""):
            continue
        value = record[field]
        if isinstance(value, bool):
            errors.append(f"{field} n'est pas numerique : {value!r}")
        elif isinstance(value, (int, float)):
            continue
        elif isinstance(value, str):
            try:
                float(value.replace(",", "."))
            except ValueError:
                errors.append(f"{field} n'est pas numerique : {value!r}")
        else:
            errors.append(f"{field} n'est pas numerique : {value!r}")

    for field in profile.get("date", []):
        if field not in record or record[field] in (None, ""):
            continue
        if _parse_timestamp_or_none(record[field]) is None:
            errors.append(f"{field} n'est pas une date ISO-8601 valide (avec fuseau) : {record[field]!r}")

    period = profile.get("period")
    period_field = profile.get("period_field")
    if period and period_field and period_field in record and record[period_field] not in (None, ""):
        parsed = _parse_timestamp_or_none(record[period_field])
        if parsed is not None:
            since = _parse_timestamp_or_none(period.get("since")) if period.get("since") else None
            until = _parse_timestamp_or_none(period.get("until")) if period.get("until") else None
            if since is not None and parsed < since:
                errors.append(f"{period_field} hors periode : avant {period.get('since')}")
            if until is not None and parsed >= until:
                errors.append(f"{period_field} hors periode : a partir de {period.get('until')}")

    return {"valid": len(errors) == 0, "errors": errors}


def quarantine(conn, record, reasons, source=None, author=DEFAULT_AUTHOR, severity="moyenne"):
    """Met ``record`` en quarantaine de maniere tracee : un evenement
    ``SYSTEM.Quarantine`` immuable au journal + une anomalie associee.

    Le contenu de ``record`` n'entre jamais dans le journal comme un fait
    mesure ou observe - seul le fait qu'il ait ete mis en quarantaine,
    avec ses raisons, y entre.

    Args:
        conn: connexion SQLite ouverte.
        record: l'enregistrement brut rejete.
        reasons: liste de motifs de rejet (ex. la sortie de ``validate``).
        source: provenance du fichier/flux d'origine (optionnel).
        author: auteur/agent responsable de la detection.
        severity: gravite de l'anomalie associee.

    Returns:
        tuple[str, str]: (event_id, anomaly_id).
    """
    now = _now_iso()
    envelope = make_envelope(
        id=f"EVT:{uuid4().hex}",
        type_="SYSTEM.Quarantine",
        label="Enregistrement mis en quarantaine",
        source=source or "unknown",
        author=author,
        valid_from=now,
        ts_record=now,
        nature="fait",
        score=1.0,
        owner="system",
        visibility="interne",
        authority=1,
    )
    _, event_id = event_store.append(
        conn, envelope, payload={"record": record, "reasons": list(reasons)}
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
            "quality/invalid-record",
            severity,
            1.0,
            None,
            "Corriger la source ou ressaisir l'enregistrement manuellement.",
            "ouverte",
            now,
            json.dumps({"event_id": event_id, "reasons": list(reasons)}, ensure_ascii=False),
        ),
    )
    conn.commit()
    return event_id, anomaly_id
