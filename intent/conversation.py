"""Resolveur d'intentions deterministe - sans LLM, sans API (T-M22-1).

Routeur par motifs (``data/intents.json``) : une question cadree est
reconnue par sous-chaine, resolue par une requete KPI/graphe/anomalies
locale, et la reponse porte **toujours** la confiance (nature + score),
la preuve (evenements sources via M24), et se termine par une **action**
possible (Conception 5.1).

Regle anti-invention (frontiere) : une question hors du perimetre des
intentions declarees recoit « je ne sais pas repondre a ca pour
l'instant » - **jamais** une reponse devinee. Zero appel externe.
"""
import json
import os
import unicodedata

from calc import kpi_catalog
from governance import audit
from intent import explain, search

DEFAULT_INTENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "intents.json")

UNKNOWN_ANSWER = "Je ne sais pas répondre à ça pour l'instant."

_NATURE_LABEL = {"fait": "fait", "mesuré": "mesuré", "estimé": "estimé",
                 "hypothèse": "hypothèse", "projection": "projection"}


def load_intents(path=DEFAULT_INTENTS_PATH):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _fold(text):
    """Normalisation deterministe pour la comparaison de motifs :
    minuscules + suppression des diacritiques (« trésorerie » et
    « tresorerie » designent la meme intention). Aucun modele, aucune
    heuristique : une transformation Unicode standard, reversible en
    inspection."""
    decomposed = unicodedata.normalize("NFD", (text or "").strip().lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def resolve_intent(question, intents=None):
    """Trouve l'intention declaree dont un motif apparait dans la
    question (insensible a la casse et aux accents). ``None`` si aucune -
    jamais une intention devinee."""
    normalized = _fold(question)
    for intent in intents or load_intents():
        if any(_fold(pattern) in normalized for pattern in intent["patterns"]):
            return intent
    return None


def _format_value(value, unit):
    if value is None:
        return "inconnu (aucune donnée)"
    if unit == "ratio":
        return f"{value * 100:.1f} %"
    if unit == "EUR":
        return f"{value:.2f} EUR"
    return f"{value:.2f} {unit}"


def _answer_kpi(conn, intent):
    unfolded = explain.unfold(conn, intent["kpi"])
    value_text = _format_value(unfolded["kpi"]["value"], unfolded["kpi"]["unit"])
    nature = unfolded["confidence"]["nature"]
    text = (f"{intent['kpi']} : {value_text} "
            f"[{_NATURE_LABEL[nature]}, confiance {unfolded['confidence']['score']:.2f}]")
    return {
        "intent": intent["intent"],
        "answer": text,
        "value": unfolded["kpi"]["value"],
        "confidence": unfolded["confidence"],
        "proof": {"rule": unfolded["rule"]["name"] + "@" + str(unfolded["rule"]["version"]),
                  "events": [e["event_id"] for e in unfolded["events"]],
                  "sources": sorted({e["source"] for e in unfolded["events"]})},
        "action": intent["action"],
        "known": True,
    }


def _answer_que_faire(conn, intent):
    anomalies = audit.open_anomalies(conn)
    if not anomalies:
        answer = "Rien d'urgent : aucune anomalie ouverte. [fait, confiance 1.00]"
        action = "Aucune action requise."
    else:
        top = anomalies[0]
        answer = (f"{len(anomalies)} anomalie(s) ouverte(s). La plus recente : "
                  f"{top['type']} (gravité {top['severity']}). "
                  f"Recommandation : {top['recommendation']} [fait, confiance 1.00]")
        action = top["recommendation"]
    return {"intent": intent["intent"], "answer": answer,
            "confidence": {"nature": "fait", "score": 1.0},
            "proof": {"anomalies": [a["anomaly_id"] for a in anomalies]},
            "action": action, "known": True}


def _answer_recherche(conn, intent, question):
    # Le terme cherche = ce qui suit le motif declencheur.
    normalized = _fold(question)
    term = normalized
    for pattern in intent["patterns"]:
        folded_pattern = _fold(pattern)
        if folded_pattern in normalized:
            term = normalized.split(folded_pattern, 1)[1].strip(" ?!.")
            break
    results = search.query(conn, term)
    if not results:
        answer = f"Aucun objet trouvé pour « {term} ». [fait, confiance 1.00]"
    else:
        top = results[0]
        answer = (f"{len(results)} résultat(s) pour « {term} ». Premier : "
                  f"{top['type']} « {top['label']} ». [fait, confiance 1.00]")
    return {"intent": intent["intent"], "answer": answer,
            "confidence": {"nature": "fait", "score": 1.0},
            "proof": {"results": [r["object_id"] for r in results]},
            "action": intent["action"], "known": True}


def ask(conn, question, intents=None):
    """Repond a une question cadree, localement, sans invention.

    Returns:
        dict: ``{"intent", "answer", "confidence", "proof", "action",
        "known"}``. Question inconnue -> ``known=False``, reponse
        « je ne sais pas », aucune valeur produite.
    """
    intent = resolve_intent(question, intents)
    if intent is None:
        return {"intent": None, "answer": UNKNOWN_ANSWER, "confidence": None,
                "proof": None, "action": None, "known": False}

    if intent["intent"] == "que_faire":
        return _answer_que_faire(conn, intent)
    if intent["intent"] == "recherche":
        return _answer_recherche(conn, intent, question)
    if intent.get("kpi"):
        return _answer_kpi(conn, intent)

    return {"intent": intent["intent"], "answer": UNKNOWN_ANSWER, "confidence": None,
            "proof": None, "action": intent.get("action"), "known": False}
