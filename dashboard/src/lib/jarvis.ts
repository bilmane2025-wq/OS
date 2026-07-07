/**
 * Moteur Jarvis — compréhension d'intention (FR) + personnalité.
 *
 * Ton (profil Bilal) : direct, sans politesse excessive, labels d'état
 * [RÉDIGÉ / ENVOYÉ / CONFIRMÉ / EN ATTENTE]. Règles : jamais inventer un
 * chiffre, donnée manquante = anomalie, distinguer mesuré/estimé/hypothèse.
 *
 * Tourne côté client sur l'instantané de données (zéro appel externe).
 * Le branchement d'un vrai LLM se fait dans app/api/jarvis/route.ts.
 */
import { BUSINESS } from "./config";
import { fmtConfidence, fmtEur, fmtNum, fmtPct } from "./format";
import { OWNER, SHOP_TA_PAIRE } from "./profile";
import type { AttentionBudget, JarvisReply, Kpi } from "./types";

export interface JarvisContext {
  kpis: Kpi[];
  attention: AttentionBudget;
}

/* ---------------------------------------------------------------- */
/* Personnalité : efficace d'abord, pique sèche ensuite.              */
/* ---------------------------------------------------------------- */
const QUIPS = [
  "Pendant ce temps, l'avoir Foodex de 516,01 € prend l'humidité. Je dis ça.",
  "Je ne dors jamais. Le flux CODA Fintro non plus — lui, il n'a jamais commencé.",
  "Aucun chiffre inventé dans cette réponse. Politique de la maison.",
  "Takeaway prend ≈23 %. Le site web prend 0 %. Faites le calcul, moi je l'ai déjà fait.",
];

function quip(seed: number): string | undefined {
  return seed % 3 === 0 ? QUIPS[seed % QUIPS.length] : undefined;
}

const GREETINGS = [
  `${OWNER.callMe}. Les exports sont parsés : caisse, Fintro, Revolut, TPE. 3 alertes hautes. On commence par laquelle ?`,
  `Présent. ${BUSINESS.name} sous surveillance — caisse rapprochée du TPE, litiges, soldes. Question ?`,
  "Oui ? J'écoutais déjà.",
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
      text: "Pas de donnée fiable sur ce point — et je ne vais pas l'inventer. Donnée manquante = anomalie : la source est réclamée au watchdog.",
      navigateTo: "/alertes",
    };
  }
  return { text: `${phrase(k)} (${fmtConfidence(k.confidence)}).` };
}

