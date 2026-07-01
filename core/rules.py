"""Corpus de regles (patrimoine 2) - versionnees, bi-temporelles
(T-M02-1, T-M02-2).

Le corpus de regles est le second patrimoine (Constitution, section II ;
Conception, module M02) : chaque regle (categorisation, definition de KPI,
seuil, taux...) est un Objet **verse**, jamais ecrase. Corriger une regle,
c'est ajouter une nouvelle version datee (``valid_from``) ; toutes les
versions anterieures restent interrogeables pour toujours, condition du
rejeu fidele (Chronos - une regle d'aujourd'hui ne doit jamais s'appliquer
retroactivement a un fait d'hier).

``add_version`` insere une nouvelle version (numero de version calcule
automatiquement, jamais reutilise pour un ``name`` donne : la cle primaire
``(name, version)`` de la table ``rules`` empeche structurellement tout
ecrasement). ``get`` renvoie la version applicable a une date du monde
donnee (``valid_from``), pas necessairement la plus recente.
"""
import json
import os
from datetime import datetime, timezone

DEFAULT_SEED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "seed_rules.json"
)

_RULE_COLUMNS = (
    "rule_id", "name", "version", "valid_from", "valid_to", "ts_record",
    "body_json", "origin", "confidence", "active", "note",
)


class RuleError(ValueError):
    """Leve quand une regle est mal formee (date non ISO-8601 avec fuseau)."""


def _rule_id(name):
    # Meme famille de regle (ex. "categorization/foodex") -> meme rule_id a
    # travers toutes ses versions. L'identite immortelle complete (M03) sera
    # branchee plus tard sans changer ce contrat.
    return f"RULE:{name}"


def _require_timezone_aware_timestamp(value, field_name):
    if not isinstance(value, str) or value.strip() == "":
        raise RuleError(f"{field_name} doit etre une chaine ISO-8601 non vide (recu: {value!r})")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise RuleError(f"{field_name} n'est pas une date/heure ISO-8601 valide (recu: {value!r})")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuleError(
            f"{field_name} doit indiquer un fuseau horaire explicite (Z ou +HH:MM), "
            f"pas une date/heure naive (recu: {value!r})"
        )
    return value


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _next_version(conn, name):
    row = conn.execute("SELECT MAX(version) FROM rules WHERE name = ?", (name,)).fetchone()
    current_max = row[0]
    return 1 if current_max is None else current_max + 1


def _row_to_dict(row):
    result = dict(zip(_RULE_COLUMNS, row))
    result["body"] = json.loads(result.pop("body_json"))
    result["active"] = bool(result["active"])
    return result


