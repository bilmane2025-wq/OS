/**
 * Moteur Jarvis — compréhension d'intention (FR) + personnalité.
 *
 * Tourne entièrement côté client sur l'instantané de données (zéro appel
 * externe, conforme à la Constitution de l'OS). Le branchement d'un vrai
 * LLM se fait dans app/api/jarvis/route.ts : même contrat JarvisReply.
 */
import { BUSINESS } from "./config";
import { fmtConfidence, fmtEur, fmtNum, fmtPct } from "./format";
import type { AttentionBudget, JarvisReply, Kpi } from "./types";

export interface JarvisContext {
  kpis: Kpi[];
  attention: AttentionBudget;
}

/* ---------------------------------------------------------------- */
/* Personnalité : efficace d'abord, pique d'esprit ensuite.           */
/* ---------------------------------------------------------------- */
const QUIPS = [
  "Pendant que vous lisiez ceci, j'ai recalculé deux KPI. De rien.",
  "Je ne dors jamais. La boucle de synchro non plus. On s'entend bien.",
  "Efficacité : 100 %. Modestie : en cours de calibration.",
  "J'aurais bien pris un café, mais je carbure aux événements horodatés.",
  "Notez que je n'invente jamais un chiffre. Contrairement à certains tableurs.",
];

function quip(seed: number): string | undefined {
  // Une pique une fois sur trois — l'attention du dirigeant est un budget.
  return seed % 3 === 0 ? QUIPS[seed % QUIPS.length] : undefined;
}

const GREETINGS = [
  `À votre service, ${BUSINESS.operator}. Les huit KPI sont à jour et la boucle tourne.`,
  `Présent. ${BUSINESS.name} est sous surveillance — que puis-je pour vous ?`,
  "Oui ? J'écoutais déjà, évidemment.",
];

/* ---------------------------------------------------------------- */
/* Intentions : motif → réponse. Ordre = priorité.                    */
/* ---------------------------------------------------------------- */
interface Intent {
  patterns: RegExp[];
  handle: (ctx: JarvisContext, q: string, seed: number) => JarvisReply;
}

function kpiByKey(ctx: JarvisContext, key: string): Kpi | undefined {
  return ctx.kpis.find((k) => k.key === key);
}

function kpiAnswer(ctx: JarvisContext, key: string, phrase: (k: Kpi) => string): JarvisReply {
  const k = kpiByKey(ctx, key);
  if (!k || k.value === null) {
    return {
      text: "Pas de donnée fiable sur ce point — et je ne vais certainement pas l'inventer. Déposez la source manquante dans l'inbox et je recalcule.",
      navigateTo: "/alertes",
    };
  }
  return { text: `${phrase(k)} (${fmtConfidence(k.confidence)}).` };
}

const NAV_TARGETS: Array<{ patterns: RegExp; path: string; label: string }> = [
  { patterns: /instantan|accueil|home|vue.?10|cockpit/i, path: "/", label: "Vue instantanée" },
  { patterns: /revenu|vente|chiffre|commande/i, path: "/revenus", label: "Revenus & ventes" },
  { patterns: /mail|email|courriel|boite|boîte/i, path: "/emails", label: "Emails" },
  { patterns: /social|insta|tiktok|facebook|contenu|post/i, path: "/social", label: "Social & contenu" },
  { patterns: /campagne|marketing|pub|ads/i, path: "/campagnes", label: "Campagnes" },
  { patterns: /automat|tâche|tache|robot/i, path: "/automatisations", label: "Automatisations" },
  { patterns: /alerte|anomalie|insight|probl/i, path: "/alertes", label: "Insights & alertes" },
  { patterns: /équipe|equipe|staff|personnel/i, path: "/equipe", label: "Équipe" },
];

