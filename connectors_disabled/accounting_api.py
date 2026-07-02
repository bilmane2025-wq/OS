"""Connecteur logiciel comptable - DESACTIVE (T-CONN-1).

Contrat d'ingestion futur : ``fetch(conn)`` produirait des evenements
``PERCEPTION.FactObserved`` (balance) via la passerelle M04. Tant que le
module n'est pas active, il leve « connecteur non activé » et demande le
depot de la balance XLSX dans ``data/inbox/``.
"""
from connectors_disabled import make_disabled_connector

CONNECTOR_NAME = "comptable"
EVENT_TYPE = "PERCEPTION.FactObserved"
FILE_HINT = "la balance comptable XLSX (profil source-profile/balance-comptable)"

is_enabled, fetch = make_disabled_connector(CONNECTOR_NAME, FILE_HINT)