const NAV_TARGETS: Array<{ patterns: RegExp; path: string; label: string }> = [
  { patterns: /instantan|accueil|home|vue.?10|cockpit/i, path: "/", label: "Vue instantanée" },
  { patterns: /revenu|vente|chiffre|commande|caisse/i, path: "/revenus", label: "Revenus & ventes" },
  { patterns: /mail|email|courriel|boite|boîte/i, path: "/emails", label: "Emails" },
  { patterns: /social|insta|tiktok|facebook|contenu|post/i, path: "/social", label: "Social & contenu" },
  { patterns: /campagne|marketing|pub|ads/i, path: "/campagnes", label: "Campagnes" },
  { patterns: /automat|tâche|tache|robot/i, path: "/automatisations", label: "Automatisations" },
  { patterns: /alerte|anomalie|insight|probl|litige/i, path: "/alertes", label: "Insights & alertes" },
  { patterns: /équipe|equipe|staff|personnel/i, path: "/equipe", label: "Équipe" },
  { patterns: /paire|sneaker|shop ta paire|stp/i, path: "/shoptapaire", label: "Shop Ta Paire" },
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
          `${total} sollicitation${total > 1 ? "s" : ""} après dédup, ${shown.length} montrée${shown.length > 1 ? "s" : ""} sous budget` +
          (suppressed ? ` (${suppressed} contenues, consultables)` : "") +
          `. La plus urgente : ${worst ? worst.message : "aucune"}`,
        navigateTo: "/alertes",
        quip: quip(seed),
      };
    },
  },
  {
    patterns: [/(caisse|journal de caisse|journaux|écart|ecart)/i],
    handle: () => ({
      text:
        "Dernier journal : 05/07, 1 201,03 €. Le rapprochement TPE a parlé : le 30/06, l'écart de +4 € est EXPLIQUÉ (le TPE a réglé 679,00 €, la saisie de 675,00 € est fausse) ; et le 28/06 cache un écart jamais vu de −32,80 € (390,80 € TPE vs 358,00 € saisis). Le 06/07 n'est pas encore saisi. [EN ATTENTE]",
      navigateTo: "/revenus",
    }),
  },
  {
    patterns: [/(charge|frais fixe|loyer|abonnement|carburant)/i],
    handle: () => ({
      text:
        "Charges de juin mesurées sur Fintro : carburant FleetCor 1 449,27 € (5 prélèvements — c'est le poste n°1, à challenger), loyers 1 375 €, énergie 528 €, Renewi 151,60 €, Proximus 116,54 €, Yuzzu 87,73 €, Jims 2 × 44,99 € le même jour — doublon possible, à vérifier.",
      navigateTo: "/alertes",
    }),
  },
  {
    patterns: [/(tpe|terminal|frais carte|sumup)/i],
    handle: () => ({
      text:
        "Frais TPE mesurés sur 36 jours : 207,32 € sur 20 461,12 € encaissés, soit 1,01 % effectif. Solde du compte marchand : 281,16 €. C'est propre — rien à renégocier en priorité.",
    }),
  },
  {
    patterns: [/(avance|salaire|acompte|accompte|gautier)/i],
    handle: () => ({
      text:
        "Mouvements équipe repérés sur Revolut le 06/07 : avance sur salaire de 150 € à Gautier B (à régulariser en paie), et 1 500 € de remboursements d'acompte vers Aymane. Tout est tracé.",
      navigateTo: "/equipe",
    }),
  },
  {
    patterns: [/(litige|foodex|avoir|dirk marchand)/i],
    handle: () => ({
      text:
        "Deux litiges fournisseurs ouverts : Foodex — avoir de 516,01 € non crédité (compte C64478), relance [RÉDIGÉ], envoi N5 : vous. " +
        "Dirk Marchand — surfacturation récurrente : contrôle ligne à ligne des 3 dernières factures recommandé avant paiement.",
      navigateTo: "/alertes",
    }),
  },
  {
    patterns: [/(assurance|prime|maxel|rc exploitation)/i],
    handle: () => ({
      text:
        "Prime RC Exploitation 163,71 € échue le 23/04, statut impayé à vérifier (courtier MAXEL, Yvan Krug). " +
        "C'est irréversible + matériel si la couverture saute : priorité haute. [EN ATTENTE]",
      navigateTo: "/alertes",
    }),
  },
  {
    patterns: [/(chiffre d.affaires|\bca\b|revenu)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "ca", (k) =>
        `CA 7 derniers jours : ${fmtEur(k.value, true)} — 100 % journal de caisse réel (29/06 → 05/07), soit ≈${fmtEur((k.value ?? 0) / 7)} par jour, au-dessus des 670 €/j de l'historique`),
  },
  {
    patterns: [/(trésorerie|tresorerie|cash\b|banque|solde|revolut|fintro)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "tresorerie", (k) =>
        `Trésorerie CONNUE : ${fmtEur(k.value, true)} — Revolut 668,34 € (06/07) + TPE 281,16 €. Sous le seuil provisoire de 2 000 €, MAIS les deux comptes Fintro sont inconnus alors que ~15 000 € y sont entrés fin juin. Priorité : récupérer ces deux soldes`),
  },
  {
    patterns: [/(food ?cost|coût matière|cout matiere)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "food_cost", (k) =>
        `Food cost mesuré sur l'historique : ${fmtPct(k.value)}. Cible non définie au profil — la référence métier est 28 %. iFood pèse ≈48 % de ce poste`),
  },
  {
    patterns: [/(marge|bénéfice|benefice)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "marge", (k) =>
        `Marge estimée sur 7 j : ${fmtEur(k.value)} — base 25 % de marge nette mesurée sur 267 jours (44 846 € de bénéfice / 178 987 € de CA)`),
  },
  {
    patterns: [/(ticket moyen|panier)/i],
    handle: (ctx) => kpiAnswer(ctx, "ticket_moyen", (k) => `Ticket moyen mesuré : ${fmtEur(k.value, true)}`),
  },
  {
    patterns: [/(commande)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "commandes_jour", (k) =>
        `${fmtNum(k.value)} commandes/jour cette semaine — l'historique mesuré est à ≈15/j (3 970 commandes sur 267 j, ~40 % de clients récurrents)`),
  },
  {
    patterns: [/(commission|takeaway)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "commission", (k) =>
        `Commission Takeaway.com sur 7 j : ${fmtEur(k.value)} — taux ≈23,3 % estimé sur l'historique, à confirmer sur le prochain relevé (contact : Ruben Pécriaux). Le site web, lui, prélève zéro`),
  },
  {
    patterns: [/(fournisseur|ifood|dépendance|dependance|seamar|oscar|colruyt|ozfood)/i],
    handle: (ctx) =>
      kpiAnswer(ctx, "dependance_fournisseur", (k) =>
        `${fmtPct(k.value)} du food cost chez iFood (historique). Côté carte Revolut sur 5 semaines : Oscar Drink 1 612 €, OzFood 1 183 €, Clavie 1 026 €, Cré Embal 821 €, Colruyt 752 €. Un second fournisseur asiatique reste la priorité`),
  },
  {
    patterns: [/(uber|deliveroo)/i],
    handle: () => ({
      text:
        "Uber Eats : onboarding bloqué depuis 3+ mois, possiblement suspendu — relance à faire au +32 2 808 66 28 avec le BCE 1028.675.991. [EN ATTENTE] " +
        "Deliveroo : statut inconnu, contact existant Samia Meddah.",
      navigateTo: "/alertes",
    }),
  },
  {
    patterns: [/(paire|sneaker|shop ta paire|\bstp\b|stock)/i],
    handle: () => {
      const e = SHOP_TA_PAIRE.economics;
      return {
        text:
          `Shop Ta Paire : ≈${e.stockConnu} paires en stock (${e.stockMarques}). ` +
          `Marge unitaire ${fmtEur(e.margeUnitaire)} (achat ${fmtEur(e.achatMoyen)} → vente ${fmtEur(e.venteMoyenne)}). ` +
          `Précommandes et rotation : dans l'Airtable, connecteur pas encore branché. Patrimoine séparé de Kameha — sacré.`,
        navigateTo: "/shoptapaire",
      };
    },
  },
  {
    patterns: [/(alerte|anomalie|urgent|problème|probleme)/i],
    handle: (ctx, _q, seed) => {
      const { shown } = ctx.attention;
      if (!shown.length) return { text: "Aucune alerte sous budget. Rare. Profitez.", quip: quip(seed) };
      return {
        text: shown.map((a, i) => `${i + 1}. [${a.severity}] ${a.message}`).join(" "),
        navigateTo: "/alertes",
      };
    },
  },
  {
    patterns: [/(mail|email|courriel)/i],
    handle: () => ({
      text:
        "Trois emails attendent une action : relance Foodex [RÉDIGÉ], confirmation du flux CODA Fintro [EN ATTENTE], et le relevé Takeaway à importer pour confirmer le taux de commission.",
      navigateTo: "/emails",
    }),
  },
  {
    patterns: [/(aide|help|que sais|commandes disponibles|\?$)/i],
    handle: () => ({
      text:
        "Demandez un KPI (« le CA ? », « trésorerie », « food cost »), l'état (« rapport »), « caisse », « litiges », « Shop Ta Paire », ou « va aux alertes » pour naviguer. Micro supporté.",
    }),
  },
];

/* ---------------------------------------------------------------- */
/* Point d'entrée.                                                    */
/* ---------------------------------------------------------------- */
export function ask(ctx: JarvisContext, raw: string): JarvisReply {
  const q = raw.trim();
  if (!q) return { text: "Le silence n'est pas une requête." };

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
      return intent.handle(ctxSafe(ctx), q, seed);
    }
  }

  return {
    text:
      "Pas dans mon répertoire. Reformulez ou tapez « aide ». Mon vocabulaire s'étend à chaque sprint — contrairement à la patience de Foodex sur les avoirs.",
  };
}

function ctxSafe(ctx: JarvisContext): JarvisContext {
  return ctx ?? { kpis: [], attention: { shown: [], suppressed: 0, total: 0, cap: 3 } };
}