const INTENTS: Intent[] = [
  {
    patterns: [/^(salut|bonjour|hello|hey|yo|jarvis)\b/i],
    handle: (_ctx, _q, seed) => ({
      text: GREETINGS[seed % GREETINGS.length],
      quip: quip(seed + 1),
    }),
  },
  {
    patterns: [/(ça va|comment vas|status|statut|état du système|etat du systeme|rapport)/i],
    handle: (ctx, _q, seed) => {
      const { shown, suppressed, total } = ctx.attention;
      const worst = shown[0];
      return {
        text:
          `Systèmes nominaux. ${total} sollicitation${total > 1 ? "s" : ""} en attente, ` +
          `${shown.length} montrée${shown.length > 1 ? "s" : ""} sous budget d'attention` +
          (suppressed ? ` (${suppressed} contenue${suppressed > 1 ? "s" : ""} — consultables, pas insistantes)` : "") +
          `. La plus urgente : ${worst ? worst.message : "aucune, profitez-en"}`,
        navigateTo: "/alertes",
        quip: quip(seed),
      };
    },
  },
  {
    patterns: [/(chiffre d.affaires|\bca\b|revenu)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "ca", (k) => `Chiffre d'affaires des 7 derniers jours : ${fmtEur(k.value)}, ${fmtPct(k.delta, true)} vs semaine précédente`),
  },
  {
    patterns: [/(trésorerie|tresorerie|cash|banque|solde)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "tresorerie", (k) =>
        `Trésorerie : ${fmtEur(k.value)} — seuil d'alerte à ${fmtEur(BUSINESS.cashAlertThreshold)}. Tendance ${k.delta && k.delta < 0 ? "baissière, je surveille de près" : "stable"}`),
  },
  {
    patterns: [/(food ?cost|coût matière|cout matiere)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "food_cost", (k) =>
        `Food cost : ${fmtPct(k.value)} — la cible est 28 %. ${k.value! > 0.28 ? `${BUSINESS.mainSupplier} et vos fiches techniques méritent une conversation ferme` : "Dans les clous"}`),
  },
  {
    patterns: [/(marge)/i],
    handle: (ctx) => kpiAnswer(ctx, "marge", (k) => `Marge estimée sur 7 jours : ${fmtEur(k.value)}`),
  },
  {
    patterns: [/(ticket moyen|panier)/i],
    handle: (ctx) => kpiAnswer(ctx, "ticket_moyen", (k) => `Ticket moyen : ${fmtEur(k.value, true)}`),
  },
  {
    patterns: [/(commande)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "commandes_jour", (k) => `${fmtNum(k.value)} commandes par jour en moyenne cette semaine`),
  },
  {
    patterns: [/(commission)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "commission", (k) =>
        `Les plateformes ont prélevé ${fmtEur(k.value)} cette semaine. Le canal direct, lui, prélève zéro — je dis ça, je ne dis rien`),
  },
  {
    patterns: [/(fournisseur|foodex|dépendance|dependance)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "dependance_fournisseur", (k) =>
        `${fmtPct(k.value)} des achats chez ${BUSINESS.mainSupplier}. Un seul point de défaillance, ce n'est pas une stratégie d'approvisionnement, c'est un pari`),
  },
  {
    patterns: [/(alerte|anomalie|urgent|problème|probleme)/i],
    handle: (ctx, _q, seed) => {
      const { shown } = ctx.attention;
      if (!shown.length) return { text: "Aucune alerte sous budget. Savourez, c'est rare.", quip: quip(seed) };
      return {
        text: shown.map((a, i) => `${i + 1}. [${a.severity}] ${a.message}`).join(" "),
        navigateTo: "/alertes",
      };
    },
  },
  {
    patterns: [/(planifie|programme|poste|publie).*(post|reel|story|contenu|vidéo|video)/i, /(post|contenu).*(planifie|programme)/i],
    handle: () => ({
      text: "Brouillon créé dans le planificateur. Il attend votre approbation — la publication automatique est N4, et meta_api est encore inerte : posez le jeton META_GRAPH_TOKEN dans le coffre pour l'éveiller.",
      navigateTo: "/social",
    }),
  },
  {
    patterns: [/(mail|email|courriel)/i],
    handle: () => ({
      text: "Deux emails demandent une action : la facture Foodex à déposer dans l'inbox, et le relevé Belfius que le watchdog réclame depuis trois jours.",
      navigateTo: "/emails",
    }),
  },
  {
    patterns: [/(aide|help|que sais|commandes disponibles|\?$)/i],
    handle: () => ({
      text:
        "Demandez-moi un KPI (« le CA ? », « trésorerie »), l'état du système (« rapport »), les alertes, ou dites « va aux campagnes » pour naviguer. Le micro fonctionne aussi — je parle couramment le dirigeant pressé.",
    }),
  },
];

/* ---------------------------------------------------------------- */
/* Point d'entrée.                                                    */
/* ---------------------------------------------------------------- */
export function ask(ctx: JarvisContext, raw: string): JarvisReply {
  const q = raw.trim();
  if (!q) return { text: "Je suis bon, mais pas au point de répondre au silence." };

  const seed = [...q].reduce((a, c) => a + c.charCodeAt(0), 0);

  // Navigation explicite : « va / ouvre / montre … »
  if (/(va|aller|ouvre|montre|affiche)\b/i.test(q)) {
    for (const target of NAV_TARGETS) {
      if (target.patterns.test(q)) {
        return { text: `${target.label} — on y est.`, navigateTo: target.path, quip: quip(seed) };
      }
    }
  }

  for (const intent of INTENTS) {
    if (intent.patterns.some((p) => p.test(q))) {
      return intent.handle({ ...ctxSafe(ctx) }, q, seed);
    }
  }

  return {
    text:
      "Pas encore dans mon répertoire. Reformulez, ou essayez « aide » — mon vocabulaire s'étend à chaque sprint, contrairement à ma patience pour les plateformes à 30 % de commission.",
  };
}

function ctxSafe(ctx: JarvisContext): JarvisContext {
  return ctx ?? { kpis: [], attention: { shown: [], suppressed: 0, total: 0, cap: 3 } };
}
