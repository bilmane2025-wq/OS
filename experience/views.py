"""Moteur de vues - les profondeurs d'usage du MVP (T-M25-1 a T-M25-5).

Regles d'affichage figees (Conception 6.3) :

- **Silence par defaut** : la Vue Instantanee ne montre que l'ecart et la
  decision ; le succes est cache (« tout est sous controle » suffit).
- **La confiance est visible** : chaque chiffre porte sa nature - un
  estime n'a jamais l'apparence d'un fait (marquage distinct).
- **Chaque chiffre est une porte** : la vue detail (Acces Absolu) deplie
  tout KPI/objet jusqu'a sa preuve (M24).

Ce module produit des donnees de vue (dicts) et leur rendu HTML via les
gabarits de ``experience/web/`` - servis en local par ``app.py``, aucun
appel externe. Il porte aussi la **saisie manuelle officielle**
(T-M25-5) : les formulaires de ``forms/*.json`` deviennent des evenements
``HUMAN.*``/``PERCEPTION.*`` traces, controles par l'echelle d'autorite
(M28) et journalises (M29).
"""
import html
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from calc import kpi_catalog
from core import event_store
from core.envelope import make_envelope
from governance import audit, identity_access, observability, permissions
from intent import explain, search

FORMS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "forms")
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# Ponderation de gravite pour le tri impact x urgence des priorites.
_SEVERITY_WEIGHT = {"haute": 3.0, "moyenne": 2.0, "douce": 1.0, "basse": 1.0}


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _template(name):
    with open(os.path.join(WEB_DIR, name), "r", encoding="utf-8") as handle:
        return handle.read()


def _tagged_value(kpi_row):
    """Un chiffre n'est jamais nu : valeur + nature visibles ensemble.
    Un estime est marque distinctement (jamais l'apparence d'un fait)."""
    if kpi_row is None or kpi_row["value"] is None:
        return "inconnu"
    text = f"{kpi_row['value']:.2f} EUR"
    if kpi_row["nature"] != "fait":
        text += f" [{kpi_row['nature']}]"
    return text


# ---------------------------------------------------------------- T-M25-1

def instant(conn):
    """Vue Instantanee (10 s) : phrase d'etat + tresorerie + 0-3 alertes.

    Silence par defaut : sans anomalie ouverte, une seule phrase -
    « Tout est sous controle » - et rien d'autre (le succes est cache).
    """
    anomalies = audit.open_anomalies(conn)
    alerts = anomalies[:3]
    tresorerie = kpi_catalog.get(conn, "tresorerie")

    if not alerts:
        phrase = "Tout est sous contrôle."
    else:
        phrase = f"{len(anomalies)} point(s) demande(nt) votre attention."

    return {
        "phrase": phrase,
        "tresorerie": _tagged_value(tresorerie),
        "tresorerie_nature": tresorerie["nature"] if tresorerie else "hypothèse",
        "alerts": [{"anomaly_id": a["anomaly_id"], "type": a["type"],
                    "severity": a["severity"], "recommendation": a["recommendation"]}
                   for a in alerts],
    }


def render_instant(conn):
    view = instant(conn)
    alerts_html = "".join(
        f'<li class="alerte {html.escape(a["severity"] or "")}">'
        f'{html.escape(a["type"])} — {html.escape(a["recommendation"] or "")}</li>'
        for a in view["alerts"]
    ) or ""
    return _template("instant.html").format(
        phrase=html.escape(view["phrase"]),
        tresorerie=html.escape(view["tresorerie"]),
        alertes=alerts_html,
    )


# ---------------------------------------------------------------- T-M25-2

