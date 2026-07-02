"""Proactivite niveaux 1-2 : reactif / proactif (T-M26-1).

Niveau 1 (reactif) : le systeme repond quand on l'interroge - ce sont
les vues et la conversation, deja en place. Niveau 2 (proactif) : des
**regles de seuil versionnees** (famille ``alert-threshold/*`` du
corpus, T-M02-2) produisent des alertes **groupees** destinees a la Vue
Quotidienne. Les niveaux predictif et strategique sont explicitement V2
(Backlog).

Regles figees (Conception 6.4 ; Constitution) :
- **jamais d'alerte sur le non-actionnable** : un KPI sans donnee ne
  declenche pas d'alerte de seuil (c'est le watchdog M33 qui reclame la
  source manquante - une alerte "tresorerie basse" sans chiffre ne donne
  aucune decision a prendre) ;
- **regroupement** : les alertes de meme type sont presentees en une
  seule sollicitation portant le compte, jamais en rafale.
"""
from datetime import datetime, timezone

from calc import kpi_catalog
from core import rules
from governance import audit

# Regle de seuil -> KPI surveille et sens de comparaison.
THRESHOLD_RULES = {
    "alert-threshold/tresorerie-basse": {"kpi": "tresorerie", "direction": "below"},
}

_SEVERITY_RANK = {"haute": 0, "moyenne": 1, "douce": 2, "basse": 2}


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def threshold_alerts(conn, at_date=None):
    """Applique chaque regle de seuil versionnee applicable a ``at_date``
    au KPI qu'elle surveille.

    Un KPI dont la valeur est inconnue (``None``) ne produit **aucune**
    alerte de seuil : il n'y a rien d'actionnable dans « peut-etre en
    dessous » - l'absence de donnee est deja portee, elle, par le
    watchdog des sources (M33).
    """
    at_date = at_date or _now_iso()
    alerts = []
    for rule_name, spec in THRESHOLD_RULES.items():
        rule = rules.get(conn, rule_name, at_date)
        if rule is None:
            continue
        kpi_row = kpi_catalog.get(conn, spec["kpi"])
        if kpi_row is None or kpi_row["value"] is None:
            continue  # non-actionnable : pas de chiffre, pas d'alerte de seuil

        threshold = rule["body"]["seuil_montant"]
        crossed = (kpi_row["value"] < threshold if spec["direction"] == "below"
                   else kpi_row["value"] > threshold)
        if crossed:
            alerts.append({
                "type": f"seuil/{spec['kpi']}",
                "severity": rule["body"].get("gravite", "haute"),
                "message": (f"{spec['kpi']} = {kpi_row['value']:.2f} "
                            f"{kpi_row['unit'] or ''} (seuil : {threshold})"),
                "recommendation": rule["body"].get(
                    "recommandation",
                    f"Examiner le KPI {spec['kpi']} et decider d'une action."),
                "rule": f"{rule['name']}@{rule['version']}",
                "refs": [spec["kpi"]],
            })
    return alerts


def collect_alerts(conn, at_date=None):
    """Toutes les sollicitations candidates du cycle : alertes de seuil
    (regles versionnees) + anomalies ouvertes (M31), normalisees dans le
    meme format. Chacune est actionnable par construction (une anomalie
    porte toujours sa recommandation - loi 21)."""
    alerts = list(threshold_alerts(conn, at_date))
    for anomaly in audit.open_anomalies(conn):
        alerts.append({
            "type": anomaly["type"],
            "severity": anomaly["severity"] or "moyenne",
            "message": anomaly["type"],
            "recommendation": anomaly["recommendation"],
            "rule": None,
            "refs": [anomaly["anomaly_id"]],
        })
    return alerts


def group_alerts(alerts):
    """Regroupe les alertes de meme type en une seule sollicitation
    (comptee), triee par gravite puis par type - jamais de rafale de
    notifications identiques."""
    groups = {}
    for alert in alerts:
        group = groups.setdefault(alert["type"], {
            "type": alert["type"], "severity": alert["severity"],
            "recommendation": alert["recommendation"], "count": 0, "refs": [],
        })
        group["count"] += 1
        group["refs"].extend(alert["refs"])
        if _SEVERITY_RANK.get(alert["severity"], 2) < _SEVERITY_RANK.get(group["severity"], 2):
            group["severity"] = alert["severity"]

    return sorted(groups.values(),
                  key=lambda g: (_SEVERITY_RANK.get(g["severity"], 2), g["type"]))
