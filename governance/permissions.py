"""Permissions & autorite - echelle N0-N5 (T-M28-1).

Modele unifie de permission (Conception, section 7.1 ; Constitution, loi
16) : chaque transition d'etat est controlee par une echelle N0-N5.

- **N0** (observateur) : niveau par defaut de tout acteur inconnu
  (Conception 4.3 : "tout nouvel agent nait N0").
- **N1-N4** : autorite croissante, actionnable automatiquement des lors
  que l'acteur en dispose.
- **N5** : humain exclusivement. Toute transition **irreversible ou
  materielle** l'exige, quel que soit le niveau demande par ailleurs -
  ce plancher est une frontiere architecturale, jamais une convention
  contournable par l'appelant (Constitution, loi 16 ; risque R11).

Les droits eux-memes (qui a quelle autorite sur quel type d'objet) sont
stockes dans la table ``permissions`` (creee par ``app.init_db``,
T-M00-1) - ce module ne fait qu'y lire/ecrire et y appliquer la regle.
"""

AUTHORITY_MIN = 0
AUTHORITY_MAX = 5
HUMAN_AUTHORITY = 5


class AuthorityError(PermissionError):
    """Levee quand une transition est refusee par l'echelle d'autorite."""


def _validate_authority_level(value, field_name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} doit etre un entier (recu: {value!r})")
    if not (AUTHORITY_MIN <= value <= AUTHORITY_MAX):
        raise ValueError(
            f"{field_name} doit etre compris entre {AUTHORITY_MIN} et {AUTHORITY_MAX} (recu: {value})"
        )
    return value


def _validate_non_empty_str(value, field_name):
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{field_name} doit etre une chaine non vide (recu: {value!r})")
    return value


def grant(conn, subject, object_type, max_authority):
    """Attribue (ou met a jour) l'autorite maximale de ``subject`` pour
    ``object_type``.

    Idempotent par construction (upsert) : un nouvel appel remplace la
    valeur precedente pour ce couple (subject, object_type).

    Args:
        conn: connexion SQLite ouverte.
        subject: identifiant de l'acteur (humain ou agent), ex.
            ``"human:pierre"``, ``"agent:doctrine"``.
        object_type: type d'objet/domaine concerne par cette autorite,
            ex. ``"Facture"``, ``"Paiement"``.
        max_authority: niveau d'autorite accorde, entier N0-N5.
    """
    _validate_non_empty_str(subject, "subject")
    _validate_non_empty_str(object_type, "object_type")
    _validate_authority_level(max_authority, "max_authority")

    conn.execute(
        """
        INSERT INTO permissions (subject, object_type, max_authority)
        VALUES (?, ?, ?)
        ON CONFLICT(subject, object_type) DO UPDATE SET max_authority = excluded.max_authority
        """,
        (subject, object_type, max_authority),
    )
    conn.commit()


def authority_of(conn, subject, object_type):
    """Autorite maximale de ``subject`` pour ``object_type``.

    Renvoie ``0`` (N0, observateur) si ``subject`` n'a jamais recu
    d'autorite explicite pour ce type d'objet - jamais une erreur, jamais
    un acces implicitement large.
    """
    _validate_non_empty_str(subject, "subject")
    _validate_non_empty_str(object_type, "object_type")

    row = conn.execute(
        "SELECT max_authority FROM permissions WHERE subject = ? AND object_type = ?",
        (subject, object_type),
    ).fetchone()
    return row[0] if row is not None else AUTHORITY_MIN


def check(conn, actor, transition):
    """Controle si ``actor`` peut franchir ``transition``.

    Args:
        conn: connexion SQLite ouverte.
        actor: identifiant de l'acteur qui demande la transition.
        transition: dict decrivant la transition demandee :
            - ``object_type`` (str, requis) : cle de recherche dans la
              table ``permissions``.
            - ``action`` (str, optionnel) : libelle de la transition,
              pour la tracabilite d'un refus. Par defaut, ``object_type``.
            - ``required_authority`` (int N0-N5, defaut 0) : niveau
              demande pour une transition ordinaire.
            - ``irreversible`` (bool, defaut False).
            - ``material`` (bool, defaut False).

    Regle figee (Conception 7.1) : toute transition ``irreversible`` ou
    ``material`` exige N5 (humain), quel que soit ``required_authority``
    fourni - ce plancher n'est jamais contournable par l'appelant. Sinon,
    la transition est autorisee si l'autorite de ``actor`` pour
    ``object_type`` est superieure ou egale a ``required_authority``.

    Returns:
        ``True`` si la transition est autorisee.

    Raises:
        AuthorityError: si la transition est refusee (autorite
            insuffisante, ou N5 humain requis et non atteint).
    """
    object_type = _validate_non_empty_str(transition.get("object_type"), "transition['object_type']")
    required_authority = _validate_authority_level(
        transition.get("required_authority", AUTHORITY_MIN), "transition['required_authority']"
    )
    irreversible = bool(transition.get("irreversible", False))
    material = bool(transition.get("material", False))
    action = transition.get("action") or object_type

    human_floor_applies = irreversible or material
    effective_required = HUMAN_AUTHORITY if human_floor_applies else required_authority

    actor_authority = authority_of(conn, actor, object_type)

    if actor_authority < effective_required:
        if human_floor_applies:
            reason = "transition irreversible ou materielle : autorite humaine N5 requise"
        else:
            reason = f"autorite insuffisante (N{actor_authority} < N{effective_required} requis)"
        raise AuthorityError(
            f"transition '{action}' refusee pour '{actor}' sur '{object_type}' : {reason}"
        )

    return True
