"""Connecteur banque (bank-feed) - DESACTIVE (T-CONN-1).

Contrat d'ingestion futur : ``fetch(conn)`` produirait des evenements
``PERCEPTION.StatementLine`` via la passerelle M04. Tant que le module
n'est pas active, il leve « connecteur non activé » et demande le depot
du releve bancaire (CSV) dans ``data/inbox/``.
"""
from connectors_disabled import make_disabled_connector

CONNECTOR_NAME = "banque (bank-feed)"
EVENT_TYPE = "PERCEPTION.StatementLine"
FILE_HINT = "l'export CSV du relevé bancaire (profil source-profile/banque-releve)"

is_enabled, fetch = make_disabled_connector(CONNECTOR_NAME, FILE_HINT)
