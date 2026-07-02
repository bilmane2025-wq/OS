"""Trous & contradictions - l'inconnu et le desaccord sont des etats
explicites (T-M11-1, T-M11-2).

- **Le trou est un Objet** : une donnee attendue absente devient un Objet
  ``Trou`` visible (forme attendue, source attendue, delai), accompagne
  d'un evenement ``SYSTEM.GapDetected`` et d'une anomalie douce - jamais
  un zero muet (Constitution : « le systeme n'invente jamais ; s'il
  ignore, il le dit »). A l'arrivee du reel, le trou est resolu, trace.

- **La contradiction est un etat** : deux faits incompatibles deviennent
  un Objet ``Tension`` qui conserve les deux versions rivales, relie par
  un Lien ``contredit`` a l'objet conteste. La resolution suit la regle
  figee « preuve > autorite > escalade humaine » (Conception 4.4) et
  produit un evenement ``SYSTEM.ContradictionResolved`` - aucune ecrasure
  silencieuse, les deux versions restent conservees dans la tension.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

from core import event_store
from core.envelope import make_envelope
from graph import graph_engine

DEFAULT_AUTHOR = "system:gaps"


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _system_event(conn, type_, label, payload, nature="fait", score=1.0):
    now = _now_iso()
    envelope = make_envelope(
        id=f"EVT:{uuid4().hex}", type_=type_, label=label,
        source="system", author=DEFAULT_AUTHOR,
        valid_from=now, ts_record=now, nature=nature, score=score,
        owner="system", visibility="interne", authority=1,
    )
    _, event_id = event_store.append(conn, envelope, payload=payload)
    return event_id, now


def declare(conn, expected):
    """Declare un trou : une donnee attendue est absente.

    Args:
        conn: connexion SQLite ouverte.
        expected: dict decrivant l'attendu - ``label`` (requis),
            ``expected_type`` (forme attendue, ex. "releve bancaire"),
            ``expected_source`` (source attendue), ``due`` (delai/date
            attendue, optionnel).

    Returns:
        dict: ``{"gap_id", "event_id", "anomaly_id"}``.
    """
    event_id, now = _system_event(
        conn, "SYSTEM.GapDetected", f"Trou : {expected['label']}", dict(expected)
    )
    event = {
        "event_id": event_id, "source": "system", "author": DEFAULT_AUTHOR,
        "valid_from": now, "ts_record": now,
        "envelope": {"confidence": {"nature": "fait", "score": 1.0}, "label": ""},
        "payload": expected, "type": "SYSTEM.GapDetected",
    }
    gap_id = graph_engine.upsert_object(
        conn, "Trou", f"trou:{event_id}", label=f"Trou : {expected['label']}",
        body=dict(expected, resolu_par=None), event=event, state="ouvert",
        nature="hypothèse", score=0.0,
    )

    anomaly_id = f"ANOM:{uuid4().hex}"
    conn.execute(
        """
        INSERT INTO anomalies (anomaly_id, type, severity, probability, impact,
                               recommendation, state, created_at, refs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (anomaly_id, "gap/donnee-attendue-absente", "douce", 1.0, None,
         f"Deposer la source attendue ({expected.get('expected_source', 'inconnue')}) "
         "ou saisir la donnee manuellement.",
         "ouverte", now,
         json.dumps({"gap_id": gap_id, "event_id": event_id}, ensure_ascii=False)),
    )
    conn.commit()
    return {"gap_id": gap_id, "event_id": event_id, "anomaly_id": anomaly_id}


def resolve(conn, gap_id, real_event_id):
    """Resout un trou a l'arrivee du reel : l'Objet Trou passe a l'etat
    « resolu » (il n'est jamais supprime - loi 2), relie a l'evenement
    reel, et la resolution est tracee au journal."""
    gap = graph_engine.get_object(conn, gap_id)
    if gap is None:
        raise LookupError(f"trou inconnu : {gap_id}")

    event_id, now = _system_event(
        conn, "SYSTEM.Reconciliation", f"Trou resolu : {gap['label']}",
        {"gap_id": gap_id, "resolved_by_event": real_event_id},
    )
    event = {
        "event_id": event_id, "source": "system", "author": DEFAULT_AUTHOR,
        "valid_from": now, "ts_record": now,
        "envelope": {"confidence": {"nature": "fait", "score": 1.0}, "label": ""},
        "payload": {}, "type": "SYSTEM.Reconciliation",
    }
    graph_engine.upsert_object(
        conn, "Trou", f"trou:{gap['envelope']['provenance']['event_id']}",
        label=gap["label"], body=dict(gap["body"], resolu_par=real_event_id),
        event=event, state="resolu", nature="fait", score=1.0,
    )
    conn.execute(
        "UPDATE anomalies SET state = 'resolue' WHERE refs_json LIKE ?",
        (f'%"gap_id": "{gap_id}"%',),
    )
    conn.commit()
    return {"gap_id": gap_id, "event_id": event_id}


