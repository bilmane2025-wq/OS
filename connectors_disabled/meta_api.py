"""Connecteur Meta (publicites/statistiques) - DESACTIVE (T-CONN-1).

Contrat d'ingestion futur : ``fetch(conn)`` produirait des evenements
``PERCEPTION.FactObserved`` via la passerelle M04. Tant que le module
n'est pas active, il leve « connecteur non activé » et demande le depot
d'un export CSV dans ``data/inbox/``.
"""
from connectors_disabled import make_disabled_connector

CONNECTOR_NAME = "Meta"
EVENT_TYPE = "PERCEPTION.FactObserved"
FILE_HINT = "l'export CSV des statistiques Meta"

is_enabled, fetch = make_disabled_connector(CONNECTOR_NAME, FILE_HINT)
