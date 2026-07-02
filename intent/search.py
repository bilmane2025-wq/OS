"""Recherche universelle locale (T-M23-1).

Index lexical **local** sur les Objets du graphe (label + corps +
enveloppe) : aucune base parallele (frontiere M23 - la recherche est une
projection de lecture sur ``objects``/``links``), aucun appel externe.

Du resultat a la preuve : chaque resultat porte son type, son objet
complet, et ``to_proof`` remonte de l'objet a l'evenement createur
(provenance) puis au fichier d'origine - Acces Absolu (Conception 12.3).
"""
import json

from graph import graph_engine


def query(conn, text, filters=None):
    """Recherche lexicale sur tous les Objets.

    Args:
        conn: connexion SQLite ouverte.
        text: texte cherche (insensible a la casse, sous-chaine).
        filters: dict optionnel - ``{"type": "Facture"}`` restreint aux
            Objets de ce type ; ``{"state": ...}`` a cet etat.

    Returns:
        list[dict]: resultats **types et regroupes** - chaque entree :
        ``{"object_id", "type", "label", "state", "score", "object"}``,
        tries par pertinence (label > corps) puis par identifiant
        (ordre stable, explicable - pas de boite noire de pertinence).
    """
    filters = filters or {}
    needle = (text or "").strip().lower()
    if not needle:
        return []

    clauses, params = [], []
    if filters.get("type"):
        clauses.append("type = ?")
        params.append(filters["type"])
    if filters.get("state"):
        clauses.append("state = ?")
        params.append(filters["state"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    results = []
    for row in conn.execute(
        f"SELECT object_id, type, label, body_json, envelope_json, state "
        f"FROM objects {where} ORDER BY object_id", params
    ).fetchall():
        object_id, type_, label, body_json, envelope_json, state = row
        label_hit = needle in (label or "").lower()
        body_hit = needle in body_json.lower() or needle in envelope_json.lower()
        if not (label_hit or body_hit):
            continue
        results.append({
            "object_id": object_id, "type": type_, "label": label, "state": state,
            # Pertinence explicable : 2 = trouve dans le libelle,
            # 1 = trouve dans le corps/l'enveloppe.
            "score": 2 if label_hit else 1,
            "object": {"body": json.loads(body_json)},
        })

    results.sort(key=lambda r: (-r["score"], r["object_id"]))
    return results


def related(conn, object_id):
    """Liens et voisins d'un resultat (navigation de proche en proche)."""
    return graph_engine.neighbors(conn, object_id, "both")


def to_proof(conn, object_id):
    """De l'objet a sa preuve : l'evenement createur (provenance de
    l'enveloppe) et le fichier d'origine - un geste, Acces Absolu."""
    obj = graph_engine.get_object(conn, object_id)
    if obj is None:
        return None
    event_id = obj["envelope"]["provenance"]["event_id"]
    row = conn.execute(
        "SELECT event_id, type, source, author, ts_record FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    proof_event = None
    if row is not None:
        proof_event = {"event_id": row[0], "type": row[1], "source": row[2],
                       "author": row[3], "ts_record": row[4]}
    return {"object_id": object_id, "event": proof_event,
            "origin": proof_event["source"] if proof_event else None}
