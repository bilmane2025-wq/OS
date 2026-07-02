"""Budget d'attention (T-M27-1).

L'attention du dirigeant est une ressource finie : les sollicitations
sont **dedupliquees** puis **plafonnees** (Constitution : « jamais
optimiser pour l'engagement » ; risque R8 - fatigue d'alertes). Ce qui
depasse le plafond n'est jamais perdu : il est compte et reste
consultable dans les ecrans (anomalies/inbox) - simplement, il ne
sollicite pas.
"""
DEFAULT_CAP = 3

_SEVERITY_RANK = {"haute": 0, "moyenne": 1, "douce": 2, "basse": 2}


def budget(alerts, cap=DEFAULT_CAP):
    """Applique le budget d'attention a une liste d'alertes (groupees ou
    non).

    - **Deduplication** : deux sollicitations de meme type n'en font
      qu'une (la plus grave gagne, les references sont fusionnees).
    - **Plafond** : au plus ``cap`` sollicitations montrees, les plus
      graves d'abord ; le reste est compte, jamais montre.

    Returns:
        dict: ``{"shown": [...], "suppressed": n, "total": n}``.
    """
    if cap < 0:
        raise ValueError(f"cap doit etre >= 0 (recu: {cap})")

    deduped = {}
    for alert in alerts:
        existing = deduped.get(alert["type"])
        if existing is None:
            deduped[alert["type"]] = dict(alert)
            continue
        # Dedup : fusion des references, la gravite la plus haute gagne.
        existing["refs"] = list(dict.fromkeys(
            list(existing.get("refs", [])) + list(alert.get("refs", []))))
        if _SEVERITY_RANK.get(alert["severity"], 2) < _SEVERITY_RANK.get(existing["severity"], 2):
            existing["severity"] = alert["severity"]

    ordered = sorted(deduped.values(),
                     key=lambda a: (_SEVERITY_RANK.get(a["severity"], 2), a["type"]))
    shown = ordered[:cap]
    return {"shown": shown, "suppressed": len(ordered) - len(shown),
            "total": len(ordered)}
