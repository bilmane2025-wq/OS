"""Enveloppe universelle (T-M00-2).

Toute donnee du systeme (Objet, Lien, Evenement) porte la meme enveloppe a
six facettes (Conception Complete, section 3.1 ; Backlog, section 1) :

    {id, type, label,
     provenance:  {source, origin_ref, author, event_id},
     temporal:    {valid_from, valid_to, ts_record, version},
     confidence:  {nature, score, evidence[]},
     permissions: {owner, visibility, authority},
     lifecycle:   {state, history[]}}

``make_envelope`` construit et valide une enveloppe complete.
``validate_envelope`` verifie une enveloppe existante (par ex. relue depuis
la DB) et refuse tout ce qui est incomplet ou hors specification -
conformement a la loi 4 ("aucun chiffre n'existe sans provenance") et a la
loi 5 ("le systeme distingue toujours fait, mesure, estimation, hypothese,
projection").
"""
from datetime import datetime

# Les 5 natures de confiance (Constitution loi 5 ; Conception section 3.1).
# Une enveloppe dont la nature n'appartient pas a cet ensemble est rejetee.
NATURES = ("fait", "mesuré", "estimé", "hypothèse", "projection")

# Echelle d'autorite N0-N5 (Constitution, section VII Securite). N5 = humain.
AUTHORITY_MIN = 0
AUTHORITY_MAX = 5

_REQUIRED_TOP_LEVEL_KEYS = (
    "id", "type", "label",
    "provenance", "temporal", "confidence", "permissions", "lifecycle",
)
_REQUIRED_PROVENANCE_KEYS = ("source", "origin_ref", "author", "event_id")
_REQUIRED_TEMPORAL_KEYS = ("valid_from", "valid_to", "ts_record", "version")
_REQUIRED_CONFIDENCE_KEYS = ("nature", "score", "evidence")
_REQUIRED_PERMISSIONS_KEYS = ("owner", "visibility", "authority")
_REQUIRED_LIFECYCLE_KEYS = ("state", "history")


class EnvelopeError(ValueError):
    """Leve quand une enveloppe est absente, incomplete ou invalide.

    C'est le mecanisme de rejet structurel : aucune donnee sans enveloppe
    complete et valide ne peut entrer dans le systeme (Constitution, loi 4).
    """


def _fail(message):
    raise EnvelopeError(message)


def _require_non_empty_str(value, field_name):
    if not isinstance(value, str) or value.strip() == "":
        _fail(f"{field_name} doit etre une chaine non vide (recu: {value!r})")
    return value


def _require_dict(value, field_name):
    if not isinstance(value, dict):
        _fail(f"{field_name} doit etre un objet (dict) (recu: {type(value).__name__})")
    return value


def _require_keys(mapping, keys, field_name):
    missing = [key for key in keys if key not in mapping]
    if missing:
        _fail(f"{field_name} incomplet : cle(s) manquante(s) {missing}")


def _require_list(value, field_name):
    if not isinstance(value, list):
        _fail(f"{field_name} doit etre une liste (recu: {type(value).__name__})")
    return value


def _require_list_of_non_empty_str(value, field_name):
    _require_list(value, field_name)
    for index, item in enumerate(value):
        if not isinstance(item, str) or item.strip() == "":
            _fail(f"{field_name}[{index}] doit etre une chaine non vide (recu: {item!r})")
    return value


def _require_list_of_dicts(value, field_name):
    _require_list(value, field_name)
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            _fail(f"{field_name}[{index}] doit etre un objet (dict) (recu: {type(item).__name__})")
    return value


