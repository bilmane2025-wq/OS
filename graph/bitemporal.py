"""Requete bi-temporelle sur le graphe (T-M10-1).

Reconstruit « l'etat connu a une date » en croisant les deux horloges
(Conception 3.8) :

- **valid-time** (verite-monde) : seuls les evenements dont
  ``valid_from <= valid_date`` participent a l'etat.
- **decision-time** (connaissance-systeme) : seuls les evenements deja
  enregistres a ``decision_date`` (``ts_record <= decision_date``)
  participent - ce que le systeme *savait* a cette date, pas ce qu'il a
  appris depuis.

« L'etat connu au 12/06 » (decision-time) est donc distinct de « l'etat
vrai au 03/06 » (valid-time) - et les deux sont exacts (critere backlog).

La reconstruction se fait dans une base **en memoire jetable** : le
graphe courant (projection ``objects``/``links`` de ``data/eos.db``)
n'est jamais touche par une requete au passe.
"""
import sqlite3
from datetime import datetime

import app as eos_app
from core import event_store
from graph import graph_engine


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def state_as_of(conn, valid_date, decision_date=None):
    """Etat du graphe tel qu'il etait connu.

    Args:
        conn: connexion SQLite sur la base reelle (lecture du journal).
        valid_date: borne sur le temps du monde (ISO-8601 avec fuseau) -
            les evenements dont ``valid_from`` est posterieur sont exclus.
        decision_date: borne sur le temps du systeme - les evenements
            enregistres apres cette date sont exclus (``None`` = tout ce
            qui est connu aujourd'hui).

    Returns:
        dict: ``{"objects": {object_id: obj}, "links": [...],
        "event_count": n}`` - reconstruit par rejeu, sans toucher a la
        projection courante.
    """
    events = event_store.read(conn, decision_time=decision_date)
    valid_boundary = _parse(valid_date)
    selected = [e for e in events if _parse(e["valid_from"]) <= valid_boundary]

    scratch = sqlite3.connect(":memory:")
    try:
        scratch.executescript(eos_app.SCHEMA)
        graph_engine.apply_events(scratch, selected)

        objects = {}
        for row in scratch.execute(
            "SELECT object_id FROM objects ORDER BY object_id"
        ).fetchall():
            objects[row[0]] = graph_engine.get_object(scratch, row[0])
        links = scratch.execute(
            "SELECT link_id, src, rel, dst FROM links ORDER BY link_id"
        ).fetchall()
    finally:
        scratch.close()

    return {"objects": objects, "links": links, "event_count": len(selected)}
