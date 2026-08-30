"""Tests T-M17-1 : runtime des agents (brain.agent_runtime).

Criteres (Conception 4.1/4.3/4.7, Constitution lois 7/15/16) : un agent
percoit en lecture seule et n'emet que des propositions journalisees ;
aucune proposition sans preuve liee n'est acceptee ; tout agent nait
N0, sauf un gardien qui nait a son niveau declare une seule fois.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as eos_app  # noqa: E402
from brain import agent_runtime  # noqa: E402
from core import event_store  # noqa: E402
from governance import permissions  # noqa: E402
from graph import graph_engine  # noqa: E402
from tests.test_graph import make_event  # noqa: E402


class AgentRuntimeTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_tmp_test_agent_runtime.db")
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        eos_app.init_db(self.db_path)
        self.conn = event_store.connect(self.db_path)

        self._saved_registry = dict(agent_runtime._REGISTRY)
        agent_runtime._REGISTRY.clear()

    def tearDown(self):
        agent_runtime._REGISTRY.clear()
        agent_runtime._REGISTRY.update(self._saved_registry)
        self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _table_snapshot(self, *tables):
        return {t: self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


class DispatchTests(AgentRuntimeTestCase):
    def test_only_agents_watching_the_event_type_are_solicited(self):
        calls = []

        def invoice_perceive(context, event):
            calls.append(("invoice_watcher", event["type"]))
            return []

        def order_perceive(context, event):
            calls.append(("order_watcher", event["type"]))
            return []

        agent_runtime.register(agent_runtime.Agent(
            "invoice_watcher", "surveille les factures",
            ("PERCEPTION.InvoiceReceived",), invoice_perceive))
        agent_runtime.register(agent_runtime.Agent(
            "order_watcher", "surveille les commandes",
            ("PERCEPTION.OrderObserved",), order_perceive))

        event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                           {"fields": {"montant": "10,00", "fournisseur": "Foodex"}}, 1)
        agent_runtime.on_event(self.conn, event)

        self.assertEqual(calls, [("invoice_watcher", "PERCEPTION.InvoiceReceived")])

    def test_an_event_without_watchers_triggers_nothing(self):
        emitted = agent_runtime.on_event(self.conn, {"type": "RULE.RuleCreated"})
        self.assertEqual(emitted, [])


class ProposalValidationTests(AgentRuntimeTestCase):
    def _register(self, perceive):
        agent_runtime.register(agent_runtime.Agent(
            "sentinelle", "detecte les ecarts", ("PERCEPTION.InvoiceReceived",), perceive))

    def test_proposal_without_evidence_is_rejected(self):
        self._register(lambda ctx, evt: [
            {"subtype": "Observation", "label": "facture suspecte"}  # pas d'evidence
        ])
        event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                           {"fields": {"montant": "10,00"}}, 1)

        before = event_store.read(self.conn)
        with self.assertRaises(agent_runtime.AgentError):
            agent_runtime.on_event(self.conn, event)
        after = event_store.read(self.conn)

        self.assertEqual(len(before), len(after))  # rien n'a atteint le journal

    def test_proposal_with_unknown_subtype_is_rejected(self):
        self._register(lambda ctx, evt: [
            {"subtype": "Decision", "label": "x", "evidence": [evt["event_id"]]}
        ])
        event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                           {"fields": {"montant": "10,00"}}, 1)
        with self.assertRaises(agent_runtime.AgentError):
            agent_runtime.on_event(self.conn, event)

    def test_proposal_without_label_is_rejected(self):
        self._register(lambda ctx, evt: [
            {"subtype": "Alert", "evidence": [evt["event_id"]]}
        ])
        event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                           {"fields": {"montant": "10,00"}}, 1)
        with self.assertRaises(agent_runtime.AgentError):
            agent_runtime.on_event(self.conn, event)

    def test_valid_proposal_is_journaled_with_full_provenance(self):
        self._register(lambda ctx, evt: [
            {"subtype": "Recommendation", "label": "verifier le fournisseur",
             "evidence": [evt["event_id"]], "nature": "estimé", "score": 0.7,
             "body": {"conseil": "demander une confirmation"}}
        ])
        event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                           {"fields": {"montant": "10,00"}}, 1)

        emitted = agent_runtime.on_event(self.conn, event)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["type"], "AGENT.Recommendation")
        self.assertEqual(emitted[0]["status"], event_store.APPENDED)

        journaled = [e for e in event_store.read(self.conn) if e["type"] == "AGENT.Recommendation"][0]
        self.assertEqual(journaled["causation_id"], event["event_id"])
        self.assertEqual(journaled["correlation_id"], event["event_id"])
        self.assertEqual(journaled["envelope"]["confidence"]["nature"], "estimé")
        self.assertEqual(journaled["envelope"]["confidence"]["score"], 0.7)
        self.assertEqual(journaled["envelope"]["confidence"]["evidence"], [event["event_id"]])
        self.assertEqual(journaled["envelope"]["provenance"]["author"], "agent:sentinelle")
        self.assertEqual(journaled["payload"]["agent"], "sentinelle")
        self.assertEqual(journaled["payload"]["body"]["conseil"], "demander une confirmation")

    def test_multiple_proposals_from_one_event_are_each_journaled(self):
        self._register(lambda ctx, evt: [
            {"subtype": "Observation", "label": "obs 1", "evidence": [evt["event_id"]]},
            {"subtype": "Alert", "label": "obs 2", "evidence": [evt["event_id"]]},
        ])
        event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                           {"fields": {"montant": "10,00"}}, 1)

        emitted = agent_runtime.on_event(self.conn, event)
        self.assertEqual(sorted(e["type"] for e in emitted),
                         ["AGENT.Alert", "AGENT.Observation"])
        self.assertEqual(len({e["event_id"] for e in emitted}), 2)


class ReadOnlyContextTests(AgentRuntimeTestCase):
    def test_agent_can_read_the_graph_it_helped_trigger_but_never_mutates_it(self):
        """Un agent lit le graphe (evidence tiree d'un Objet reel) sans
        jamais l'ecrire - le graphe/les KPI/les regles sont inchanges
        apres son passage, seul le journal grandit (frontiere M17)."""
        event = make_event(self.conn, "PERCEPTION.InvoiceReceived",
                           {"fields": {"montant": "600,00", "fournisseur": "Foodex"}}, 1)
        touched = graph_engine.apply(self.conn, event)
        invoice_id = touched[0]

        def perceive(context, evt):
            invoice = context.object(invoice_id)
            neighbors = context.neighbors(invoice_id, "out")
            self.assertIsNotNone(invoice)
            self.assertTrue(neighbors)
            return [{"subtype": "Observation", "label": "facture elevee",
                     "evidence": [invoice_id] + [n["object"]["object_id"] for n in neighbors]}]

        agent_runtime.register(agent_runtime.Agent(
            "lecteur", "observe les factures", ("PERCEPTION.InvoiceReceived",), perceive))

        before = self._table_snapshot("objects", "links", "kpi", "rules")
        agent_runtime.on_event(self.conn, event)
        after = self._table_snapshot("objects", "links", "kpi", "rules")

        self.assertEqual(before, after)

        journaled = [e for e in event_store.read(self.conn) if e["type"] == "AGENT.Observation"][0]
        self.assertIn(invoice_id, journaled["envelope"]["confidence"]["evidence"])

    def test_context_exposes_no_write_method(self):
        context = agent_runtime.AgentContext(self.conn)
        for forbidden in ("execute", "upsert_object", "upsert_link", "commit", "append"):
            self.assertFalse(hasattr(context, forbidden))


class AuthorityBirthTests(AgentRuntimeTestCase):
    def test_ordinary_agent_is_born_at_n0(self):
        agent = agent_runtime.register(agent_runtime.Agent(
            "croissance", "explore les opportunites de croissance", (), lambda c, e: []))
        self.assertEqual(agent_runtime.authority_of(self.conn, agent), 0)

    def test_guardian_is_born_at_its_declared_authority(self):
        guardian = agent_runtime.register(agent_runtime.Agent(
            "doctrine", "garde la Constitution", (), lambda c, e: [],
            is_guardian=True, guardian_authority=3))

        self.assertEqual(agent_runtime.authority_of(self.conn, guardian), 0)  # avant amorcage
        bootstrapped = agent_runtime.bootstrap_authority(self.conn)

        self.assertEqual(bootstrapped, ["doctrine"])
        self.assertEqual(agent_runtime.authority_of(self.conn, guardian), 3)

    def test_bootstrap_never_overwrites_an_existing_authority(self):
        """Une calibration ulterieure (T-M20-1) qui aurait deja ajuste
        l'autorite d'un gardien n'est jamais ecrasee par un redemarrage."""
        guardian = agent_runtime.register(agent_runtime.Agent(
            "audit", "detecte les ecarts", (), lambda c, e: [],
            is_guardian=True, guardian_authority=3))
        permissions.grant(self.conn, guardian.subject,
                          agent_runtime.AGENT_AUTHORITY_DOMAIN, 1)  # deja ajuste

        bootstrapped = agent_runtime.bootstrap_authority(self.conn)

        self.assertEqual(bootstrapped, [])
        self.assertEqual(agent_runtime.authority_of(self.conn, guardian), 1)

    def test_bootstrap_is_idempotent_across_restarts(self):
        agent_runtime.register(agent_runtime.Agent(
            "fiscal", "veille aux obligations fiscales", (), lambda c, e: [],
            is_guardian=True, guardian_authority=2))

        first = agent_runtime.bootstrap_authority(self.conn)
        second = agent_runtime.bootstrap_authority(self.conn)

        self.assertEqual(first, ["fiscal"])
        self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
