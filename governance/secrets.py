"""Coffre a secrets - isole, chiffre au repos, inerte au MVP (T-M30-1).

Prepare l'isolement des futurs identifiants de connecteurs (banque,
email, plateformes - Conception, section 7.3) : ``data/secrets/`` est un
coffre chiffre local, totalement independant de ``data/eos.db``. Un
secret n'est **jamais** ecrit dans le journal, les regles, ou une
quelconque projection - ce module ne touche jamais une connexion SQLite,
par construction (aucune fonction ci-dessous ne prend de ``conn`` en
parametre).

**Vide au MVP** : aucune API n'est encore activee (les connecteurs
arrivent, inertes, en Sprint 8 - T-CONN-1), donc rien n'est stocke ici en
usage normal du MVP. L'interface (``get``/``set``) existe pour que
l'activation future d'un connecteur n'ait qu'a lire un secret deja
present, sans jamais toucher au reste du systeme.

Chiffrement : Fernet (AES-128-CBC authentifie, bibliotheque
``cryptography``) avec une cle maitresse generee localement au premier
usage et stockee dans ``data/secrets/master.key`` (permissions 0600,
jamais versionnee - voir ``.gitignore``). C'est la seule dependance
externe du projet ; elle est deliberee : le chiffrement au repos est une
exigence de securite explicite (Constitution, principes Securite),
et il n'existe pas d'implementation de chiffrement authentifie dans la
bibliotheque standard Python.
"""
import json
import os

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_SECRETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "secrets"
)

_KEY_FILENAME = "master.key"
_VAULT_FILENAME = "vault.enc"


class SecretsError(RuntimeError):
    """Levee quand le coffre est corrompu ou illisible."""


def _validate_name(name):
    if not isinstance(name, str) or name.strip() == "":
        raise ValueError(f"name doit etre une chaine non vide (recu: {name!r})")


def _key_path(secrets_dir):
    return os.path.join(secrets_dir, _KEY_FILENAME)


def _vault_path(secrets_dir):
    return os.path.join(secrets_dir, _VAULT_FILENAME)


def _load_or_create_key(secrets_dir):
    os.makedirs(secrets_dir, exist_ok=True)
    key_path = _key_path(secrets_dir)
    if os.path.exists(key_path):
        with open(key_path, "rb") as handle:
            return handle.read()

    key = Fernet.generate_key()
    with open(key_path, "wb") as handle:
        handle.write(key)
    os.chmod(key_path, 0o600)
    return key


def _load_vault(secrets_dir):
    vault_path = _vault_path(secrets_dir)
    if not os.path.exists(vault_path):
        return {}

    with open(vault_path, "rb") as handle:
        token = handle.read()
    if not token:
        return {}

    key = _load_or_create_key(secrets_dir)
    try:
        decrypted = Fernet(key).decrypt(token)
    except (InvalidToken, ValueError) as exc:
        raise SecretsError("coffre a secrets illisible : cle invalide ou fichier corrompu") from exc

    return json.loads(decrypted.decode("utf-8"))


def _save_vault(secrets_dir, vault):
    key = _load_or_create_key(secrets_dir)
    payload = json.dumps(vault, sort_keys=True, ensure_ascii=False).encode("utf-8")
    token = Fernet(key).encrypt(payload)

    vault_path = _vault_path(secrets_dir)
    with open(vault_path, "wb") as handle:
        handle.write(token)
    os.chmod(vault_path, 0o600)


def set(name, value, secrets_dir=DEFAULT_SECRETS_DIR):
    """Stocke ``value`` sous ``name`` dans le coffre chiffre.

    Args:
        name: identifiant du secret (ex. ``"banque/api-key"``).
        value: valeur du secret (chaine).
        secrets_dir: dossier du coffre (par defaut ``data/secrets/``).
    """
    _validate_name(name)
    if not isinstance(value, str):
        raise ValueError(f"value doit etre une chaine (recu: {type(value).__name__})")

    vault = _load_vault(secrets_dir)
    vault[name] = value
    _save_vault(secrets_dir, vault)


def get(name, secrets_dir=DEFAULT_SECRETS_DIR):
    """Relit la valeur de ``name`` depuis le coffre chiffre.

    Returns:
        str: la valeur stockee, ou ``None`` si ``name`` n'existe pas.
    """
    _validate_name(name)
    vault = _load_vault(secrets_dir)
    return vault.get(name)