def daily(conn):
    """Vue Quotidienne (2 min) : resultat d'hier + 3 priorites + derives.

    Priorites = anomalies ouvertes triees par **impact x urgence**
    (impact financier connu x poids de gravite), les 3 premieres.
    """
    def priority_score(anomaly):
        impact = anomaly["impact"] if anomaly["impact"] is not None else 1.0
        return impact * _SEVERITY_WEIGHT.get(anomaly["severity"], 1.0)

    anomalies = sorted(audit.open_anomalies(conn), key=priority_score, reverse=True)
    kpis = {name: kpi_catalog.get(conn, name)
            for name in ("ca", "marge", "tresorerie")}

    return {
        "resultat": {name: _tagged_value(row) for name, row in kpis.items()},
        "priorites": [{"anomaly_id": a["anomaly_id"], "type": a["type"],
                       "severity": a["severity"], "impact": a["impact"],
                       "recommendation": a["recommendation"],
                       "score": priority_score(a)}
                      for a in anomalies[:3]],
    }


def render_daily(conn):
    view = daily(conn)
    kpis_html = "".join(
        f"<li>{html.escape(name)} : {html.escape(value)}</li>"
        for name, value in view["resultat"].items())
    priorites_html = "".join(
        f'<li>{html.escape(p["type"])} — {html.escape(p["recommendation"] or "")}</li>'
        for p in view["priorites"]) or "<li>Aucune priorité.</li>"
    return _template("daily.html").format(resultat=kpis_html, priorites=priorites_html)


# ---------------------------------------------------------------- T-M25-3

def detail(conn, kpi_name=None, object_id=None):
    """Acces Absolu : de tout chiffre a sa preuve.

    - ``kpi_name`` : depliage M24 complet (valeur -> regle -> evenements
      -> fichiers d'origine).
    - ``object_id`` : fiche d'un Objet du graphe -> evenement createur ->
      fichier d'origine.
    """
    if kpi_name is not None:
        return {"kind": "kpi", "unfolded": explain.unfold(conn, kpi_name)}
    if object_id is not None:
        return {"kind": "object", "proof": search.to_proof(conn, object_id),
                "related": search.related(conn, object_id)}
    raise ValueError("detail() exige kpi_name ou object_id")


def render_detail(conn, kpi_name):
    view = detail(conn, kpi_name=kpi_name)["unfolded"]
    events_html = "".join(
        f'<li>{html.escape(e["event_id"])} — {html.escape(e["type"])} — '
        f'origine : {html.escape(e["source"] or "?")}</li>'
        for e in view["events"]) or "<li>Aucun événement source.</li>"
    value = view["kpi"]["value"]
    value_text = "inconnu" if value is None else f"{value:.4g} {view['kpi']['unit']}"
    return _template("detail.html").format(
        nom=html.escape(view["kpi"]["name"]),
        valeur=html.escape(value_text),
        nature=html.escape(view["confidence"]["nature"]),
        score=f"{view['confidence']['score']:.2f}",
        regle=html.escape(f"{view['rule']['name']}@{view['rule']['version']}"),
        evenements=events_html,
    )


# ---------------------------------------------------------------- T-M25-4