def _require_int_in_range(value, field_name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{field_name} doit etre un entier (recu: {value!r})")
    if not (minimum <= value <= maximum):
        _fail(f"{field_name} doit etre compris entre {minimum} et {maximum} (recu: {value})")
    return value


def _require_score(value, field_name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{field_name} doit etre un nombre (recu: {value!r})")
    if not (0.0 <= float(value) <= 1.0):
        _fail(f"{field_name} doit etre compris entre 0 et 1 (recu: {value})")
    return value


def _parse_timestamp(value, field_name):
    if not isinstance(value, str) or value.strip() == "":
        _fail(f"{field_name} doit etre une chaine ISO-8601 non vide (recu: {value!r})")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(f"{field_name} n'est pas une date/heure ISO-8601 valide (recu: {value!r})")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        # La bi-temporalite exige un instant non ambigu : un fuseau horaire
        # explicite (Z ou +HH:MM) est obligatoire, une heure locale nue est
        # refusee (revue externe PR #2, commentaire 1).
        _fail(
            f"{field_name} doit indiquer un fuseau horaire explicite (Z ou "
            f"+HH:MM), pas une date/heure naive (recu: {value!r})"
        )
    return parsed


def _validate_provenance(provenance):
    _require_dict(provenance, "provenance")
    _require_keys(provenance, _REQUIRED_PROVENANCE_KEYS, "provenance")
    _require_non_empty_str(provenance["source"], "provenance.source")
    _require_non_empty_str(provenance["author"], "provenance.author")
    # origin_ref et event_id sont optionnels (None autorise : un evenement
    # racine n'a pas d'evenement createur, une saisie manuelle n'a pas de
    # document d'origine) mais doivent etre presents et, si fournis, textuels.
    for optional_field in ("origin_ref", "event_id"):
        value = provenance[optional_field]
        if value is not None and not isinstance(value, str):
            _fail(f"provenance.{optional_field} doit etre une chaine ou None (recu: {value!r})")


def _validate_temporal(temporal):
    _require_dict(temporal, "temporal")
    _require_keys(temporal, _REQUIRED_TEMPORAL_KEYS, "temporal")

    valid_from = _parse_timestamp(temporal["valid_from"], "temporal.valid_from")
    _parse_timestamp(temporal["ts_record"], "temporal.ts_record")

    valid_to_raw = temporal["valid_to"]
    if valid_to_raw is not None:
        valid_to = _parse_timestamp(valid_to_raw, "temporal.valid_to")
        if valid_to <= valid_from:
            _fail(
                "temporal.valid_to doit etre strictement posterieur a "
                f"temporal.valid_from (recu valid_from={temporal['valid_from']!r}, "
                f"valid_to={valid_to_raw!r})"
            )

    _require_int_in_range(temporal["version"], "temporal.version", 1, float("inf"))


def _validate_confidence(confidence):
    _require_dict(confidence, "confidence")
    _require_keys(confidence, _REQUIRED_CONFIDENCE_KEYS, "confidence")

    nature = confidence["nature"]
    if nature not in NATURES:
        _fail(f"confidence.nature hors specification : {nature!r} (attendu l'une de {NATURES})")

    _require_score(confidence["score"], "confidence.score")
    _require_list_of_non_empty_str(confidence["evidence"], "confidence.evidence")


def _validate_permissions(permissions):
    _require_dict(permissions, "permissions")
    _require_keys(permissions, _REQUIRED_PERMISSIONS_KEYS, "permissions")
    _require_non_empty_str(permissions["owner"], "permissions.owner")
    _require_non_empty_str(permissions["visibility"], "permissions.visibility")
    _require_int_in_range(permissions["authority"], "permissions.authority", AUTHORITY_MIN, AUTHORITY_MAX)


def _validate_lifecycle(lifecycle):
    _require_dict(lifecycle, "lifecycle")
    _require_keys(lifecycle, _REQUIRED_LIFECYCLE_KEYS, "lifecycle")
    _require_non_empty_str(lifecycle["state"], "lifecycle.state")
    _require_list_of_dicts(lifecycle["history"], "lifecycle.history")


def validate_envelope(envelope):
    """Valide une enveloppe universelle complete.

    Retourne ``True`` si l'enveloppe est valide. Leve ``EnvelopeError`` au
    premier probleme rencontre sinon (facette manquante, champ manquant,
    type incorrect, nature de confiance hors liste, intervalle temporel
    incoherent...). Aucune enveloppe partielle n'est jamais acceptee.
    """
    _require_dict(envelope, "envelope")
    _require_keys(envelope, _REQUIRED_TOP_LEVEL_KEYS, "envelope")

    _require_non_empty_str(envelope["id"], "id")
    _require_non_empty_str(envelope["type"], "type")
    _require_non_empty_str(envelope["label"], "label")

    _validate_provenance(envelope["provenance"])
    _validate_temporal(envelope["temporal"])
    _validate_confidence(envelope["confidence"])
    _validate_permissions(envelope["permissions"])
    _validate_lifecycle(envelope["lifecycle"])

    return True


def make_envelope(
    *,
    id,
    type_,
    label,
    source,
    author,
    valid_from,
    ts_record,
    nature,
    score,
    owner,
    visibility,
    authority,
    origin_ref=None,
    event_id=None,
    valid_to=None,
    version=1,
    evidence=None,
    state="actif",
    history=None,
):
    """Construit une enveloppe universelle complete et la valide.

    Un seul point d'entree pour fabriquer l'enveloppe de tout Objet, Lien ou
    Evenement, garantissant que les six facettes (identite, provenance,
    temporalite, confiance, permissions, cycle de vie) sont toujours
    presentes et coherentes. Leve ``EnvelopeError`` si l'un des arguments
    produit une enveloppe invalide - il est impossible de construire une
    enveloppe incomplete via cette fonction.

    Args:
        id: identifiant immortel de l'Objet/Lien/Evenement (voir T-M03-1).
        type_: type de l'Objet/Lien/Evenement.
        label: libelle humain.
        source, author, origin_ref, event_id: facette provenance.
        valid_from, valid_to, ts_record, version: facette temporalite
            bi-temporelle (valid-time / decision-time).
        nature, score, evidence: facette confiance (nature parmi
            :data:`NATURES`, score dans [0, 1]).
        owner, visibility, authority: facette permissions (authority dans
            l'echelle N0-N5).
        state, history: facette cycle de vie.

    Returns:
        dict: l'enveloppe complete, serialisable en JSON.
    """
    envelope = {
        "id": id,
        "type": type_,
        "label": label,
        "provenance": {
            "source": source,
            "origin_ref": origin_ref,
            "author": author,
            "event_id": event_id,
        },
        "temporal": {
            "valid_from": valid_from,
            "valid_to": valid_to,
            "ts_record": ts_record,
            "version": version,
        },
        "confidence": {
            "nature": nature,
            "score": score,
            "evidence": list(evidence) if evidence is not None else [],
        },
        "permissions": {
            "owner": owner,
            "visibility": visibility,
            "authority": authority,
        },
        "lifecycle": {
            "state": state,
            "history": list(history) if history is not None else [],
        },
    }

    validate_envelope(envelope)
    return envelope
