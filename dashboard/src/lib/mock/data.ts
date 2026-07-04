/**
 * Couche de données — calibrée sur le PROFIL RÉEL (src/data/business-profile.json).
 *
 * Trois natures de valeurs, jamais mélangées :
 *  - "fait"       : mesuré (jumeau kameha_os.db 267 j, journaux de caisse) ;
 *  - "estimation" : calculé depuis l'historique, à confirmer ;
 *  - inconnu      : null / listes vides — affiché comme tel, JAMAIS inventé.
 *
 * Les jours sans journal de caisse sont simulés à partir des moyennes
 * historiques mesurées (670 €/j, split canaux 48/43,5/8,5) et portent une
 * confiance d'estimation. Les jours connus (29/06 → 01/07) utilisent les
 * montants réels saisis.
 */
import { BUSINESS } from "../config";
import { KAMEHA } from "../profile";
import type {
  Alert,
  AttentionBudget,
  Automation,
  Campaign,
  ChannelDay,
  ChannelName,
  EmailThread,
  IntegrationSlot,
  Kpi,
  ScheduledPost,
  SocialStat,
  SourceHealth,
  TeamMember,
} from "../types";

/* ------------------------------------------------------------------ */
/* Générateur pseudo-aléatoire seedé (mulberry32) : déterministe.       */
/* ------------------------------------------------------------------ */
function mulberry32(seed: number) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const DAY_MS = 86_400_000;