def inbox_view(conn, limit=50):
    """Ecran Inbox : chaque depot visible avec son statut, plus les
    anomalies/quarantaines ouvertes."""
    ingestions = [
        {"import_id": r[0], "ts": r[1], "file": r[2], "status": r[3],
         "new_records": r[4], "duplicates": r[5], "anomalies": r[6]}
        for r in conn.execute(
            "SELECT import_id, ts, file, status, new_records, duplicates, anomalies "
            "FROM ingestion_log ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    ]
    return {"ingestions": ingestions, "anomalies": audit.open_anomalies(conn)[:limit]}


def render_inbox(conn):
    view = inbox_view(conn)
    ingestions_html = "".join(
        f'<tr><td>{html.escape(i["ts"])}</td><td>{html.escape(i["file"] or "")}</td>'
        f'<td>{html.escape(i["status"] or "")}</td></tr>'
        for i in view["ingestions"]) or "<tr><td colspan=3>Aucun dépôt.</td></tr>"
    anomalies_html = "".join(
        f'<li>{html.escape(a["type"])} — {html.escape(a["recommendation"] or "")}</li>'
        for a in view["anomalies"]) or "<li>Aucune anomalie ouverte.</li>"
    return _template("inbox.html").format(ingestions=ingestions_html,
                                          anomalies=anomalies_html)


# ------------------------------------------------------- sante (T-M33-1)

def render_health(conn):
    report = observability.health(conn)
    sources_html = "".join(
        f'<tr><td>{html.escape(s["label"] or s["source_id"])}</td>'
        f'<td>{html.escape(s["status"])}</td>'
        f'<td>{html.escape(s["last_seen"] or "jamais")}</td></tr>'
        for s in report["sources"]) or "<tr><td colspan=3>Aucune source déclarée.</td></tr>"
    return _template("health.html").format(
        score=f"{report['score'] * 100:.0f}", sources=sources_html)


# ---------------------------------------------------------------- T-M25-5

def load_form_schemas(forms_dir=FORMS_DIR):
    """Charge les schemas de formulaires manuels (``forms/*.json``)."""
    schemas = {}
    for name in sorted(os.listdir(forms_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(forms_dir, name), "r", encoding="utf-8") as handle:
            schema = json.load(handle)
        schemas[schema["form"]] = schema
    return schemas


class FormError(ValueError):
    """Formulaire inconnu ou champ requis manquant."""


def submit_manual(conn, form, fields, author, forms_dir=FORMS_DIR):
    """Saisie manuelle officielle : le formulaire devient un evenement
    ``HUMAN.ManualEntry`` immuable.

    - Valide les champs requis du schema (``forms/*.json``).
    - Controle l'autorite de l'auteur (M28 : transition « ManualEntry »,
      N1 requis - reversible, donc jamais N5, mais jamais anonyme).
    - Trace l'acces (M29 : qui/quoi/quand dans ``access_log``).

    Returns:
        dict: ``{"event_id", "form", "event_type"}``.
    """
    schemas = load_form_schemas(forms_dir)
    if form not in schemas:
        raise FormError(f"formulaire inconnu : {form!r}")
    schema = schemas[form]

    missing = [f["name"] for f in schema["fields"]
               if f.get("required") and fields.get(f["name"]) in (None, "")]
    if missing:
        raise FormError(f"champ(s) requis manquant(s) : {missing}")

    permissions.check(conn, author, {"object_type": "ManualEntry",
                                     "action": f"saisie-{form}",
                                     "required_authority": 1})

    now = _now_iso()
    envelope = make_envelope(
        id=f"EVT:{uuid4().hex}",
        type_="HUMAN.ManualEntry",
        label=f"Saisie manuelle : {schema['label']}",
        source=f"formulaire/{form}",
        author=author,
        valid_from=now,
        ts_record=now,
        nature="fait",  # une saisie humaine assumee est un fait declare
        score=1.0,
        owner=author,
        visibility="interne",
        authority=1,
    )
    _, event_id = event_store.append(
        conn, envelope,
        payload={"form": form, "fields": dict(fields),
                 "target_event_type": schema["event_type"]},
    )
    identity_access.log_access(conn, author, "manual-entry", event_id)
    return {"event_id": event_id, "form": form, "event_type": schema["event_type"]}


def render_forms(forms_dir=FORMS_DIR):
    schemas = load_form_schemas(forms_dir)
    blocks = []
    for form, schema in schemas.items():
        fields_html = "".join(
            f'<label>{html.escape(f["label"])}'
            f'<input name="{html.escape(f["name"])}" type="{html.escape(f["type"])}"'
            f'{" required" if f.get("required") else ""}></label>'
            for f in schema["fields"])
        blocks.append(f'<form data-form="{html.escape(form)}">'
                      f'<h2>{html.escape(schema["label"])}</h2>{fields_html}'
                      f'<button type="submit">Enregistrer</button></form>')
    return _template("forms.html").format(formulaires="".join(blocks))
