"""Catalogue de KPI - chaque indicateur est une regle versionnee
(T-M14-1).

Les 8 KPI du MVP (Backlog) : CA, marge, food cost, ticket moyen,
commandes/jour, tresorerie, commission, dependance fournisseur. Chaque
KPI :

- est **defini par une regle versionnee** (``kpi/*`` du corpus seed,
  T-M02-2) : changer une definition = nouvelle version, le passe garde
  l'ancienne (Chronos) ;
- se calcule depuis le **journal** (les evenements sont la seule verite) ;
- porte sa **version de regle** et sa **confiance** (nature + score),
  propagee depuis les evenements sources par l'algebre M13 - aucune
  valeur nue ;
- s'ecrit dans la projection ``kpi`` (reconstructible) ;
- se recalcule **incrementalement** via le DAG M12 (chaque KPI declare
  ses types d'evenements sources).
"""
import json
from datetime import datetime, timezone

from calc import confidence, derivation
from core import event_store, rules

KPI_KEY = "global"

# Types d'evenements sources par KPI : la declaration de dependance du DAG.
KPI_SOURCES = {
    "ca": ("PERCEPTION.OrderObserved", "HUMAN.ManualEntry"),
    "marge": ("PERCEPTION.OrderObserved", "PERCEPTION.InvoiceReceived", "HUMAN.ManualEntry"),
    "food_cost": ("PERCEPTION.OrderObserved", "PERCEPTION.InvoiceReceived", "HUMAN.ManualEntry"),
    "ticket_moyen": ("PERCEPTION.OrderObserved", "HUMAN.ManualEntry"),
    "commandes_jour": ("PERCEPTION.OrderObserved", "HUMAN.ManualEntry"),
    "tresorerie": ("PERCEPTION.StatementLine", "HUMAN.ManualEntry"),
    "commission": ("PERCEPTION.OrderObserved", "HUMAN.ManualEntry"),
    "dependance_fournisseur": ("PERCEPTION.InvoiceReceived", "HUMAN.ManualEntry"),
}

