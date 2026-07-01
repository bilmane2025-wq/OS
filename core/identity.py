"""Registre d'identite des Objets - id immortels, jamais reutilises
(T-M03-1).

Un identifiant est la seule chose qui ne change jamais pour un Objet, un
Lien ou un Evenement au long de sa vie (Conception, section 3.1 : id
immortel ``TYPE:ENTITE:sequence-monotone`` ; frontiere M03 : "reutiliser
un id" est interdit). ``new_id`` attribue, pour chaque paire (type,
entite), une sequence strictement croissante, jamais reutilisee meme
apres redemarrage du systeme - le compteur est persiste dans
``data/eos.db``, jamais garde seulement en memoire.
"""
import re

ID_PATTERN = re.compile(r"^[^:]+:[^:]+:\d+$")


class IdentityError(ValueError):
    """Leve pour un type ou une entite invalide (vide, ou contenant ':')."""


def ensure_schema(conn):
    """Cree (si absente) la table qui porte les sequences d'identite.

    Idempotent : peut etre appele a chaque connexion sans effet
    destructeur.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS identity_sequences (
            type TEXT NOT NULL,
            entity TEXT NOT NULL,
            last_sequence INTEGER NOT NULL,
            PRIMARY KEY (type, entity)
        )
        """
    )
    conn.commit()
    return conn


def _validate_component(value, field_name):
    if not isinstance(value, str) or value.strip() == "":
        raise IdentityError(f"{field_name} doit etre une chaine non vide (recu: {value!r})")
    if ":" in value:
        raise IdentityError(f"{field_name} ne peut pas contenir ':' (recu: {value!r})")


def new_id(conn, type_, entity):
    """Attribue un identifiant immortel ``TYPE:ENTITE:sequence`` pour
    cette paire (type, entite).

    La sequence est monotone et jamais reutilisee : deux appels, meme
    concurrents sur la meme connexion ou apres un redemarrage complet du
    systeme, ne colissionnent jamais - le compteur est stocke en base
    (table ``identity_sequences``), pas en memoire du processus.

    Args:
        conn: connexion SQLite ouverte sur ``data/eos.db``.
        type_: type de l'Objet/Lien/Evenement (ex. ``"OBJ"``, ``"EVT"``).
            Ne peut pas contenir ``':'``.
        entity: entite proprietaire (ex. ``"KAMEHA"``). Ne peut pas
            contenir ``':'``.

    Returns:
        str: l'identifiant, format ``TYPE:ENTITE:NNNNNN`` (sequence sur
        6 chiffres au minimum, jamais tronquee au-dela).
    """
    _validate_component(type_, "type_")
    _validate_component(entity, "entity")

    ensure_schema(conn)
    row = conn.execute(
        """
        INSERT INTO identity_sequences (type, entity, last_sequence)
        VALUES (?, ?, 1)
        ON CONFLICT(type, entity) DO UPDATE SET last_sequence = last_sequence + 1
        RETURNING last_sequence
        """,
        (type_, entity),
    ).fetchone()
    conn.commit()

    sequence = row[0]
    return f"{type_}:{entity}:{sequence:06d}"


def is_valid_id(value):
    """True si ``value`` respecte le format ``TYPE:ENTITE:sequence``."""
    return isinstance(value, str) and bool(ID_PATTERN.match(value))