function today(): number {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

function iso(ts: number): string {
  return new Date(ts).toISOString();
}

function isoDay(ts: number): string {
  return new Date(ts).toISOString().slice(0, 10);
}

/* ------------------------------------------------------------------ */
/* Ventes par canal — mesuré quand connu, sinon simulé sur l'historique */
/* ------------------------------------------------------------------ */
const CHANNELS: ChannelName[] = ["Site web", "Takeaway.com", "Comptoir"];

/** CA moyen/jour mesuré (178 987 € / 267 j) réparti par canal historique. */
const DAILY_TOTAL = KAMEHA.historique.ca / KAMEHA.historique.days; // ≈ 670 €
const COMMISSION_RATE: Record<ChannelName, number> = {
  "Site web": 0,
  "Takeaway.com": KAMEHA.takeawayCommissionRate, // ≈ 23,3 % (estimé)
  Comptoir: 0,
};

/** Journaux de caisse réels (totaux jour, saisis manuellement). */
const CAISSE_REELLE: Record<string, number> = Object.fromEntries(
  KAMEHA.caisseRecente.map((c) => [c.date, c.total]),
);

export function getChannelDays(days = 14): ChannelDay[] {
  const rng = mulberry32(20260704);
  const t0 = today() - (days - 1) * DAY_MS;
  const rows: ChannelDay[] = [];
  for (let i = 0; i < days; i++) {
    const ts = t0 + i * DAY_MS;
    const day = isoDay(ts);
    const weekday = new Date(ts).getDay();
    // Pics week-end simulés (peakDays inconnu au profil — hypothèse métier).
    const dayBoost = weekday === 5 || weekday === 6 ? 1.35 : weekday === 0 ? 1.15 : 0.92;
    const simulatedTotal = DAILY_TOTAL * dayBoost * (0.85 + rng() * 0.3);
    // Jour connu : le total réel de caisse remplace la simulation.
    const total = CAISSE_REELLE[day] ?? simulatedTotal;
    for (const channel of CHANNELS) {
      const share = KAMEHA.channelSplit[channel];
      const revenue = Math.round(total * share * 100) / 100;
      rows.push({
        date: day,
        channel,
        revenue,
        orders: Math.max(1, Math.round(revenue / KAMEHA.historique.ticketMoyen)),
        commission: Math.round(revenue * COMMISSION_RATE[channel] * 100) / 100,
      });
    }
  }
  return rows;
}

/* ------------------------------------------------------------------ */
/* Les 8 KPI — natures et scores fidèles au profil.                     */
/* ------------------------------------------------------------------ */
export function getKpis(): Kpi[] {
  const rows = getChannelDays();
  const byDay = new Map<string, { revenue: number; orders: number; commission: number }>();
  for (const r of rows) {
    const agg = byDay.get(r.date) ?? { revenue: 0, orders: 0, commission: 0 };
    agg.revenue += r.revenue;
    agg.orders += r.orders;
    agg.commission += r.commission;
    byDay.set(r.date, agg);
  }
  const dayKeys = [...byDay.keys()].sort();
  const daily = dayKeys.map((k) => byDay.get(k)!);
  const revHistory = daily.map((d) => Math.round(d.revenue));

  const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
  const last7 = daily.slice(-7);
  const prev7 = daily.slice(0, 7);
  const ca7 = Math.round(sum(last7.map((d) => d.revenue)));
  const caPrev7 = sum(prev7.map((d) => d.revenue));
  const orders7 = sum(last7.map((d) => d.orders));
  const commission7 = Math.round(sum(last7.map((d) => d.commission)));
  const now = iso(Date.now());

  const mk = (
    key: string,
    label: string,
    value: number | null,
    unit: Kpi["unit"],
    history: number[],
    delta: number | null,
    nature: Kpi["confidence"]["nature"],
    score: number,
  ): Kpi => ({
    key,
    label,
    value,
    unit,
    confidence: { nature, score },
    delta,
    history,
    ruleVersion: 1,
    computedAt: now,
  });

  const h = KAMEHA.historique;

  return [
    // CA 7 j : mélange caisse réelle (3 j) + simulation calibrée → estimation.
    mk("ca", "Chiffre d'affaires (7 j)", ca7, "EUR", revHistory, ca7 / caPrev7 - 1, "estimation", 0.75),
    // Marge : bénéfice historique ≈ 25 % du CA (mesuré sur 267 j).
    mk("marge", "Marge (7 j, base 25 % hist.)", Math.round(ca7 * h.margeNettePct), "EUR",
      revHistory.map((r) => Math.round(r * h.margeNettePct)), null, "estimation", 0.7),
    // Food cost : ≈32 % mesuré sur l'historique complet.
    mk("food_cost", "Food cost (mesuré 267 j)", h.foodCostPct, "ratio",
      revHistory.map(() => h.foodCostPct), null, "fait", 0.86),
    // Ticket moyen : 45 € mesuré.
    mk("ticket_moyen", "Ticket moyen (mesuré)", h.ticketMoyen, "EUR",
      daily.map((d) => d.revenue / Math.max(1, d.orders)), null, "fait", 0.9),
    // Dérivé du CA ÷ ticket moyen (pas un comptage) → estimation.
    mk("commandes_jour", "Commandes / jour (dérivé)", orders7 / 7, "commandes/jour",
      daily.map((d) => d.orders), null, "estimation", 0.7),
    // Trésorerie : Revolut seul connu (≈9 169 €) — solde Fintro INCONNU.
    mk("tresorerie", "Trésorerie (Revolut seul)", KAMEHA.soldeRevolut, "EUR",
      revHistory.map(() => KAMEHA.soldeRevolut), null, "estimation", 0.5),
    // Commission : Takeaway.com uniquement, taux ≈23,3 % estimé à confirmer.
    mk("commission", "Commission Takeaway (7 j)", commission7, "EUR",
      daily.map((d) => Math.round(d.commission)), null, "estimation", 0.72),
    // Dépendance fournisseur : iFood ≈48 % du food cost, mesuré.
    mk("dependance_fournisseur", "Dépendance iFood", h.ifoodSharePct, "ratio",
      revHistory.map(() => h.ifoodSharePct), null, "fait", 0.85),
  ];
}

/* ------------------------------------------------------------------ */
/* Alertes RÉELLES (anomalies ouvertes du profil) + budget d'attention. */
/* ------------------------------------------------------------------ */
const SEVERITY_RANK: Record<Alert["severity"], number> = {
  haute: 0,
  moyenne: 1,
  douce: 2,
};

export function getAlerts(): Alert[] {
  const t = Date.now();
  return [
    {
      id: "AN-001",
      type: "assurance/prime-impayee",
      severity: "haute",
      message:
        "Prime RC Exploitation 163,71 € impayée, échue le 23/04 (courtier MAXEL, Yvan Krug) — risque de rupture de couverture.",
      recommendation:
        "Vérifier si le paiement est parti ; sinon payer aujourd'hui et demander confirmation écrite de maintien de couverture. [EN ATTENTE]",
      impact: 163.71,
      refs: ["assurances"],
      createdAt: iso(t - 72 * 86_400_000 / 24),
      state: "ouverte",
    },
    {
      id: "AN-002",
      type: "litige/foodex-avoir",
      severity: "haute",
      message: "Avoir Foodex de 516,01 € ouvert (compte C64478) — toujours non crédité.",
      recommendation:
        "Relancer commande@foodex.be avec la référence de l'avoir ; joindre la facture concernée. Brouillon prêt. [RÉDIGÉ]",
      impact: 516.01,
      refs: ["food_cost", "tresorerie"],
      createdAt: iso(t - 6 * 86_400_000),
      state: "ouverte",
    },
    {
      id: "AN-003",
      type: "caisse/ecart",
      severity: "moyenne",
      message: "Écart de caisse +4,00 € le 30/06 : 1 198,90 € calculé vs 1 202,90 € saisi.",
      recommendation: "Recompter le journal du 30/06 avec Aymane ; corriger la saisie ou justifier l'écart.",
      impact: 4,
      refs: ["ca"],
      createdAt: iso(t - 4 * 86_400_000),
      state: "ouverte",
    },
    {
      id: "AN-004",
      type: "fournisseur/dependance-ifood",
      severity: "moyenne",
      message: "≈48 % du food cost concentré chez iFood (mesuré sur l'historique) — point de défaillance unique.",
      recommendation: "Identifier un second fournisseur pour les 5 références asiatiques les plus achetées.",
      refs: ["dependance_fournisseur"],
      createdAt: iso(t - 10 * 86_400_000),
      state: "ouverte",
    },
    {
      id: "AN-005",
      type: "plateforme/uber-onboarding",
      severity: "moyenne",
      message: "Onboarding Uber Eats bloqué depuis 3+ mois (possiblement suspendu) — canal de croissance fermé.",
      recommendation:
        "Relancer restaurants.belgium@uber.com / +32 2 808 66 28 avec le n° BCE 1028.675.991. [EN ATTENTE]",
      refs: ["ca"],
      createdAt: iso(t - 20 * 86_400_000),
      state: "ouverte",
    },
    {
      id: "AN-006",
      type: "regle/fdc-non-confirmee",
      severity: "douce",
      message: "Signification de la colonne « Fdc » du journal de caisse non confirmée (17,60 € / 24,20 € observés).",
      recommendation: "Confirmer avec Aymane ce que « Fdc » désigne (fond de caisse ?) — la règle de parsing attend.",
      refs: ["ca"],
      createdAt: iso(t - 3 * 86_400_000),
      state: "ouverte",
    },
    {
      id: "AN-007",
      type: "fournisseur/dirk-marchand-surfacturation",
      severity: "douce",
      message: "Litige surfacturation récurrent avec Dirk Marchand (fruits & légumes).",
      recommendation: "Contrôler ligne à ligne les 3 dernières factures avant le prochain règlement.",
      refs: ["food_cost"],
      createdAt: iso(t - 8 * 86_400_000),
      state: "ouverte",
    },
  ];
}

/** Budget d'attention M27 : dédup par type (la plus grave gagne), plafond. */
export function getAttention(cap = BUSINESS.attentionCap): AttentionBudget {
  const deduped = new Map<string, Alert>();
  for (const alert of getAlerts()) {
    const existing = deduped.get(alert.type);
    if (!existing) {
      deduped.set(alert.type, { ...alert });
      continue;
    }
    existing.refs = [...new Set([...existing.refs, ...alert.refs])];
    if (SEVERITY_RANK[alert.severity] < SEVERITY_RANK[existing.severity]) {
      existing.severity = alert.severity;
    }
  }
  const ordered = [...deduped.values()].sort(
    (a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || a.type.localeCompare(b.type),
  );
  return {
    shown: ordered.slice(0, cap),
    suppressed: Math.max(0, ordered.length - cap),
    total: ordered.length,
    cap,
  };
}

/* ------------------------------------------------------------------ */
/* Emails — correspondants réels du profil, statuts Jarvis.             */
/* ------------------------------------------------------------------ */
export function getEmails(): EmailThread[] {
  const t = Date.now();
  return [
    {
      id: "EM-01",
      from: "Foodex (commande@foodex.be)",
      subject: "Avoir 516,01 € — compte C64478",
      snippet: "Relance concernant l'avoir toujours non crédité sur votre compte…",
      receivedAt: iso(t - 2 * 3600_000),
      category: "fournisseur",
      needsAction: true,
      suggestedAction: "Relance [RÉDIGÉ] — envoi N5 : vous. Rappel : commande avant 16 h pour J+1.",
      unread: true,
    },
    {
      id: "EM-02",
      from: "Takeaway.com (Ruben Pécriaux)",
      subject: "Relevé hebdomadaire partenaire",
      snippet: "Votre relevé de commandes et commissions de la semaine est disponible…",
      receivedAt: iso(t - 5 * 3600_000),
      category: "plateforme",
      needsAction: true,
      suggestedAction: "Importer l'export → confirmer le taux de commission réel (≈23,3 % estimé).",
      unread: true,
    },
    {
      id: "EM-03",
      from: "Fintro (Tom Van Herle)",
      subject: "Mandat CodaClean — BE69 1431 3360 5578",
      snippet: "Suite à la signature du mandat, voici les étapes d'activation du flux CODA…",
      receivedAt: iso(t - 26 * 3600_000),
      category: "banque",
      needsAction: true,
      suggestedAction: "Confirmer que le bank-feed CODA est actif — le watchdog n'a encore rien reçu. [EN ATTENTE]",
      unread: false,
    },
    {
      id: "EM-04",
      from: "Brahim (comptable)",
      subject: "Accès ClearFacts / clôture Q1 2026",
      snippet: "L'accès ClearFacts est en cours de configuration ; il me manque encore…",
      receivedAt: iso(t - 30 * 3600_000),
      category: "admin",
      needsAction: true,
      suggestedAction: "Demander la fréquence de remise de la balance (inconnue au profil).",
      unread: false,
    },
    {
      id: "EM-05",
      from: "Uber Eats (restaurants.belgium@uber.com)",
      subject: "Dossier d'onboarding — statut",
      snippet: "Votre dossier est en cours d'examen…  (dernier message reçu il y a plus de 3 mois)",
      receivedAt: iso(t - 24 * 86_400_000),
      category: "plateforme",
      needsAction: true,
      suggestedAction: "Relance téléphonique +32 2 808 66 28 avec BCE 1028.675.991. [EN ATTENTE]",
      unread: false,
    },
    {
      id: "EM-06",
      from: "Fleetcor (billingdocuments@fleetcor.eu)",
      subject: "Document de facturation disponible",
      snippet: "Votre document de facturation mensuel est prêt au téléchargement…",
      receivedAt: iso(t - 3 * 86_400_000),
      category: "admin",
      needsAction: false,
      unread: false,
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Social — INCONNU au profil : aucun chiffre inventé.                  */
/* ------------------------------------------------------------------ */
export function getSocialStats(): SocialStat[] {
  // Handles et accès non fournis (section 4 du profil en attente).
  return [];
}

export function getScheduledPosts(): ScheduledPost[] {
  // Aucun planificateur branché — seul le Reels Tracker (3 reels seedés)
  // existe côté analyse de contenu.
  return [];
}

/* ------------------------------------------------------------------ */
/* Campagnes — INCONNU au profil : rien d'inventé.                      */
/* ------------------------------------------------------------------ */
export function getCampaigns(): Campaign[] {
  return [];
}

/* ------------------------------------------------------------------ */
/* Automatisations — échelle N0-N5, état réel des chantiers.            */
/* ------------------------------------------------------------------ */
export function getAutomations(): Automation[] {
  const t = Date.now();
  return [
    {
      id: "AUT-01",
      name: "Ingestion journaux de caisse",
      description:
        "Saisie manuelle Tkw / Rev(carte) / Cash / Total / Fdc → événements. La colonne « Fdc » attend confirmation avant parsing complet.",
      authority: 2,
      requiresHuman: false,
      enabled: true,
      lastRun: iso(t - 3 * 86_400_000),
      runsThisWeek: 3,
      status: "attention",
    },
    {
      id: "AUT-02",
      name: "Recalcul incrémental des KPI",
      description: "DAG M12 : seuls les KPI dépendant des nouveaux événements sont recalculés.",
      authority: 2,
      requiresHuman: false,
      enabled: true,
      lastRun: iso(t - 3 * 86_400_000),
      runsThisWeek: 12,
      status: "ok",
    },
    {
      id: "AUT-03",
      name: "Rapprochement caisse ↔ banque",
      description:
        "Attend le flux CODA Fintro (mandat CodaClean signé, activation à confirmer) — inerte sans relevés.",
      authority: 3,
      requiresHuman: false,
      enabled: false,
      lastRun: null,
      runsThisWeek: 0,
      status: "inerte",
    },
    {
      id: "AUT-04",
      name: "Relance fournisseur (brouillon email)",
      description:
        "Brouillon de relance Foodex (avoir 516,01 €) prêt [RÉDIGÉ] — l'envoi reste humain (N5).",
      authority: 3,
      requiresHuman: true,
      enabled: true,
      lastRun: iso(t - 2 * 3600_000),
      runsThisWeek: 1,
      status: "ok",
    },
    {
      id: "AUT-05",
      name: "Suivi litiges fournisseurs",
      description:
        "Foodex (avoir 516,01 €) + Dirk Marchand (surfacturation récurrente) : relances et contrôle facture.",
      authority: 3,
      requiresHuman: true,
      enabled: true,
      lastRun: iso(t - 6 * 86_400_000),
      runsThisWeek: 2,
      status: "attention",
    },
    {
      id: "AUT-06",
      name: "Paiement fournisseur",
      description:
        "Transition matérielle irréversible : plancher N5 — humain exclusivement, par construction.",
      authority: 5,
      requiresHuman: true,
      enabled: false,
      lastRun: null,
      runsThisWeek: 0,
      status: "inerte",
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Équipe — profil réel, inconnues affichées comme telles.              */
/* ------------------------------------------------------------------ */
export function getTeam(): TeamMember[] {
  return [
    {
      id: "TM-01",
      name: "Aymane Bonouh",
      role: "Cogérant",
      hoursWeek: null,
      ordersHandled: null,
      onShift: null,
    },
    {
      id: "TM-02",
      name: "Sacha Debast",
      role: null,
      hoursWeek: null,
      ordersHandled: null,
      onShift: null,
      note: "Contrat Article 61 (CPAS Wavre)",
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Fraîcheur des sources (watchdog M33) — état réel.                    */
/* ------------------------------------------------------------------ */
export function getSources(): SourceHealth[] {
  return [
    {
      sourceId: "journaux-caisse",
      label: "Journaux de caisse (saisie manuelle quotidienne)",
      expectedEveryDays: 1,
      lastSeen: "2026-07-01T22:00:00Z",
      status: "en retard",
    },
    {
      sourceId: "fintro-coda",
      label: "Relevés Fintro (CODA via CodaClean — mandat signé)",
      expectedEveryDays: 7,
      lastSeen: null,
      status: "muette",
    },
    {
      sourceId: "revolut-csv",
      label: "Relevés Revolut Business (CSV)",
      expectedEveryDays: 7,
      lastSeen: null,
      status: "muette",
    },
    {
      sourceId: "balance-comptable",
      label: "Balance comptable Brahim (Q1 2026 en cours)",
      expectedEveryDays: 90,
      lastSeen: null,
      status: "en retard",
    },
    {
      sourceId: "takeaway-export",
      label: "Exports Takeaway.com (relevés partenaire)",
      expectedEveryDays: 7,
      lastSeen: null,
      status: "muette",
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Connecteurs — inertes tant que la clé n'est pas dans le coffre M30.  */
/* ------------------------------------------------------------------ */
export function getIntegrations(): IntegrationSlot[] {
  return [
    {
      id: "takeaway",
      label: "Takeaway.com Partner",
      kind: "ventes",
      enabled: false,
      envKey: "TAKEAWAY_PARTNER_TOKEN",
      note: "Commandes + relevés — confirme le taux de commission réel (≈23,3 % estimé). Contact : Ruben Pécriaux.",
    },
    {
      id: "fintro-coda",
      label: "Fintro (CODA via CodaClean)",
      kind: "banque",
      enabled: false,
      envKey: "CODACLEAN_FEED_KEY",
      note: "Mandat signé sur BE69 1431 3360 5578 — activation à confirmer avec Tom Van Herle.",
    },
    {
      id: "revolut",
      label: "Revolut Business",
      kind: "banque",
      enabled: false,
      envKey: "REVOLUT_API_KEY",
      note: "Solde connu ≈9 169 € (dernière lecture manuelle) — export CSV à confirmer.",
    },
    {
      id: "clearfacts",
      label: "ClearFacts (comptabilité Brahim)",
      kind: "comptabilité",
      enabled: false,
      envKey: "CLEARFACTS_TOKEN",
      note: "Accès en cours de configuration — nourrira marge et food cost. Q1 2026 en clôture.",
    },
    {
      id: "gmail",
      label: "Gmail",
      kind: "email",
      enabled: false,
      envKey: "GMAIL_OAUTH_CLIENT",
      note: "Triage factures Foodex/Seamar/Fleetcor et relevés → inbox OS.",
    },
    {
      id: "uber-eats",
      label: "Uber Eats",
      kind: "ventes",
      enabled: false,
      envKey: "UBER_EATS_API_KEY",
      note: "Onboarding bloqué 3+ mois côté plateforme — relance en cours, pas une question de clé.",
    },
    {
      id: "airtable-stp",
      label: "Airtable — Shop Ta Paire",
      kind: "ventes",
      enabled: false,
      envKey: "AIRTABLE_PAT",
      note: "Base appRvWC0OPKv4LmH6 (STOCK, PRÉCOMMANDES, ARRIVAGES, COMMANDES) — patrimoine séparé.",
    },
  ];
}
