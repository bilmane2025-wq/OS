"""Connecteurs API desactives (T-CONN-1).

Chaque source API future a son module ici, expose le **meme contrat
d'ingestion** que la passerelle M04, et **leve ConnectorDisabledError**
au lieu de produire la moindre donnee. Aucune API simulee, aucun faux
connecteur (Backlog, contrainte n.5-6) : en attendant l'activation, la
source s'utilise par depot de fichier dans ``data/inbox/`` - c'est le
mode officiel, pas un pis-aller.

Activation future = implementer ``fetch`` dans le module concerne et le
brancher sur la meme passerelle M04 (``intake_folder``), sans toucher au
reste du systeme.
"""


class ConnectorDisabledError(RuntimeError):
    """Levee par tout connecteur non active : aucune donnee n'est jamais
    produite, un depot de fichier est demande a la place."""

    def __init__(self, connector_name, file_hint):
        self.connector_name = connector_name
        self.file_hint = file_hint
        super().__init__(
            f"connecteur non activé : {connector_name}. Aucune donnée ne peut "
            f"être récupérée automatiquement. Déposez à la place {file_hint} "
            f"dans data/inbox/ (mode officiel)."
        )


def make_disabled_connector(name, file_hint):
    """Fabrique le contrat d'ingestion inerte d'un connecteur.

    Returns:
        tuple ``(is_enabled, fetch)`` :
        - ``is_enabled()`` -> toujours ``False`` tant que le module n'est
          pas active ;
        - ``fetch(*args, **kwargs)`` -> leve ``ConnectorDisabledError``
          **avant toute action** : ne lit rien, n'ecrit rien, ne simule
          rien.
    """
    def is_enabled():
        return False

    def fetch(*_args, **_kwargs):
        raise ConnectorDisabledError(name, file_hint)

    return is_enabled, fetch