def add_version(
    conn,
    name,
    body,
    valid_from,
    valid_to=None,
    ts_record=None,
    origin="manual",
    confidence=None,
    active=True,
    note=None,
):
    """Ajoute une nouvelle version d'une regle, sans jamais ecraser les
    versions existantes.

    Args:
        conn: connexion SQLite ouverte sur ``data/eos.db`` (table ``rules``
            creee par ``app.init_db``).
        name: nom de la regle (ex. ``"categorization/foodex"``). Toutes les
            versions d'un meme ``name`` partagent le meme ``rule_id``.
        body: contenu de la regle (dict JSON-serialisable) - formule,
            mapping, seuil...
        valid_from: date/heure ISO-8601 avec fuseau horaire explicite a
            partir de laquelle cette version est effective (temps du
            monde).
        valid_to: date/heure de fin de validite (exclue), ou ``None`` si
            la version reste ouverte (cas usuel : elle sera implicitement
            close par la version suivante lors de la lecture).
        ts_record: date/heure a laquelle le systeme enregistre cette
            version (temps du systeme). Par defaut, l'instant present -
            distinct de ``valid_from`` (une regle peut etre saisie
            aujourd'hui pour une entree en vigueur passee ou future).
        origin: provenance de la regle, ``"seed" | "manual" | "learned"``.
        confidence: score de confiance optionnel (float).
        active: si ``False``, cette version n'est jamais renvoyee par
            ``get`` meme si elle est temporellement applicable.
        note: commentaire libre optionnel.

    Returns:
        dict: la version inseree (memes champs que ``get``).
    """
    _require_timezone_aware_timestamp(valid_from, "valid_from")
    if valid_to is not None:
        _require_timezone_aware_timestamp(valid_to, "valid_to")
    if ts_record is None:
        ts_record = _now_iso()
    else:
        _require_timezone_aware_timestamp(ts_record, "ts_record")

    version = _next_version(conn, name)
    record = {
        "rule_id": _rule_id(name),
        "name": name,
        "version": version,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "ts_record": ts_record,
        "body_json": json.dumps(body, sort_keys=True, ensure_ascii=False, default=str),
        "origin": origin,
        "confidence": confidence,
        "active": 1 if active else 0,
        "note": note,
    }

    conn.execute(
        """
        INSERT INTO rules (
            rule_id, name, version, valid_from, valid_to, ts_record,
            body_json, origin, confidence, active, note
        ) VALUES (
            :rule_id, :name, :version, :valid_from, :valid_to, :ts_record,
            :body_json, :origin, :confidence, :active, :note
        )
        """,
        record,
    )
    conn.commit()

    return _row_to_dict(tuple(record[col] for col in _RULE_COLUMNS))


def get(conn, name, at_date):
    """Renvoie la version de ``name`` applicable a ``at_date`` (temps du
    monde), jamais simplement la derniere version creee.

    Parmi les versions actives dont ``valid_from <= at_date`` (et
    ``valid_to`` non atteint le cas echeant), renvoie celle dont
    ``valid_from`` est la plus recente - c'est la version qui etait en
    vigueur a cette date, condition du rejeu fidele.

    Args:
        conn: connexion SQLite ouverte.
        name: nom de la regle.
        at_date: date/heure ISO-8601 avec fuseau horaire explicite.

    Returns:
        dict ou ``None`` si aucune version n'est applicable a cette date.
    """
    _require_timezone_aware_timestamp(at_date, "at_date")

    columns = ", ".join(_RULE_COLUMNS)
    row = conn.execute(
        f"""
        SELECT {columns}
        FROM rules
        WHERE name = ?
          AND active = 1
          AND valid_from <= ?
          AND (valid_to IS NULL OR ? < valid_to)
        ORDER BY valid_from DESC, version DESC
        LIMIT 1
        """,
        (name, at_date, at_date),
    ).fetchone()

    if row is None:
        return None
    return _row_to_dict(row)


def load_seed_rules(conn, path=DEFAULT_SEED_PATH):
    """Charge le jeu initial de regles (categorisation, KPI, seuils, taux
    de change) comme version 1 de chacune (Backlog, T-M02-2).

    Idempotent : une regle qui possede deja au moins une version (seed ou
    non) n'est jamais reseedee - un redemarrage ne cree pas de version 2 a
    chaque fois, et une regle deja corrigee manuellement n'est jamais
    ecrasee.

    Args:
        conn: connexion SQLite ouverte.
        path: chemin du fichier JSON de regles seed (par defaut
            ``data/seed_rules.json``).

    Returns:
        list[dict]: les versions effectivement inserees lors de cet appel
        (liste vide si tout etait deja seede).
    """
    with open(path, "r", encoding="utf-8") as seed_file:
        entries = json.load(seed_file)

    inserted = []
    for entry in entries:
        name = entry["name"]
        if _next_version(conn, name) != 1:
            continue  # deja une version existante : on ne touche jamais a l'existant
        result = add_version(
            conn,
            name=name,
            body=entry["body"],
            valid_from=entry["valid_from"],
            origin=entry.get("origin", "seed"),
            confidence=entry.get("confidence"),
            note=entry.get("note"),
        )
        inserted.append(result)
    return inserted
