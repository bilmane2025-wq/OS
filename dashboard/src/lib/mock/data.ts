/**
 * Couche de données simulée — le contrat exact que rempliront les vrais
 * connecteurs (connectors_disabled/ de l'OS : uber_eats_api, deliveroo_api,
 * bank_api, accounting_api, meta_api). Chaque fonction est le point de
 * branchement d'une intégration réelle : même forme, mêmes garanties
 * (confiance sur chaque valeur, null plutôt qu'un zéro inventé).
 *
 * Générateur seedé → chiffres stables entre rendus (pas d'hydratation
 * divergente), cohérents entre eux (CA = somme des canaux, etc.).
 */
import { BUSINESS } from "../config";
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

/** Ancre temporelle : minuit du jour courant (stable pendant un rendu). */
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
/* Ventes par canal — 14 jours (Uber Eats / Deliveroo / Direct).        */
/* ------------------------------------------------------------------ */
const CHANNELS: ChannelName[] = ["Uber Eats", "Deliveroo", "Direct"];
// Poids de chaque canal et taux de commission plateforme (~30 %).
const CHANNEL_PROFILE: Record<ChannelName, { base: number; commission: number }> = {
  "Uber Eats": { base: 520, commission: 0.3 },
  Deliveroo: { base: 380, commission: 0.29 },
  Direct: { base: 260, commission: 0 },
};

export function getChannelDays(days = 14): ChannelDay[] {
  const rng = mulberry32(20260703);
  const t0 = today() - (days - 1) * DAY_MS;
  const rows: ChannelDay[] = [];
  for (let i = 0; i < days; i++) {
    const ts = t0 + i * DAY_MS;
    const weekday = new Date(ts).getDay();
    // Vendredi/samedi/dimanche : pics de commandes (métier livraison).
    const dayBoost = weekday === 5 || weekday === 6 ? 1.45 : weekday === 0 ? 1.2 : 1;
    for (const channel of CHANNELS) {
      const { base, commission } = CHANNEL_PROFILE[channel];
      const revenue = Math.round(base * dayBoost * (0.82 + rng() * 0.4));
      const ticket = 21 + rng() * 8; // ticket moyen ~21-29 €
      rows.push({
        date: isoDay(ts),
        channel,
        revenue,
        orders: Math.max(1, Math.round(revenue / ticket)),
        commission: Math.round(revenue * commission),
      });
    }
  }
  return rows;
}

/* ------------------------------------------------------------------ */
/* Les 8 KPI du MVP (catalogue calc/kpi_catalog.py).                    */
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
  const revHistory = daily.map((d) => d.revenue);

  const last7 = daily.slice(-7);
  const prev7 = daily.slice(0, 7);
  const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
  const ca7 = sum(last7.map((d) => d.revenue));
  const caPrev7 = sum(prev7.map((d) => d.revenue));
  const orders7 = sum(last7.map((d) => d.orders));
  const commission7 = sum(last7.map((d) => d.commission));

  const rng = mulberry32(42);
  const foodCost = 0.312; // achats Foodex / CA — au-dessus de la cible 28 %
  const couts7 = Math.round(ca7 * foodCost);
  const marge7 = ca7 - couts7 - commission7;
  const treso = 4870; // au-dessus du seuil de 2 000 €, mais en baisse
  const now = iso(Date.now());

  const mk = (
    key: string,
    label: string,
    value: number | null,
    unit: Kpi["unit"],
    history: number[],
    delta: number | null,
    nature: Kpi["confidence"]["nature"] = "fait",
    score = 0.92 + rng() * 0.07,
  ): Kpi => ({
    key,
    label,
    value,
    unit,
    confidence: { nature, score: Math.round(score * 100) / 100 },
    delta,
    history,
    ruleVersion: 1,
    computedAt: now,
  });

  return [
    mk("ca", "Chiffre d'affaires (7 j)", ca7, "EUR", revHistory, ca7 / caPrev7 - 1),
    mk("marge", "Marge (7 j)", marge7, "EUR",
      daily.map((d) => Math.round(d.revenue * (1 - foodCost) - d.commission)),
      0.041, "estimation", 0.83),
    mk("food_cost", "Food cost", foodCost, "ratio",
      revHistory.map((_, i) => 0.29 + 0.03 * (i / revHistory.length) + (mulberry32(i)() - 0.5) * 0.01),
      0.028, "estimation", 0.78),
    mk("ticket_moyen", "Ticket moyen", ca7 / orders7, "EUR",
      daily.map((d) => d.revenue / Math.max(1, d.orders)), 0.012),
    mk("commandes_jour", "Commandes / jour", orders7 / 7, "commandes/jour",
      daily.map((d) => d.orders), (orders7 / 7) / (sum(prev7.map((d) => d.orders)) / 7) - 1),
    mk("tresorerie", "Trésorerie", treso, "EUR",
      revHistory.map((_, i) => 6400 - i * 118 + (mulberry32(i * 7)() - 0.5) * 300), -0.087),
    mk("commission", "Commissions plateformes (7 j)", commission7, "EUR",
      daily.map((d) => d.commission), 0.056),
    mk("dependance_fournisseur", `Dépendance ${BUSINESS.mainSupplier}`, 0.63, "ratio",
      revHistory.map((_, i) => 0.58 + 0.05 * (i / revHistory.length)), 0.032, "fait", 0.95),
  ];
}

