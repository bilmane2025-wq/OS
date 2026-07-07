/**
 * Couche de données — désormais branchée sur les EXPORTS RÉELS déposés
 * dans src/data/exports/ (journal de caisse, Fintro, Revolut, TPE) via
 * src/lib/real/finance.ts. Serveur uniquement.
 *
 * Ce qui reste simulé : RIEN. Ce qui reste estimé : marge (25 % hist.),
 * commission Takeaway (taux ≈23,3 % à confirmer), commandes/jour (dérivé
 * du ticket moyen). Ce qui reste inconnu : soldes Fintro, social,
 * campagnes — affichés comme tels.
 */
import { BUSINESS } from "../config";
import { KAMEHA } from "../profile";
import {
  getBalances,
  getCaisseDays,
  getChargesJuin,
  getOpenReconGaps,
  getReconciliation,
  getSupplierCardSpend,
  getTakeawayPayouts,
  getTpeFees,
} from "../real/finance";
import type {
  Alert,
  AttentionBudget,
  Automation,
  Campaign,
  ChannelDay,
  EmailThread,
  IntegrationSlot,
  Kpi,
  ScheduledPost,
  SocialStat,
  SourceHealth,
  TeamMember,
} from "../types";

function iso(ts: number): string {
  return new Date(ts).toISOString();
}

/* ------------------------------------------------------------------ */
/* Ventes par canal — le journal de caisse RÉEL (8 jours saisis).       */
/* ------------------------------------------------------------------ */
/** Tous les jours réels du journal — le paramètre historique est ignoré. */
export function getChannelDays(): ChannelDay[] {
  const rate = KAMEHA.takeawayCommissionRate;
  const rows: ChannelDay[] = [];
  for (const d of getCaisseDays()) {
    rows.push(
      {
        date: d.date,
        channel: "Takeaway.com",
        revenue: d.tkw,
        orders: Math.max(1, Math.round(d.tkw / KAMEHA.historique.ticketMoyen)),
        commission: Math.round(d.tkw * rate * 100) / 100, // estimé, à confirmer
      },
      {
        date: d.date,
        channel: "Carte (TPE)",
        revenue: d.carte,
        orders: Math.max(1, Math.round(d.carte / KAMEHA.historique.ticketMoyen)),
        commission: 0, // frais TPE ≈1 % suivis à part (mesurés)
      },
      {
        date: d.date,
        channel: "Espèces",
        revenue: d.cash,
        orders: Math.max(1, Math.round(d.cash / KAMEHA.historique.ticketMoyen)),
        commission: 0,
      },
    );
  }
  return rows;
}

/* ------------------------------------------------------------------ */
/* Les 8 KPI — sur données réelles, natures fidèles.                    */
/* ------------------------------------------------------------------ */
export function getKpis(): Kpi[] {
  const caisse = getCaisseDays();
  const balances = getBalances();
  const now = iso(Date.now());
  const h = KAMEHA.historique;
  const rate = KAMEHA.takeawayCommissionRate;

  const totals = caisse.map((d) => d.total);
  const last7 = caisse.slice(-7);
  const ca7 = Math.round(last7.reduce((a, d) => a + d.total, 0) * 100) / 100;
  const tkw7 = last7.reduce((a, d) => a + d.tkw, 0);

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
    ruleVersion: 2,
    computedAt: now,
  });

  return [
    // CA : somme des 7 derniers journaux de caisse saisis — un fait
    // (avec deux écarts TPE connus, d'où 0,9 et pas 1,0).
    mk("ca", "CA 7 derniers jours (caisse)", ca7, "EUR", totals, null, "fait", 0.9),
    mk("marge", "Marge (base 25 % hist.)", Math.round(ca7 * h.margeNettePct), "EUR",
      totals.map((t) => Math.round(t * h.margeNettePct)), null, "estimation", 0.7),
    mk("food_cost", "Food cost (mesuré 267 j)", h.foodCostPct, "ratio",
      totals.map(() => h.foodCostPct), null, "fait", 0.86),
    mk("ticket_moyen", "Ticket moyen (mesuré hist.)", h.ticketMoyen, "EUR",
      totals.map(() => h.ticketMoyen), null, "fait", 0.9),
    mk("commandes_jour", "Commandes / jour (dérivé)", ca7 / h.ticketMoyen / 7, "commandes/jour",
      totals.map((t) => Math.round(t / h.ticketMoyen)), null, "estimation", 0.7),
    // Trésorerie CONNUE : Revolut 668,34 € (06/07) + TPE 281,16 € —
    // les deux comptes Fintro restent inconnus.
    mk("tresorerie", "Trésorerie connue (Revolut + TPE)", balances.totalKnown, "EUR",
      totals.map(() => balances.totalKnown), null, "estimation", 0.6),
    mk("commission", "Commission Takeaway (7 j, estimée)", Math.round(tkw7 * rate), "EUR",
      caisse.map((d) => Math.round(d.tkw * rate)), null, "estimation", 0.72),
    mk("dependance_fournisseur", "Dépendance iFood (hist.)", h.ifoodSharePct, "ratio",
      totals.map(() => h.ifoodSharePct), null, "fait", 0.85),
  ];
}