_UNITS = {"food_cost": "ratio", "dependance_fournisseur": "ratio",
          "commandes_jour": "commandes/jour"}


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _to_number(value):
    """Convertit un champ montant en nombre (virgule decimale acceptee).
    ``None`` si illisible - jamais un zero invente."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ".").replace(" ", ""))
        except ValueError:
            return None
    return None


def _fields_of(payload):
    for key in ("fields", "record"):
        if isinstance(payload.get(key), dict):
            return payload[key]
    return payload


def _collect(conn, event_types, manual_forms=()):
    """Evenements sources d'un KPI : (event, champs metier, confiance).
    Une saisie manuelle (HUMAN.ManualEntry) ne compte que si son
    formulaire correspond au KPI (ex. 'vente' pour le CA)."""
    items = []
    for event in event_store.read(conn):
        if event["type"] not in event_types:
            continue
        payload = event["payload"]
        if event["type"] == "HUMAN.ManualEntry" and payload.get("form") not in manual_forms:
            continue
        conf = event["envelope"]["confidence"]
        items.append((event, _fields_of(payload), (conf["nature"], conf["score"])))
    return items


def _sales(conn):
    return _collect(conn, ("PERCEPTION.OrderObserved", "HUMAN.ManualEntry"), ("vente",))


def _purchases(conn):
    return _collect(conn, ("PERCEPTION.InvoiceReceived", "HUMAN.ManualEntry"), ("facture", "depense"))


def _statements(conn):
    return _collect(conn, ("PERCEPTION.StatementLine", "HUMAN.ManualEntry"), ("depense",))


def _sum_amounts(items, field="montant"):
    total, used = 0.0, []
    for event, fields, conf in items:
        amount = _to_number(fields.get(field))
        if amount is None:
            continue  # illisible : ignore, jamais invente
        total += amount
        used.append((event, conf))
    return total, used


def _detail(value, unit, used, extra=None):
    conf = confidence.combine(conf for _, conf in used)
    return {"value": value, "unit": unit, "nature": conf["nature"],
            "score": conf["score"], "events": [event["event_id"] for event, _ in used],
            **(extra or {})}


def _compute_ca(conn):
    total, used = _sum_amounts(_sales(conn))
    return _detail(total if used else None, "EUR", used)


def _compute_couts(conn):
    total, used = _sum_amounts(_purchases(conn))
    return _detail(total if used else None, "EUR", used)


def _compute_marge(conn):
    ca, couts = _compute_ca(conn), _compute_couts(conn)
    used_events = ca["events"] + couts["events"]
    if ca["value"] is None:
        return {"value": None, "unit": "EUR", "nature": "hypothèse", "score": 0.0,
                "events": used_events}
    value = ca["value"] - (couts["value"] or 0.0)
    conf = confidence.combine([(ca["nature"], ca["score"]), (couts["nature"], couts["score"])]
                              if couts["value"] is not None else [(ca["nature"], ca["score"])])
    return {"value": value, "unit": "EUR", "nature": conf["nature"], "score": conf["score"],
            "events": used_events}


def _compute_food_cost(conn):
    ca, couts = _compute_ca(conn), _compute_couts(conn)
    used_events = ca["events"] + couts["events"]
    if not ca["value"]:  # None ou 0 : ratio incalculable, jamais invente
        return {"value": None, "unit": "ratio", "nature": "hypothèse", "score": 0.0,
                "events": used_events}
    conf = confidence.combine([(ca["nature"], ca["score"]), (couts["nature"], couts["score"])])
    return {"value": (couts["value"] or 0.0) / ca["value"], "unit": "ratio",
            "nature": conf["nature"], "score": conf["score"], "events": used_events}


def _compute_ticket_moyen(conn):
    total, used = _sum_amounts(_sales(conn))
    if not used:
        return _detail(None, "EUR", used)
    return _detail(total / len(used), "EUR", used)


def _compute_commandes_jour(conn):
    items = _sales(conn)
    days = set()
    used = []
    for event, fields, conf in items:
        day = str(fields.get("date") or event["valid_from"])[:10]
        days.add(day)
        used.append((event, conf))
    if not used:
        return _detail(None, "commandes/jour", used)
    return _detail(len(used) / len(days), "commandes/jour", used)


def _compute_tresorerie(conn):
    total, used = _sum_amounts(_statements(conn))
    return _detail(total if used else None, "EUR", used)


def _compute_commission(conn):
    total, used = _sum_amounts(_sales(conn), field="commission")
    return _detail(total if used else None, "EUR", used)


def _compute_dependance_fournisseur(conn):
    per_supplier, used = {}, []
    for event, fields, conf in _purchases(conn):
        amount = _to_number(fields.get("montant"))
        supplier = fields.get("fournisseur")
        if amount is None or not supplier:
            continue
        per_supplier[supplier] = per_supplier.get(supplier, 0.0) + amount
        used.append((event, conf))
    total = sum(per_supplier.values())
    if not total:
        return _detail(None, "ratio", used)
    return _detail(max(per_supplier.values()) / total, "ratio", used,
                   extra={"par_fournisseur": per_supplier})


_COMPUTERS = {
    "ca": _compute_ca,
    "marge": _compute_marge,
    "food_cost": _compute_food_cost,
    "ticket_moyen": _compute_ticket_moyen,
    "commandes_jour": _compute_commandes_jour,
    "tresorerie": _compute_tresorerie,
    "commission": _compute_commission,
    "dependance_fournisseur": _compute_dependance_fournisseur,
}

KPI_NAMES = sorted(_COMPUTERS)


def compute(conn, name, persist=True, at_date=None):
    """Calcule un KPI et (par defaut) l'ecrit dans la projection ``kpi``.

    Returns:
        dict: ``{"name", "value", "unit", "nature", "score", "events",
        "rule_name", "rule_version"}`` - jamais une valeur nue.
    """
    if name not in _COMPUTERS:
        raise LookupError(f"KPI inconnu : {name}")

    rule = rules.get(conn, f"kpi/{name}", at_date or _now_iso())
    if rule is None:
        raise LookupError(f"regle kpi/{name} absente (seed non chargee ?)")

    detail = _COMPUTERS[name](conn)
    detail.update({"name": name, "rule_name": rule["name"], "rule_version": rule["version"],
                   "unit": detail.get("unit") or _UNITS.get(name, "EUR")})

    if persist:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO kpi (name, key, value, unit, nature, confidence, rule_version, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name, key) DO UPDATE SET
                value = excluded.value, unit = excluded.unit, nature = excluded.nature,
                confidence = excluded.confidence, rule_version = excluded.rule_version,
                computed_at = excluded.computed_at
            """,
            (name, KPI_KEY, detail["value"], detail["unit"], detail["nature"],
             detail["score"], rule["version"], now),
        )
        conn.commit()
        detail["computed_at"] = now
    return detail


def compute_all(conn):
    """Calcule les 8 KPI du MVP (amorcage/reconstruction uniquement - le
    flux normal passe par le DAG incremental)."""
    return {name: compute(conn, name) for name in KPI_NAMES}


def get(conn, name, key=KPI_KEY):
    row = conn.execute(
        "SELECT name, key, value, unit, nature, confidence, rule_version, computed_at "
        "FROM kpi WHERE name = ? AND key = ?", (name, key)
    ).fetchone()
    if row is None:
        return None
    return {"name": row[0], "key": row[1], "value": row[2], "unit": row[3],
            "nature": row[4], "score": row[5], "rule_version": row[6],
            "computed_at": row[7]}


def register_derivations():
    """Declare chaque KPI dans le DAG M12 avec ses types d'evenements
    sources - c'est ce qui rend le recalcul incremental et cible."""
    for name in KPI_NAMES:
        derivation.register(
            f"kpi/{name}", KPI_SOURCES[name],
            lambda conn, _name=name: compute(conn, _name),
        )