/* ------------------------------------------------------------------ */
/* Alertes proactives + budget d'attention (experience/attention.py).   */
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
      type: "reconciliation/ecart-encaissement-vente",
      severity: "haute",
      message:
        "Écart de 7,2 % entre encaissements bancaires et ventes déclarées sur les 7 derniers jours (seuil : 5 %).",
      recommendation:
        "Vérifier les encaissements manquants ou les ventes non déclarées sur la période.",
      probability: 0.86,
      impact: 640,
      refs: ["ca", "tresorerie"],
      createdAt: iso(t - 2 * 3600_000),
      state: "ouverte",
    },
    {
      id: "AN-002",
      type: "seuil/food_cost",
      severity: "moyenne",
      message: "Food cost à 31,2 % — au-dessus de la cible de 28 % pour la 3e semaine.",
      recommendation:
        `Renégocier les prix ${BUSINESS.mainSupplier} ou ajuster les fiches techniques des 3 plats les plus vendus.`,
      probability: 0.92,
      impact: 410,
      refs: ["food_cost"],
      createdAt: iso(t - 26 * 3600_000),
      state: "ouverte",
    },
    {
      id: "AN-003",
      type: "seuil/dependance_fournisseur",
      severity: "moyenne",
      message: `63 % des achats concentrés chez ${BUSINESS.mainSupplier} — risque de rupture unique.`,
      recommendation: "Identifier un second fournisseur pour les 5 références les plus achetées.",
      probability: 0.7,
      impact: 900,
      refs: ["dependance_fournisseur"],
      createdAt: iso(t - 50 * 3600_000),
      state: "ouverte",
    },
    {
      id: "AN-004",
      type: "watchdog/source-en-retard",
      severity: "douce",
      message: "La balance comptable n'a pas été déposée depuis 12 jours (attendue tous les 7 jours).",
      recommendation: "Relancer le comptable ou déposer l'export XLSX dans l'inbox.",
      refs: ["balance-comptable"],
      createdAt: iso(t - 12 * 3600_000),
      state: "ouverte",
    },
    {
      id: "AN-005",
      type: "watchdog/source-en-retard",
      severity: "douce",
      message: "Relevé bancaire attendu depuis 3 jours.",
      recommendation: "Déposer l'export CSV Belfius dans l'inbox.",
      refs: ["banque-releve"],
      createdAt: iso(t - 3 * 3600_000),
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
/* Emails — triage type Gmail (perception/parsers/email_parser).        */
/* ------------------------------------------------------------------ */
export function getEmails(): EmailThread[] {
  const t = Date.now();
  return [
    {
      id: "EM-01",
      from: `Facturation ${BUSINESS.mainSupplier}`,
      subject: `Facture ${BUSINESS.mainSupplier} n° 2026-1187 — 1 284,50 €`,
      snippet: "Veuillez trouver ci-joint votre facture du mois. Échéance au 15/07…",
      receivedAt: iso(t - 40 * 60_000),
      category: "fournisseur",
      needsAction: true,
      suggestedAction: "Déposer le PDF dans l'inbox OS → extraction + KPI food cost",
      unread: true,
    },
    {
      id: "EM-02",
      from: "Uber Eats Restaurants",
      subject: "Votre relevé hebdomadaire est disponible",
      snippet: "Résumé de la semaine : 214 commandes, 4 abandons, note moyenne 4,6…",
      receivedAt: iso(t - 3 * 3600_000),
      category: "plateforme",
      needsAction: true,
      suggestedAction: "Importer le CSV commandes → rapprochement encaissements",
      unread: true,
    },
    {
      id: "EM-03",
      from: "Deliveroo Partenaires",
      subject: "Action requise : photos du menu à mettre à jour",
      snippet: "Les menus avec photos récentes convertissent 24 % mieux…",
      receivedAt: iso(t - 7 * 3600_000),
      category: "plateforme",
      needsAction: true,
      suggestedAction: "Planifier une séance photo — lier à la campagne « Menu été »",
      unread: false,
    },
    {
      id: "EM-04",
      from: "Belfius Direct",
      subject: "Votre relevé de compte est disponible",
      snippet: "Le relevé n° 2026-27 de votre compte professionnel est prêt…",
      receivedAt: iso(t - 26 * 3600_000),
      category: "banque",
      needsAction: true,
      suggestedAction: "Exporter le CSV → inbox OS (le watchdog l'attend depuis 3 j)",
      unread: false,
    },
    {
      id: "EM-05",
      from: "Google Business",
      subject: "3 nouveaux avis sur votre fiche",
      snippet: "« Meilleur couscous du quartier, livraison rapide… » — 2 × 5★, 1 × 3★",
      receivedAt: iso(t - 30 * 3600_000),
      category: "client",
      needsAction: true,
      suggestedAction: "Répondre au 3★ (Jarvis peut proposer un brouillon)",
      unread: false,
    },
    {
      id: "EM-06",
      from: "SPF Finances",
      subject: "Rappel : déclaration TVA T2",
      snippet: "Votre déclaration TVA du deuxième trimestre est attendue avant le 20/07…",
      receivedAt: iso(t - 2 * 86_400_000),
      category: "admin",
      needsAction: false,
      unread: false,
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Social — analytics + planificateur (meta_api inerte).                */
/* ------------------------------------------------------------------ */
export function getSocialStats(): SocialStat[] {
  return [
    {
      platform: "Instagram",
      followers: 3840,
      followersDelta: 0.034,
      engagementRate: 0.047,
      reach7d: 12400,
      topPost: "Reel « coulisses du service du vendredi » — 8,2 k vues",
    },
    {
      platform: "Facebook",
      followers: 2210,
      followersDelta: 0.008,
      engagementRate: 0.021,
      reach7d: 5400,
      topPost: "Promo midi -20 % — 340 interactions",
    },
    {
      platform: "TikTok",
      followers: 1490,
      followersDelta: 0.112,
      engagementRate: 0.083,
      reach7d: 21800,
      topPost: "« Le dressage du tajine en 15 s » — 18 k vues",
    },
    {
      platform: "Google Business",
      followers: 0,
      followersDelta: 0,
      engagementRate: 0,
      reach7d: 3100,
      topPost: "Note moyenne 4,6★ (128 avis) — +3 avis cette semaine",
    },
  ];
}

export function getScheduledPosts(): ScheduledPost[] {
  const t0 = today();
  return [
    {
      id: "PST-01",
      platform: "Instagram",
      title: "Reel : nouveau plat de la semaine",
      scheduledFor: iso(t0 + 1 * DAY_MS + 11 * 3600_000),
      status: "planifié",
      mediaType: "vidéo",
    },
    {
      id: "PST-02",
      platform: "TikTok",
      title: "Coulisses : préparation du couscous du vendredi",
      scheduledFor: iso(t0 + 2 * DAY_MS + 17 * 3600_000),
      status: "planifié",
      mediaType: "vidéo",
    },
    {
      id: "PST-03",
      platform: "Facebook",
      title: "Promo midi : -20 % sur les formules cette semaine",
      scheduledFor: iso(t0 + 3 * DAY_MS + 10 * 3600_000),
      status: "brouillon",
      mediaType: "photo",
    },
    {
      id: "PST-04",
      platform: "Google Business",
      title: "Réponse aux 3 nouveaux avis (brouillon Jarvis prêt)",
      scheduledFor: iso(t0 + 1 * DAY_MS + 9 * 3600_000),
      status: "brouillon",
      mediaType: "avis",
    },
    {
      id: "PST-05",
      platform: "Instagram",
      title: "Story : sondage « votre plat préféré de l'été ? »",
      scheduledFor: iso(t0 - 1 * DAY_MS + 12 * 3600_000),
      status: "publié",
      mediaType: "story",
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Campagnes marketing.                                                 */
/* ------------------------------------------------------------------ */
export function getCampaigns(): Campaign[] {
  const t0 = today();
  return [
    {
      id: "CMP-01",
      name: "Menu été — lancement",
      channel: "Meta Ads (IG + FB)",
      status: "active",
      budget: 450,
      spent: 287,
      revenueAttributed: 1240,
      orders: 52,
      startedAt: iso(t0 - 12 * DAY_MS),
      endsAt: iso(t0 + 9 * DAY_MS),
    },
    {
      id: "CMP-02",
      name: "Boost visibilité Uber Eats",
      channel: "Uber Eats Ads",
      status: "active",
      budget: 300,
      spent: 246,
      revenueAttributed: 830,
      orders: 34,
      startedAt: iso(t0 - 8 * DAY_MS),
      endsAt: iso(t0 + 6 * DAY_MS),
    },
    {
      id: "CMP-03",
      name: "Offre -20 % midi semaine",
      channel: "Deliveroo Promo",
      status: "en pause",
      budget: 200,
      spent: 118,
      revenueAttributed: 390,
      orders: 21,
      startedAt: iso(t0 - 20 * DAY_MS),
      endsAt: null,
    },
    {
      id: "CMP-04",
      name: "Ramadan — paniers famille",
      channel: "Meta Ads + WhatsApp",
      status: "terminée",
      budget: 600,
      spent: 600,
      revenueAttributed: 3120,
      orders: 96,
      startedAt: iso(t0 - 120 * DAY_MS),
      endsAt: iso(t0 - 90 * DAY_MS),
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Automatisations — échelle d'autorité N0-N5 (governance/permissions). */
/* ------------------------------------------------------------------ */
export function getAutomations(): Automation[] {
  const t = Date.now();
  return [
    {
      id: "AUT-01",
      name: "Ingestion inbox → événements",
      description:
        "Poll de l'inbox, parsing CSV/XLSX/PDF/email, dédup, quarantaine — la boucle vivante de l'OS.",
      authority: 2,
      requiresHuman: false,
      enabled: true,
      lastRun: iso(t - 4 * 60_000),
      runsThisWeek: 2016,
      status: "ok",
    },
    {
      id: "AUT-02",
      name: "Recalcul incrémental des KPI",
      description: "DAG M12 : seuls les KPI dépendant des nouveaux événements sont recalculés.",
      authority: 2,
      requiresHuman: false,
      enabled: true,
      lastRun: iso(t - 4 * 60_000),
      runsThisWeek: 391,
      status: "ok",
    },
    {
      id: "AUT-03",
      name: "Rapprochement encaissements ↔ ventes",
      description: "Écart > 5 % ⇒ anomalie avec gravité, probabilité, impact et recommandation.",
      authority: 3,
      requiresHuman: false,
      enabled: true,
      lastRun: iso(t - 2 * 3600_000),
      runsThisWeek: 7,
      status: "attention",
    },
    {
      id: "AUT-04",
      name: "Relance fournisseur (brouillon email)",
      description:
        "Prépare un brouillon de relance quand une facture attendue manque — l'envoi reste humain.",
      authority: 3,
      requiresHuman: true,
      enabled: true,
      lastRun: iso(t - 3 * 86_400_000),
      runsThisWeek: 2,
      status: "ok",
    },
    {
      id: "AUT-05",
      name: "Publication sociale planifiée",
      description:
        "Publie les contenus approuvés à l'heure prévue (meta_api inerte : approbation humaine requise).",
      authority: 4,
      requiresHuman: true,
      enabled: false,
      lastRun: null,
      runsThisWeek: 0,
      status: "inerte",
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
/* Équipe.                                                              */
/* ------------------------------------------------------------------ */
export function getTeam(): TeamMember[] {
  return [
    { id: "TM-01", name: "Yassine", role: "Cuisine", hoursWeek: 42, ordersHandled: 388, onShift: true },
    { id: "TM-02", name: "Sarah", role: "Cuisine", hoursWeek: 35, ordersHandled: 301, onShift: true },
    { id: "TM-03", name: "Mehdi", role: "Comptoir / packaging", hoursWeek: 28, ordersHandled: 512, onShift: false },
    { id: "TM-04", name: "Lina", role: "Comptoir / packaging", hoursWeek: 22, ordersHandled: 344, onShift: true },
  ];
}

/* ------------------------------------------------------------------ */
/* Fraîcheur des sources (watchdog M33).                                */
/* ------------------------------------------------------------------ */
export function getSources(): SourceHealth[] {
  const t = Date.now();
  return [
    {
      sourceId: "plateforme-commandes",
      label: "Exports commandes (Uber Eats / Deliveroo)",
      expectedEveryDays: 1,
      lastSeen: iso(t - 10 * 3600_000),
      status: "fraîche",
    },
    {
      sourceId: "banque-releve",
      label: "Relevé bancaire (CSV Belfius)",
      expectedEveryDays: 7,
      lastSeen: iso(t - 10 * 86_400_000),
      status: "en retard",
    },
    {
      sourceId: "balance-comptable",
      label: "Balance comptable (XLSX)",
      expectedEveryDays: 7,
      lastSeen: iso(t - 12 * 86_400_000),
      status: "en retard",
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Connecteurs — inertes tant que la clé n'est pas dans le coffre M30.  */
/* ------------------------------------------------------------------ */
export function getIntegrations(): IntegrationSlot[] {
  return [
    {
      id: "uber-eats",
      label: "Uber Eats API",
      kind: "ventes",
      enabled: false,
      envKey: "UBER_EATS_API_KEY",
      note: "Commandes temps réel + relevés — remplace l'import CSV manuel.",
    },
    {
      id: "deliveroo",
      label: "Deliveroo API",
      kind: "ventes",
      enabled: false,
      envKey: "DELIVEROO_API_KEY",
      note: "Commandes + promotions — remplace l'import CSV manuel.",
    },
    {
      id: "bank",
      label: "Banque (PSD2 / Belfius)",
      kind: "banque",
      enabled: false,
      envKey: "BANK_API_KEY",
      note: "Relevés automatiques — alimente trésorerie et rapprochement.",
    },
    {
      id: "accounting",
      label: "Comptabilité",
      kind: "comptabilité",
      enabled: false,
      envKey: "ACCOUNTING_API_KEY",
      note: "Balance comptable — nourrit marge et food cost.",
    },
    {
      id: "gmail",
      label: "Gmail",
      kind: "email",
      enabled: false,
      envKey: "GMAIL_OAUTH_CLIENT",
      note: "Triage factures/relevés → inbox OS sans dépôt manuel.",
    },
    {
      id: "meta",
      label: "Meta (Instagram + Facebook)",
      kind: "social",
      enabled: false,
      envKey: "META_GRAPH_TOKEN",
      note: "Analytics + publication planifiée (approbation humaine, N4).",
    },
  ];
}
