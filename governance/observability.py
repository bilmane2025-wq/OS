"""Observabilite interne - score de sante des donnees (T-M33-1).

Proprioception du systeme : chaque source declaree (releve bancaire,
exports plateformes, factures...) porte une cadence attendue ; le score
global mesure honnetement couverture et fraicheur - **les sources
manquantes tirent le score vers le bas**, jamais l'inverse (Constitution,
loi 14 : « le systeme mesure et publie sa propre sante des donnees,
honnetement » ; « un score honnete meme bas vaut mieux qu'un faux
100 % »). Le watchdog transforme chaque retard en anomalie - sans jamais
dupliquer une alerte deja ouverte pour la meme source.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def register_source(conn, source_id, label, target, acquisition, expected_every_days):
    """Declare une source attendue (registre des sources, Conception 8.1)."""
    conn.execute(
        """
        INSERT INTO sources (source_id, label, target, acquisition,
                             expected_every_days, last_seen, status)
        VALUES (?, ?, ?, ?, ?, NULL, 'jamais-recue')
        ON CONFLICT(source_id) DO UPDATE SET
            label = excluded.label, target = excluded.target,
            acquisition = excluded.acquisition,
            expected_every_days = excluded.expected_every_days
        """,
        (source_id, label, target, acquisition, expected_every_days),
    )
    conn.commit()


def mark_seen(conn, source_id, ts=None):
    """Enregistre une reception effective de la source."""
    conn.execute(
        "UPDATE sources SET last_seen = ?, status = 'ok' WHERE source_id = ?",
        (ts or _now_iso(), source_id),
    )
    conn.commit()


def _source_status(source, now):
    source_id, label, target, acquisition, expected_days, last_seen, _ = source
    if last_seen is None:
        return {"source_id": source_id, "label": label, "status": "jamais-recue",
                "late": True, "last_seen": None}
    age_days = (_parse(now) - _parse(last_seen)).total_seconds() / 86400
    late = expected_days is not None and age_days > expected_days
    return {"source_id": source_id, "label": label,
            "status": "en-retard" if late else "ok",
            "late": late, "last_seen": last_seen}


def health(conn, now=None):
    """Score de sante des donnees, publie honnetement.

    Score = part des sources declarees qui sont a jour (recues au moins
    une fois ET dans leur cadence attendue). Aucune source declaree ->
    score 0.0 (on ne sait rien, on ne pretend pas savoir).

    Returns:
        dict: ``{"score": 0..1, "sources": [...], "late": [...]}``.
    """
    now = now or _now_iso()
    sources = conn.execute(
        "SELECT source_id, label, target, acquisition, expected_every_days, "
        "last_seen, status FROM sources ORDER BY source_id"
    ).fetchall()

    statuses = [_source_status(source, now) for source in sources]
    late = [s for s in statuses if s["late"]]
    score = (len(statuses) - len(late)) / len(statuses) if statuses else 0.0

    return {"score": score, "sources": statuses, "late": late}


def watchdog(conn, now=None):
    """Alerte sur chaque source en retard : une anomalie
    ``observability/source-en-retard`` par source (jamais dupliquee tant
    que la precedente est ouverte).

    Returns:
        list[str]: identifiants des anomalies creees par cet appel.
    """
    now = now or _now_iso()
    created = []
    for source in health(conn, now)["late"]:
        already_open = conn.execute(
            "SELECT 1 FROM anomalies WHERE type = 'observability/source-en-retard' "
            "AND state = 'ouverte' AND refs_json LIKE ?",
            (f'%"source_id": "{source["source_id"]}"%',),
        ).fetchone()
        if already_open is not None:
            continue
        anomaly_id = f"ANOM:{uuid4().hex}"
        conn.execute(
            """
            INSERT INTO anomalies (anomaly_id, type, severity, probability, impact,
                                   recommendation, state, created_at, refs_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (anomaly_id, "observability/source-en-retard", "moyenne", 1.0, None,
             f"La source « {source['label']} » n'a pas ete recue dans sa cadence "
             "attendue : deposer le fichier ou verifier l'expediteur.",
             "ouverte", now,
             json.dumps({"source_id": source["source_id"],
                         "last_seen": source["last_seen"]}, ensure_ascii=False)),
        )
        created.append(anomaly_id)
    conn.commit()
    return created
