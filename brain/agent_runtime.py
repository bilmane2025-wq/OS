"""Runtime des agents - perspectives qui proposent, sans jamais muter
l'etat (T-M17-1).

Un agent est une **perspective executee** (Conception 4.1) : il
s'abonne a des types d'evenements, lit le graphe/les KPI/le journal a
travers une facade strictement en lecture (``AgentContext`` - aucune
methode d'ecriture n'y est exposee), et **emet uniquement des
evenements de proposition** (``AGENT.Observation|Recommendation|
ActionProposed|Alert``, Conception 3.3, section E-AGENT) repris par le
journal comme tout le reste (Conception 2.2, "flux de proposition").

Deux garde-fous structurels, non contournables par un agent mal ecrit :

- **anti-hallucination** (Conception 4.7 ; Constitution loi 7) : toute
  proposition sans preuve liee (``evidence``, au moins un identifiant
  d'Objet/Evenement du graphe) est refusee avant meme d'atteindre le
  journal - jamais une exception rattrapee en aval, un rejet immediat.
- **autorite de naissance** (Conception 4.3) : tout agent nait **N0**
  (observateur) sur l'echelle N0-N5 de T-M28-1 - c'est deja le defaut
  de ``governance.permissions.authority_of`` pour tout sujet inconnu,
  rien a ecrire pour un agent ordinaire. Seuls les gardiens des lois
  (Doctrine, Audit, Securite, Fiscal) naissent a leur niveau declare,
  et uniquement une fois (``bootstrap_authority`` n'ecrase jamais un
  ajustement ulterieur de calibration, T-M20-1).

Ce module ne fait qu'executer des agents et journaliser leurs
propositions ; il ne recalcule rien et n'ecrit jamais dans le graphe,
les KPI ou les regles (frontiere M17). La deliberation (Avocat du
Diable, T-M18-1) et l'apprentissage (correction -> regle, T-M19-1) se
branchent sur ce runtime sans le modifier.
"""
from datetime import datetime, timezone
from uuid import uuid4

from calc import kpi_catalog
from core import event_store
from core.envelope import make_envelope
from governance import permissions
from graph import graph_engine

# Taxonomie E-AGENT (Backlog section 2 ; Conception 3.3).
PROPOSAL_TYPES = ("Observation", "Recommendation", "ActionProposed", "Alert")

# "Tout nouvel agent nait N0 (observateur)" (Conception 4.3).
BIRTH_AUTHORITY = permissions.AUTHORITY_MIN

# Objet de permission generique pour l'autorite de naissance d'un agent :
# un agent porte un seul niveau N0-N4 (Conception 4.3), pas une autorite
# par type d'objet - distinct des droits par domaine de T-M28-1.
AGENT_AUTHORITY_DOMAIN = "*"


class AgentError(ValueError):
    """Leve quand un agent ou une de ses propositions viole un invariant
    structurel : proposition sans preuve liee, type hors taxonomie, ou
    label absent."""


class AgentContext:
    """Facade strictement en lecture offerte a un agent pendant
    ``perceive``.

    Aucune methode d'ecriture n'y figure (pas de ``conn`` brut, pas
    d'acces a ``upsert_object``/``execute``) : un agent qui s'en tient
    a ce contrat ne peut structurellement pas muter le graphe, les KPI
    ou les regles - la frontiere M17 ("etre ecrit sans evenement",
    "muter l'etat") est ainsi rendue architecturale plutot que
    conventionnelle, sur le meme principe que le plancher N5 de M28.
    """

    def __init__(self, conn):
        self._conn = conn

    def object(self, object_id):
        """L'Objet du graphe (ou ``None``) - jamais muté par cet appel."""
        return graph_engine.get_object(self._conn, object_id)

    def neighbors(self, object_id, direction="both"):
        """Traversee bidirectionnelle des Liens (voir M09-2)."""
        return graph_engine.neighbors(self._conn, object_id, direction)

    def kpi(self, name):
        """Dernier KPI calcule (ou ``None``) - lecture seule, jamais un
        recalcul declenche depuis un agent."""
        return kpi_catalog.get(self._conn, name)

    def events(self, since=None, until=None, decision_time=None):
        """Sous-ensemble du journal (voir T-M01-2) - jamais une
        ecriture, seulement une lecture ordonnee."""
        return event_store.read(self._conn, since=since, until=until, decision_time=decision_time)


class Agent:
    """Un agent declare : nom, role, types d'evenements surveilles,
    fonction de perception, et autorite de naissance.

    Args:
        name: identifiant stable de l'agent (ex. ``"audit"``,
            ``"croissance"``) - devient le sujet de permission
            ``"agent:<name>"``.
        role: la perspective de l'agent en une phrase (dimension 1 du
            gabarit a 10 dimensions, Conception 4.1).
        watches: types d'evenements (``event["type"]``) qui declenchent
            cet agent.
        perceive: ``fn(context, event) -> list[dict] | None`` - lit le
            graphe via ``context`` (jamais un ``conn`` brut) et renvoie
            0..n propositions, chacune un dict avec au moins
            ``subtype`` (voir :data:`PROPOSAL_TYPES`), ``label`` et
            ``evidence`` (liste non vide d'identifiants d'Objets ou
            d'Evenements) ; optionnellement ``body``, ``nature``
            (defaut ``"hypothèse"``), ``score`` (defaut ``0.5``).
        is_guardian: si vrai, l'agent nait a ``guardian_authority``
            plutot qu'a N0 (exception des gardiens des lois -
            Conception 4.3).
        guardian_authority: niveau N0-N4 de naissance si
            ``is_guardian``.
    """

    def __init__(self, name, role, watches, perceive, is_guardian=False, guardian_authority=0):
        self.name = name
        self.role = role
        self.watches = frozenset(watches)
        self.perceive = perceive
        self.is_guardian = is_guardian
        self.guardian_authority = guardian_authority

    @property
    def subject(self):
        return f"agent:{self.name}"