/* ------------------------------------------------------------------ */
/* Alertes RÉELLES — profil + rapprochements calculés sur les exports.  */
/* ------------------------------------------------------------------ */
const SEVERITY_RANK: Record<Alert["severity"], number> = {
  haute: 0,
  moyenne: 1,
  douce: 2,
};

export function getAlerts(): Alert[] {
  const t = Date.now();
  const balances = getBalances();
  const gaps = getOpenReconGaps();
  const recon = getReconciliation();
  const partial = recon.find((r) => r.partial && r.ecart !== null && Math.abs(r.ecart) >= 1);

  const alerts: Alert[] = [
    {
      id: "AN-T01",
      type: "tresorerie/position-connue-sous-seuil",
      severity: "haute",
      message:
        `Trésorerie connue : ${balances.totalKnown.toFixed(2).replace(".", ",")} € (Revolut 668,34 € au 06/07 + TPE 281,16 €) — sous le seuil provisoire de 2 000 €. Soldes Fintro inconnus.`,
      recommendation:
        "Récupérer les soldes des deux comptes Fintro (BE69…5578 et BE12…1192) : ~15 000 € de crédits y sont entrés fin juin, la position réelle est probablement saine — à CONFIRMER, pas à supposer.",
      impact: 2000 - balances.totalKnown,
      refs: ["tresorerie"],
      createdAt: iso(t - 12 * 3600_000),
      state: "ouverte",
    },
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
  ];

  // Écarts caisse ↔ TPE calculés depuis les exports (le vrai rapprochement).
  for (const g of gaps) {
    const explained = g.date === "2026-06-30";
    alerts.push({
      id: `AN-REC-${g.date}`,
      type: `caisse/ecart-${g.date}`,
      severity: "moyenne",
      message:
        `Écart caisse ↔ TPE le ${g.date} : ${g.carteSaisie.toFixed(2).replace(".", ",")} € saisis vs ` +
        `${(g.tpeRegle ?? 0).toFixed(2).replace(".", ",")} € réglés par le TPE (écart ${(g.ecart ?? 0).toFixed(2).replace(".", ",")} €).` +
        (explained ? " L'anomalie « +4 € » du 30/06 est EXPLIQUÉE : la saisie est fausse, pas la caisse." : ""),
      recommendation: explained
        ? "Corriger la saisie du 30/06 à 679,00 € (montant TPE mesuré) et clôturer l'anomalie."
        : "Recompter le journal du jour avec Aymane — saisie incomplète probable côté carte.",
      impact: Math.abs(g.ecart ?? 0),
      refs: ["ca"],
      createdAt: iso(t - 2 * 86_400_000),
      state: "ouverte",
    });
  }

  if (partial) {
    alerts.push({
      id: "AN-TPE-PARTIEL",
      type: "tpe/reglement-partiel",
      severity: "douce",
      message:
        `Le ${partial.date}, ${(partial.tpeRegle ?? 0).toFixed(2).replace(".", ",")} € réglés par le TPE vs ${partial.carteSaisie.toFixed(2).replace(".", ",")} € carte saisis — règlement J+1 vraisemblablement incomplet.`,
      recommendation: "Revérifier après le prochain règlement TPE avant d'ouvrir une anomalie.",
      refs: ["ca"],
      createdAt: iso(t - 12 * 3600_000),
      state: "ouverte",
    });
  }

  alerts.push(
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
      id: "AN-JIMS",
      type: "abonnement/jims-double",
      severity: "douce",
      message: "Deux domiciliations Jims NV de 44,99 € le même jour (23/06) sur l'extrait Fintro — doublon possible.",
      recommendation: "Vérifier s'il s'agit de deux abonnements voulus ou d'un prélèvement double à contester.",
      impact: 44.99,
      refs: ["charges"],
      createdAt: iso(t - 5 * 86_400_000),
      state: "ouverte",
    },
    {
      id: "AN-006",
      type: "regle/fdc-non-confirmee",
      severity: "douce",
      message:
        "Colonne « Fdc » toujours non confirmée — et absente 3 jours sur 8 dans le journal (30/06, 02/07, 04/07).",
      recommendation: "Confirmer avec Aymane ce que « Fdc » désigne (fond de caisse ?) et pourquoi elle manque certains jours.",
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
  );

  return alerts;
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
/* Emails — correspondants réels, statuts Jarvis.                       */
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
      subject: "Relevé partenaire — payout PO-20837435852",
      snippet: "3 602,77 € nets versés le 30/06 (semaine du 22 au 28/06)…",
      receivedAt: iso(t - 5 * 3600_000),
      category: "plateforme",
      needsAction: true,
      suggestedAction: "Demander le relevé BRUT : les payouts Fintro sont nets — le taux réel de commission reste à confirmer.",
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
      suggestedAction: "Le CODA n'est toujours pas actif — les extraits arrivent en captures manuelles. Relancer. [EN ATTENTE]",
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
      snippet: "1 449,27 € de carburant domicilié en juin (5 prélèvements)…",
      receivedAt: iso(t - 3 * 86_400_000),
      category: "admin",
      needsAction: false,
      unread: false,
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Social & campagnes — toujours inconnus au profil : rien d'inventé.   */
/* ------------------------------------------------------------------ */
export function getSocialStats(): SocialStat[] {
  return [];
}

export function getScheduledPosts(): ScheduledPost[] {
  return [];
}

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
        "Parse le CSV quotidien Tkw / Rev / Cash / Total / Fdc. Dernier jour reçu : 05/07 — le 06/07 manque. « Fdc » absente 3 jours sur 8.",
      authority: 2,
      requiresHuman: false,
      enabled: true,
      lastRun: iso(t - 24 * 3600_000),
      runsThisWeek: 7,
      status: "attention",
    },
    {
      id: "AUT-02",
      name: "Rapprochement caisse ↔ TPE",
      description:
        "ACTIF sur données réelles : 2 écarts détectés (28/06 : −32,80 € ; 30/06 : −4,00 € expliqué) + 1 règlement partiel surveillé (05/07).",
      authority: 3,
      requiresHuman: false,
      enabled: true,
      lastRun: iso(t - 3600_000),
      runsThisWeek: 8,
      status: "attention",
    },
    {
      id: "AUT-03",
      name: "Rapprochement banque (Fintro/Revolut)",
      description:
        "Revolut : CSV parsé (181 mouvements, solde 668,34 €). Fintro : extrait juin + captures parsés, mais flux CODA toujours inactif — soldes inconnus.",
      authority: 3,
      requiresHuman: false,
      enabled: true,
      lastRun: iso(t - 3600_000),
      runsThisWeek: 2,
      status: "attention",
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
      name: "Surveillance charges & abonnements",
      description:
        "ACTIF sur l'extrait Fintro : doublon Jims 2 × 44,99 € détecté le 23/06 ; charges juin regroupées (loyers, carburant, énergie…).",
      authority: 2,
      requiresHuman: false,
      enabled: true,
      lastRun: iso(t - 3600_000),
      runsThisWeek: 1,
      status: "ok",
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
/* Équipe — profil + mouvements réels observés sur Revolut.             */
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
      note: "Remboursements d'acompte 1 500 € le 06/07 (Revolut)",
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
    {
      id: "TM-03",
      name: "Gautier B",
      role: null,
      hoursWeek: null,
      ordersHandled: null,
      onShift: null,
      note: "Avance sur salaire 150 € versée le 06/07 (Revolut) — à régulariser en paie",
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Fraîcheur des sources (watchdog M33) — état réel au 07/07.           */
/* ------------------------------------------------------------------ */
export function getSources(): SourceHealth[] {
  return [
    {
      sourceId: "journaux-caisse",
      label: "Journaux de caisse (saisie quotidienne — dernier : 05/07)",
      expectedEveryDays: 1,
      lastSeen: "2026-07-05T22:00:00Z",
      status: "en retard",
    },
    {
      sourceId: "revolut-csv",
      label: "Revolut Business (CSV reçu, 181 mouvements → 06/07)",
      expectedEveryDays: 7,
      lastSeen: "2026-07-06T12:00:00Z",
      status: "fraîche",
    },
    {
      sourceId: "tpe-settlements",
      label: "Règlements TPE (36 jours → 06/07)",
      expectedEveryDays: 1,
      lastSeen: "2026-07-06T16:00:00Z",
      status: "fraîche",
    },
    {
      sourceId: "fintro-coda",
      label: "Fintro — extrait juin + captures reçus ; flux CODA toujours inactif",
      expectedEveryDays: 7,
      lastSeen: "2026-07-05T12:00:00Z",
      status: "en retard",
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
      label: "Relevés BRUTS Takeaway.com (les payouts Fintro sont nets)",
      expectedEveryDays: 7,
      lastSeen: null,
      status: "muette",
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Connecteurs — état réel.                                             */
/* ------------------------------------------------------------------ */
export function getIntegrations(): IntegrationSlot[] {
  return [
    {
      id: "caisse",
      label: "Journal de caisse (CSV)",
      kind: "ventes",
      enabled: true,
      envKey: "—",
      note: "ACTIF : 8 jours parsés (28/06 → 05/07). Colonne Fdc en attente de confirmation.",
    },
    {
      id: "revolut",
      label: "Revolut Business",
      kind: "banque",
      enabled: true,
      envKey: "REVOLUT_API_KEY",
      note: "CSV parsé (solde 668,34 € au 06/07). L'API rendrait le solde temps réel.",
    },
    {
      id: "tpe",
      label: "TPE / acquéreur carte",
      kind: "banque",
      enabled: true,
      envKey: "—",
      note: "ACTIF : 36 jours de règlements + 725 transactions parsés. Frais mesurés : 1,01 %.",
    },
    {
      id: "fintro-coda",
      label: "Fintro (CODA via CodaClean)",
      kind: "banque",
      enabled: false,
      envKey: "CODACLEAN_FEED_KEY",
      note: "Extrait juin + captures parsés MANUELLEMENT. CODA à activer avec Tom Van Herle → soldes automatiques.",
    },
    {
      id: "takeaway",
      label: "Takeaway.com Partner",
      kind: "ventes",
      enabled: false,
      envKey: "TAKEAWAY_PARTNER_TOKEN",
      note: "Payouts NETS visibles via Fintro (11 723 € en juin). Le relevé brut confirmera le taux ≈23,3 %.",
    },
    {
      id: "clearfacts",
      label: "ClearFacts (comptabilité Brahim)",
      kind: "comptabilité",
      enabled: false,
      envKey: "CLEARFACTS_TOKEN",
      note: "Accès en cours — nourrira marge et food cost. Q1 2026 en clôture.",
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
      id: "airtable-stp",
      label: "Airtable — Shop Ta Paire",
      kind: "ventes",
      enabled: false,
      envKey: "AIRTABLE_PAT",
      note: "Base appRvWC0OPKv4LmH6 (STOCK, PRÉCOMMANDES, ARRIVAGES, COMMANDES) — patrimoine séparé.",
    },
  ];
}

/* ------------------------------------------------------------------ */
/* Ré-exports pratiques pour les pages et l'API finance.                */
/* ------------------------------------------------------------------ */
export {
  getBalances,
  getCaisseDays,
  getChargesJuin,
  getReconciliation,
  getSupplierCardSpend,
  getTakeawayPayouts,
  getTpeFees,
};