def declare_contradiction(conn, subject_object_id, version_a, version_b):
    """Declare une contradiction entre deux versions rivales d'un meme
    fait. Les deux versions sont **conservees telles quelles** dans le
    corps de la Tension - aucune n'ecrase l'autre.

    Args:
        subject_object_id: l'Objet du graphe sur lequel porte le desaccord.
        version_a / version_b: dicts ``{"value", "source", "event_id",
            "score", "authority"}`` decrivant chaque version rivale.

    Returns:
        dict: ``{"tension_id", "event_id"}``.
    """
    event_id, now = _system_event(
        conn, "SYSTEM.GapDetected", "Contradiction detectee",
        {"subject": subject_object_id, "version_a": version_a, "version_b": version_b},
    )
    event = {
        "event_id": event_id, "source": "system", "author": DEFAULT_AUTHOR,
        "valid_from": now, "ts_record": now,
        "envelope": {"confidence": {"nature": "fait", "score": 1.0}, "label": ""},
        "payload": {}, "type": "SYSTEM.GapDetected",
    }
    tension_id = graph_engine.upsert_object(
        conn, "Tension", f"tension:{event_id}",
        label=f"Contradiction sur {subject_object_id}",
        body={"subject": subject_object_id, "version_a": version_a,
              "version_b": version_b, "resolution": None},
        event=event, state="ouverte", nature="hypothèse", score=0.5,
    )
    graph_engine.upsert_link(conn, tension_id, "contredit", subject_object_id, event)
    conn.commit()
    return {"tension_id": tension_id, "event_id": event_id}


def resolve_contradiction(conn, tension_id):
    """Resout une tension par la regle figee : **preuve** (score de
    confiance le plus haut) > **autorite** (niveau le plus haut) >
    **escalade humaine** (aucun des deux ne tranche).

    La version retenue est designee, les deux versions restent conservees
    dans la tension, et un evenement ``SYSTEM.ContradictionResolved``
    trace la resolution (qui a gagne, par quel critere).
    """
    tension = graph_engine.get_object(conn, tension_id)
    if tension is None:
        raise LookupError(f"tension inconnue : {tension_id}")

    version_a, version_b = tension["body"]["version_a"], tension["body"]["version_b"]

    if version_a.get("score", 0) != version_b.get("score", 0):
        winner = "version_a" if version_a.get("score", 0) > version_b.get("score", 0) else "version_b"
        criterion = "preuve"
    elif version_a.get("authority", 0) != version_b.get("authority", 0):
        winner = "version_a" if version_a.get("authority", 0) > version_b.get("authority", 0) else "version_b"
        criterion = "autorite"
    else:
        winner, criterion = None, "escalade-humaine"

    resolution = {"winner": winner, "criterion": criterion}
    event_id, now = _system_event(
        conn, "SYSTEM.ContradictionResolved",
        f"Contradiction resolue ({criterion})",
        {"tension_id": tension_id, "resolution": resolution,
         "version_a": version_a, "version_b": version_b},
    )
    event = {
        "event_id": event_id, "source": "system", "author": DEFAULT_AUTHOR,
        "valid_from": now, "ts_record": now,
        "envelope": {"confidence": {"nature": "fait", "score": 1.0}, "label": ""},
        "payload": {}, "type": "SYSTEM.ContradictionResolved",
    }
    new_state = "resolue" if winner else "escalade-humaine"
    graph_engine.upsert_object(
        conn, "Tension", f"tension:{tension['envelope']['provenance']['event_id']}",
        label=tension["label"],
        body=dict(tension["body"], resolution=resolution),
        event=event, state=new_state,
        nature="fait" if winner else "hypothèse", score=1.0 if winner else 0.5,
    )
    conn.commit()
    return {"tension_id": tension_id, "event_id": event_id, "resolution": resolution}
