"""Journal d'evenements (patrimoine 1) - append-only (T-M01-1).

Le journal est la seule source de verite primaire du systeme (Constitution,
loi 1). Cette implementation garantit, au niveau de la base elle-meme (pas
seulement au niveau de l'API Python), les deux proprietes non-negociables :

- **Immuabilite** : deux triggers SQLite refusent toute tentative d'UPDATE
  ou de DELETE sur la table ``events`` (loi 2 : "rien n'est jamais
  supprime"). Meme un appel SQL direct, hors de ce module, echoue.
- **Idempotence** : ``append`` calcule une empreinte (hash) du contenu de
  l'evenement ; si cette empreinte existe deja, l'evenement n'est pas
  reinsere - l'appel est un no-op qui renvoie "duplicate".

La table ``events`` elle-meme est creee par ``app.init_db`` (T-M00-1) ;
``ensure_schema`` n'ajoute ici que la garde d'immutabilite propre au
journal.
"""
import hashlib
import json
import sqlite3

from core.envelope import validate_envelope

APPENDED = "appended"
DUPLICATE = "duplicate"

_IMMUTABILITY_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS trg_events_no_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events est append-only : UPDATE interdit');
END;

CREATE TRIGGER IF NOT EXISTS trg_events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events est append-only : DELETE interdit');
END;
"""


def ensure_schema(conn):
    """Installe (si absentes) les gardes d'immutabilite sur ``events``.

    Idempotent : peut etre appele a chaque connexion sans effet destructeur.
    """
    conn.executescript(_IMMUTABILITY_TRIGGERS)
    conn.commit()
    return conn


def connect(db_path):
    """Ouvre une connexion SQLite prete a l'emploi pour le journal.

    La table ``events`` doit deja exister (voir ``app.init_db``) ; cette
    fonction y ajoute les triggers d'immutabilite.
    """
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    return conn


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _compute_hash(envelope, payload, causation_id, correlation_id, rule_version_ref):
    """Empreinte de contenu, independante de l'identifiant attribue.

    Exclure ``envelope['id']`` du calcul est deliberer : si un evenement est
    soumis une seconde fois avec un identifiant different (par ex. apres une
    nouvelle tentative suite a une coupure), il doit tout de meme etre
    reconnu comme un doublon de contenu et ignore (idempotence, critere
    T-M01-1).
    """
    envelope_without_id = {key: value for key, value in envelope.items() if key != "id"}
    canonical = {
        "envelope": envelope_without_id,
        "payload": payload,
        "causation_id": causation_id,
        "correlation_id": correlation_id,
        "rule_version_ref": rule_version_ref,
    }
    return hashlib.sha256(_canonical_json(canonical).encode("utf-8")).hexdigest()


def append(conn, envelope, payload, causation_id=None, correlation_id=None, rule_version_ref=None):
    """Ajoute un evenement immuable au journal.

    Args:
        conn: connexion SQLite ouverte (voir ``connect``).
        envelope: enveloppe universelle complete de l'evenement (voir
            ``core.envelope.make_envelope``). Rejetee si incomplete ou
            invalide (``EnvelopeError``) - aucun evenement sans provenance
            ni confiance n'entre jamais dans le journal.
        payload: contenu metier de l'evenement, JSON-serialisable.
        causation_id: identifiant de l'evenement qui a cause celui-ci. Par
            defaut, repris de ``envelope['provenance']['event_id']``.
        correlation_id: identifiant du fil metier auquel appartient cet
            evenement (optionnel).
        rule_version_ref: version de regle appliquee lors de la production
            de cet evenement (optionnel).

    Returns:
        tuple[str, str]: (``"appended"`` ou ``"duplicate"``, event_id). En
        cas de doublon, l'``event_id`` retourne est celui deja present dans
        le journal (pas celui de l'enveloppe soumise).
    """
    validate_envelope(envelope)

    if causation_id is None:
        causation_id = envelope["provenance"]["event_id"]

    content_hash = _compute_hash(envelope, payload, causation_id, correlation_id, rule_version_ref)

    existing = conn.execute(
        "SELECT event_id FROM events WHERE hash = ?", (content_hash,)
    ).fetchone()
    if existing is not None:
        return DUPLICATE, existing[0]

    record = {
        "event_id": envelope["id"],
        "ts_record": envelope["temporal"]["ts_record"],
        "valid_from": envelope["temporal"]["valid_from"],
        "valid_to": envelope["temporal"]["valid_to"],
        "type": envelope["type"],
        "payload_json": _canonical_json({"envelope": envelope, "payload": payload}),
        "causation_id": causation_id,
        "correlation_id": correlation_id,
        "rule_version_ref": rule_version_ref,
        "source": envelope["provenance"]["source"],
        "author": envelope["provenance"]["author"],
        "hash": content_hash,
    }

    conn.execute(
        """
        INSERT INTO events (
            event_id, ts_record, valid_from, valid_to, type, payload_json,
            causation_id, correlation_id, rule_version_ref, source, author, hash
        ) VALUES (
            :event_id, :ts_record, :valid_from, :valid_to, :type, :payload_json,
            :causation_id, :correlation_id, :rule_version_ref, :source, :author, :hash
        )
        """,
        record,
    )
    conn.commit()
    return APPENDED, record["event_id"]