_REGISTRY = {}


def register(agent):
    """Enregistre un agent (idempotent par nom : re-enregistrer un nom
    deja present remplace la declaration - utile pour les tests, meme
    principe que ``calc.derivation.register``)."""
    _REGISTRY[agent.name] = agent
    return agent


def registered():
    """Noms des agents enregistres (ordre stable)."""
    return sorted(_REGISTRY)


def get(name):
    return _REGISTRY.get(name)


def _watchers_of(event_type):
    return [_REGISTRY[name] for name in sorted(_REGISTRY) if event_type in _REGISTRY[name].watches]


def authority_of(conn, agent):
    """Autorite courante de ``agent`` sur l'echelle N0-N5 (T-M28-1)."""
    return permissions.authority_of(conn, agent.subject, AGENT_AUTHORITY_DOMAIN)


def bootstrap_authority(conn):
    """Amorce l'autorite de naissance des gardiens enregistres
    (Conception 4.3).

    Un agent ordinaire nait N0 sans qu'il soit necessaire d'ecrire quoi
    que ce soit : c'est deja la valeur par defaut de
    ``permissions.authority_of`` pour tout sujet jamais vu. Seul un
    gardien (``is_guardian=True``) recoit explicitement son niveau
    declare, et **seulement s'il n'a encore jamais recu d'autorite** -
    un appel repete (redemarrage) n'ecrase jamais un ajustement
    ulterieur de calibration (T-M20-1, V2).

    Returns:
        list[str]: noms des gardiens effectivement amorces lors de cet
        appel (liste vide si tout etait deja amorce).
    """
    bootstrapped = []
    for name in sorted(_REGISTRY):
        agent = _REGISTRY[name]
        if not agent.is_guardian:
            continue
        already_granted = conn.execute(
            "SELECT 1 FROM permissions WHERE subject = ? AND object_type = ?",
            (agent.subject, AGENT_AUTHORITY_DOMAIN),
        ).fetchone()
        if already_granted is None:
            permissions.grant(conn, agent.subject, AGENT_AUTHORITY_DOMAIN, agent.guardian_authority)
            bootstrapped.append(name)
    return bootstrapped


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_proposal(proposal):
    subtype = proposal.get("subtype")
    if subtype not in PROPOSAL_TYPES:
        raise AgentError(
            f"type de proposition hors taxonomie : {subtype!r} (attendu l'un de {PROPOSAL_TYPES})"
        )
    label = proposal.get("label")
    if not isinstance(label, str) or not label.strip():
        raise AgentError("proposition refusee : label requis")
    evidence = proposal.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(
        not isinstance(item, str) or not item.strip() for item in evidence
    ):
        raise AgentError(
            "proposition refusee : aucune preuve liee (evidence) - un agent ne "
            "peut jamais affirmer sans preuve (Conception 4.7, Constitution loi 7)"
        )


def emit(conn, agent, proposal, causation_event):
    """Journalise une proposition d'agent comme un evenement ``AGENT.*``.

    N'ecrit jamais dans le graphe : c'est un simple append au journal,
    exactement comme n'importe quel autre producteur d'evenements
    (Conception 2.2). ``causation_id`` est l'evenement qui a declenche
    l'agent ; ``correlation_id`` reprend celui de cet evenement (ou son
    identifiant, s'il n'en a pas encore) pour suivre le fil metier.

    Raises:
        AgentError: proposition sans preuve liee, type hors taxonomie,
            ou label absent - refusee avant d'atteindre le journal.
    """
    _validate_proposal(proposal)

    now = _now_iso()
    nature = proposal.get("nature", "hypothèse")
    score = proposal.get("score", 0.5)
    envelope = make_envelope(
        id=f"EVT:{uuid4().hex}", type_=f"AGENT.{proposal['subtype']}",
        label=proposal["label"], source="brain/agent_runtime", author=agent.subject,
        valid_from=now, ts_record=now, nature=nature, score=score,
        owner="system", visibility="interne", authority=1,
        evidence=proposal["evidence"],
    )
    payload = {"agent": agent.name, "role": agent.role, "body": proposal.get("body", {})}
    correlation_id = causation_event.get("correlation_id") or causation_event["event_id"]
    status, event_id = event_store.append(
        conn, envelope, payload=payload,
        causation_id=causation_event["event_id"], correlation_id=correlation_id,
    )
    return {"status": status, "event_id": event_id, "type": envelope["type"]}


def on_event(conn, event):
    """Reaction a un evenement du journal : chaque agent abonne a ce
    type percoit (lecture seule, via ``AgentContext``) ; ses
    propositions eventuelles sont journalisees.

    Comme ``calc.derivation.on_event``, seuls les agents dependants du
    type de l'evenement sont sollicites - jamais tous. Si une
    proposition est invalide, l'appel s'arrete et leve ``AgentError`` ;
    les propositions deja journalisees avant elle dans cet appel le
    restent (chaque ``emit`` est un append independant, jamais une
    transaction groupee, exactement comme le reste du journal).

    Returns:
        list[dict]: une entree par proposition journalisee
        (``{"agent", "status", "event_id", "type"}``).
    """
    context = AgentContext(conn)
    emitted = []
    for agent in _watchers_of(event["type"]):
        proposals = agent.perceive(context, event) or []
        for proposal in proposals:
            outcome = emit(conn, agent, proposal, event)
            emitted.append({"agent": agent.name, **outcome})
    return emitted
