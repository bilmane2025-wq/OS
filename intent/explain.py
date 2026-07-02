"""Moteur d'explicabilite - depliage jusqu'a la preuve (T-M24-1).

« D'ou sort ce chiffre ? » : de tout KPI, ``unfold`` remonte la chaine
complete - la valeur publiee, la **regle versionnee** qui la definit, les
**evenements sources** qui l'alimentent (chacun avec sa provenance :
fichier d'origine, auteur, date), les hypotheses, et la confiance
propagee. Aucun nombre orphelin (Constitution, lois 4, 8, 9).
"""
import json

from calc import kpi_catalog
from core import rules
from datetime import datetime, timezone


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def unfold(conn, kpi_name, key=kpi_catalog.KPI_KEY):
    """Deplie un KPI jusqu'a sa preuve.

    Returns:
        dict:
        - ``kpi`` : la valeur publiee (projection ``kpi``) ;
        - ``rule`` : la regle versionnee qui definit l'indicateur
          (nom, version, corps - la definition datee) ;
        - ``events`` : les evenements sources, chacun avec type, source
          (fichier d'origine), auteur, date et confiance - la preuve ;
        - ``confidence`` : nature + score propages (M13) ;
        - ``hypotheses`` : ce que le calcul suppose (liste explicite,
          vide si le KPI est entierement factuel).
    """
    detail = kpi_catalog.compute(conn, kpi_name, persist=False)
    rule = rules.get(conn, f"kpi/{kpi_name}", _now_iso())

    events = []
    for event_id in detail["events"]:
        row = conn.execute(
            "SELECT event_id, type, source, author, ts_record, valid_from, payload_json "
            "FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            continue
        stored = json.loads(row[6])
        events.append({
            "event_id": row[0], "type": row[1], "source": row[2], "author": row[3],
            "ts_record": row[4], "valid_from": row[5],
            "confidence": stored["envelope"]["confidence"],
            "payload": stored["payload"],
        })

    hypotheses = []
    if detail["value"] is None:
        hypotheses.append("valeur incalculable : aucune donnee source - "
                          "le systeme ne l'invente pas")
    if detail["nature"] != "fait":
        hypotheses.append(f"au moins une source est de nature '{detail['nature']}' : "
                          "le KPI herite de la confiance la plus faible")

    return {
        "kpi": {"name": kpi_name, "key": key, "value": detail["value"],
                "unit": detail["unit"]},
        "rule": {"name": rule["name"], "version": rule["version"], "body": rule["body"]},
        "events": events,
        "confidence": {"nature": detail["nature"], "score": detail["score"]},
        "hypotheses": hypotheses,
    }
