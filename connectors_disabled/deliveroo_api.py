"""Connecteur Deliveroo - DESACTIVE (T-CONN-1).

Contrat d'ingestion futur : ``fetch(conn)`` produirait des evenements
``PERCEPTION.OrderObserved`` via la passerelle M04. Tant que le module
n'est pas active, il leve « connecteur non activé » et demande le depot
de l'export commandes (CSV) dans ``data/inbox/``.
"""
from connectors_disabled import make_disabled_connector

CONNECTOR_NAME = "Deliveroo"
EVENT_TYPE = "PERCEPTION.OrderObserved"
FILE_HINT = "l'export CSV des commandes (profil source-profile/plateforme-commandes)"

is_enabled, fetch = make_disabled_connector(CONNECTOR_NAME, FILE_HINT)
