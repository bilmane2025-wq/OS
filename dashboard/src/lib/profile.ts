/**
 * Profil réel du groupe — extrait typé de src/data/business-profile.json.
 *
 * Règle absolue (Constitution) : rien n'est inventé. Chaque valeur porte
 * son origine : "mesuré" (jumeau kameha_os.db, 267 j), "estimé" (calculé
 * depuis l'historique, à confirmer) ou "inconnu" (affiché comme tel,
 * jamais remplacé par un zéro).
 */
import rawProfile from "@/data/business-profile.json";

export const PROFILE = rawProfile;

export const OWNER = {
  name: "Bilal Kaddouri",
  callMe: "Bilal",
};

/* ------------------------------------------------------------------ */
/* Kameha Poke — AYBI GROUP SRL (Wavre)                                 */
/* ------------------------------------------------------------------ */
export const KAMEHA = {
  id: "kameha",
  name: "Kameha Poke",
  legalName: "AYBI GROUP SRL",
  bce: "1028.675.991",
  city: "Wavre",
  cogerant: "Aymane Bonouh",

  /** Historique mesuré : fact_ledger_daily, 267 jours (02/10/25 → 28/06/26). */
  historique: {
    days: 267,
    ca: 178_987,
    beneficeEstime: 44_846,
    margeNettePct: 0.25,
    commandes: 3_970,
    clients: 1_081,
    recurrentsPct: 0.4,
    ticketMoyen: 45,
    commandesJour: 3_970 / 267, // ≈ 14,9
    foodCostPct: 0.32,
    ifoodSharePct: 0.48,
  },

  /** Répartition historique du CA par canal (mesurée). */
  channelSplit: {
    "Site web": 85_868 / 178_987, // ≈ 48 %
    "Takeaway.com": 77_807 / 178_987, // ≈ 43,5 %
    Comptoir: (178_987 - 85_868 - 77_807) / 178_987, // ≈ 8,5 %
  } as Record<string, number>,

  /** Commission Takeaway.com estimée : 18 119 € / 77 807 € brut. */
  takeawayCommissionRate: 18_119 / 77_807, // ≈ 23,3 % — à confirmer

  /** Journaux de caisse récents (saisis manuellement). */
  caisseRecente: [
    { date: "2026-06-29", total: 882.7, note: null },
    { date: "2026-06-30", total: 1_202.9, note: "1 198,90 calculé / 1 202,90 saisi — écart +4,00 € OUVERT" },
    { date: "2026-07-01", total: 1_028.38, note: null },
  ],

  /** Mix paiement mesuré sur 3 jours. */
  mixPaiement: { carte: 0.5, takeaway: 0.35, cash: 0.14 },

  /** Solde bancaire connu : Revolut seul — Fintro inconnu. */
  soldeRevolut: 9_169,

  fournisseurs: [
    { name: "iFood", role: "produits asiatiques", share: "≈48 % du food cost (mesuré)" },
    { name: "Foodex", role: "compte C64478 · commande avant 16 h pour J+1", share: "inconnu" },
    { name: "Seamar", role: "poisson (saumon/thon)", share: "inconnu" },
    { name: "Dirk Marchand", role: "fruits & légumes", share: "inconnu" },
  ],

  contacts: {
    takeaway: "Ruben Pécriaux",
    uberEats: "restaurants.belgium@uber.com · +32 2 808 66 28",
    deliveroo: "Samia Meddah",
    fintro: "Tom Van Herle",
    comptable: "Brahim (ClearFacts/Coda — accès en cours)",
    foodex: "commande@foodex.be",
    seamar: "order@seamar.be",
  },
};

/* ------------------------------------------------------------------ */
/* Shop Ta Paire — side-venture sneakers (informel)                     */
/* ------------------------------------------------------------------ */
export const SHOP_TA_PAIRE = {
  id: "shoptapaire",
  name: "Shop Ta Paire",
  activity: "Resale sneakers",
  team: ["Azedine (Az)", "Yaya", "Bilel", "Souly", "Bilal (Billy)"],
  economics: {
    achatMoyen: 26,
    venteMoyenne: 50,
    margeUnitaire: 24,
    stockConnu: 30,
    stockMarques: "Asics, Saucony, On Cloud",
  },
  airtable: {
    baseId: "appRvWC0OPKv4LmH6",
    tables: ["STOCK", "PRÉCOMMANDES", "ARRIVAGES", "COMMANDES"],
  },
  kpis: ["stock", "précommandes", "marge réalisée", "rotation"],
};
