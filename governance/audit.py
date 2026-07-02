"""Audit permanent - reconciliation & anomalies (T-M31-1).

Applique les **regles de rapprochement versionnees** (famille
``reconciliation/*`` du corpus, T-M02-2) et transforme tout ecart
au-dela du seuil en **anomalie complete** : gravite, probabilite, impact
financier, recommandation (Constitution, loi 21). L'audit ne corrige
jamais en silence (frontiere M31) : il constate, trace, recommande.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

from calc import kpi_catalog
from core import rules

RECONCILIATION_RULE = "reconciliation/rapprochement-encaissement-vente"


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _create_anomaly(conn, type_, severity, probability, impact, recommendation, refs):
    anomaly_id = f"ANOM:{uuid4().hex}"
    conn.execute(
        """
        INSERT INTO anomalies (anomaly_id, type, severity, probability, impact,
                               recommendation, state, created_at, refs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (anomaly_id, type_, severity, probability, impact, recommendation,
         "ouverte", _now_iso(), json.dumps(refs, ensure_ascii=False)),
    )
    conn.commit()
    return anomaly_id


def reconcile_collections_vs_sales(conn, at_date=None):
    """Rapprochement encaissements bancaires <-> ventes declarees.

    Compare la somme des encaissements (lignes de releve positives) a la
    somme des ventes (commandes observees). Si l'ecart relatif depasse le
    seuil de la regle versionnee applicable, une anomalie est creee avec
    gravite/probabilite/impact/recommandation issus de la regle.

    Returns:
        dict: ``{"encaissements", "ventes", "ecart", "ecart_relatif",
        "seuil", "rule", "anomaly_id" (ou None)}``.
    """
    at_date = at_date or _now_iso()
    rule = rules.get(conn, RECONCILIATION_RULE, at_date)
    if rule is None:
        raise LookupError(f"regle absente : {RECONCILIATION_RULE}")

    statements = kpi_catalog._statements(conn)
    collections = sum(
        amount for _, fields, _ in statements
        if (amount := kpi_catalog._to_number(fields.get("montant"))) is not None and amount > 0
    )
    sales_detail = kpi_catalog.compute(conn, "ca", persist=False)
    sales = sales_detail["value"] or 0.0

    gap = abs(collections - sales)
    relative_gap = gap / sales if sales else (1.0 if gap else 0.0)
    threshold = rule["body"]["seuil_pourcentage"]

    anomaly_id = None
    if relative_gap > threshold:
        anomaly_id = _create_anomaly(
            conn,
            type_="reconciliation/ecart-encaissement-vente",
            severity=rule["body"].get("gravite", "haute"),
            probability=1.0,
            impact=gap,
            recommendation=rule["body"].get(
                "recommandation",
                "Verifier les encaissements manquants ou les ventes non declarees."),
            refs={"encaissements": collections, "ventes": sales,
                  "ecart_relatif": relative_gap,
                  "rule": f"{rule['name']}@{rule['version']}"},
        )

    return {"encaissements": collections, "ventes": sales, "ecart": gap,
            "ecart_relatif": relative_gap, "seuil": threshold,
            "rule": f"{rule['name']}@{rule['version']}", "anomaly_id": anomaly_id}


def open_anomalies(conn):
    """Anomalies ouvertes, les plus recentes d'abord - chaque anomalie
    porte gravite, probabilite, impact et recommandation (loi 21)."""
    rows = conn.execute(
        "SELECT anomaly_id, type, severity, probability, impact, recommendation, "
        "created_at, refs_json FROM anomalies WHERE state = 'ouverte' "
        "ORDER BY created_at DESC"
    ).fetchall()
    return [{"anomaly_id": r[0], "type": r[1], "severity": r[2], "probability": r[3],
             "impact": r[4], "recommendation": r[5], "created_at": r[6],
             "refs": json.loads(r[7]) if r[7] else {}} for r in rows]
