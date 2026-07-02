"""Moteur de derivations - DAG incremental reactif (T-M12-1).

Chaque valeur derivee (KPI, agregat) **declare** ses dependances : les
types d'evenements qui l'alimentent. A l'arrivee d'un evenement,
``on_event`` invalide et recompute **uniquement** les derivations
dependantes de ce type - jamais tout, jamais de recalcul global
(Constitution, loi 12 ; Conception 9.1/9.2).

Le registre est un module-niveau : les derivations s'enregistrent a
l'import (``kpi_catalog.register_derivations()``), et le moteur reste
totalement agnostique de ce qu'elles calculent.
"""

_REGISTRY = {}


class Derivation:
    """Une derivation declaree : nom, types d'evenements sources, et
    fonction de calcul ``compute(conn) -> dict``."""

    def __init__(self, name, event_types, compute):
        self.name = name
        self.event_types = frozenset(event_types)
        self.compute = compute


def register(name, event_types, compute):
    """Declare une derivation dans le DAG (idempotent : re-enregistrer le
    meme nom remplace la declaration - utile pour les tests)."""
    _REGISTRY[name] = Derivation(name, event_types, compute)


def registered():
    """Noms des derivations declarees (ordre stable)."""
    return sorted(_REGISTRY)


def dependents_of(event_type):
    """Noms des derivations qui dependent de ce type d'evenement."""
    return sorted(name for name, d in _REGISTRY.items() if event_type in d.event_types)


def on_event(conn, event):
    """Reaction a un evenement : recompute **uniquement** les derivations
    dont les types sources incluent ``event['type']``.

    Returns:
        dict: ``{nom: resultat_du_compute}`` - vide si aucune derivation
        ne depend de ce type (l'evenement ne declenche alors aucun
        calcul, c'est le comportement attendu, pas une erreur).
    """
    recomputed = {}
    for name in dependents_of(event["type"]):
        recomputed[name] = _REGISTRY[name].compute(conn)
    return recomputed


def recompute_all(conn):
    """Recalcul explicite de tout le registre - reserve a l'amorcage ou a
    une reconstruction demandee ; jamais utilise par le flux reactif."""
    return {name: _REGISTRY[name].compute(conn) for name in registered()}
