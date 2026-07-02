"""Algebre de confiance (T-M13-1).

Regles de propagation **figees** (Conception 9.3) :

- une somme (ou toute combinaison) herite de la **confiance minimale** de
  ses termes : la nature la plus faible et le score le plus bas ;
- une valeur issue d'une estimation **reste** une estimation - elle ne
  redevient jamais un fait par agregation ;
- toute sortie porte nature + score : **aucune valeur nue** (Constitution,
  lois 5-6).

L'ordre de force des natures est celui de la Constitution (loi 5) :
fait > mesure > estime > hypothese > projection.
"""

# Du plus fort au plus faible. Combiner = retenir le plus faible present.
NATURE_ORDER = ("fait", "mesuré", "estimé", "hypothèse", "projection")

_RANK = {nature: index for index, nature in enumerate(NATURE_ORDER)}


class ConfidenceError(ValueError):
    """Levee pour une nature hors des 5 valeurs de la Constitution."""


def _rank(nature):
    if nature not in _RANK:
        raise ConfidenceError(
            f"nature inconnue : {nature!r} (attendu l'une de {NATURE_ORDER})")
    return _RANK[nature]


def weakest_nature(natures):
    """Nature la plus faible d'une collection (celle qui contamine le
    resultat) : un seul terme estime rend la somme estimee."""
    natures = list(natures)
    if not natures:
        # Aucune donnee : le resultat n'est qu'une hypothese, score nul -
        # jamais un "fait 0" silencieux.
        return "hypothèse"
    return max(natures, key=_rank)


def combine_scores(scores):
    """Score combine = minimum des scores (la chaine vaut son maillon le
    plus faible). Collection vide -> 0.0 (aucune preuve)."""
    scores = list(scores)
    if not scores:
        return 0.0
    return min(scores)


def combine(items):
    """Combine une collection de confiances.

    Args:
        items: iterable de ``(nature, score)`` - typiquement la facette
            confiance des evenements sources d'un calcul.

    Returns:
        dict: ``{"nature": ..., "score": ...}`` - la nature la plus
        faible, le score le plus bas. Collection vide ->
        ``{"nature": "hypothèse", "score": 0.0}`` (l'absence de donnee
        n'est jamais deguisee en certitude).
    """
    items = list(items)
    for nature, _ in items:
        _rank(nature)  # validation stricte de chaque terme
    return {
        "nature": weakest_nature(nature for nature, _ in items),
        "score": combine_scores(score for _, score in items),
    }
