/**
 * Couche de données RÉELLE — parse les six exports déposés (caisse, Fintro,
 * Revolut, TPE) et calcule les métriques mesurées. Serveur uniquement.
 *
 * Chaque chiffre sorti d'ici est un FAIT (lu dans un export) ou porte
 * explicitement son statut (règlement partiel, solde manquant). Les
 * inconnues restent null.
 */
import { num, readExport } from "./csv";

/* ------------------------------------------------------------------ */
/* Journal de caisse quotidien (saisie manuelle Tkw/Rev/Cash/Total/Fdc) */
/* ------------------------------------------------------------------ */
export interface CaisseDay {
  date: string;
  jour: string;
  tkw: number; // Takeaway.com
  carte: number; // TPE (colonne « Rev »)
  cash: number;
  total: number;
  fdc: number | null; // signification non confirmée — jamais devinée
}

export function getCaisseDays(): CaisseDay[] {
  return readExport("journal_caisse_quotidien.csv")
    .map((r) => ({
      date: r["Date"],
      jour: r["Jour"],
      tkw: num(r["Tkw"]) ?? 0,
      carte: num(r["Rev"]) ?? 0,
      cash: num(r["Cash"]) ?? 0,
      total: num(r["Total"]) ?? 0,
      fdc: num(r["Fdc"]),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

/* ------------------------------------------------------------------ */
/* Règlements TPE quotidiens (merchant_card_settlements_daily)          */
/* ------------------------------------------------------------------ */
export function getSettlementsByDay(): Map<string, { amount: number; count: number }> {
  const map = new Map<string, { amount: number; count: number }>();
  for (const r of readExport("merchant_card_settlements_daily.csv")) {
    map.set(r["Date"], {
      amount: num(r["Montant_total_EUR"]) ?? 0,
      count: num(r["Nb_transactions"]) ?? 0,
    });
  }
  return map;
}

/* ------------------------------------------------------------------ */
/* Rapprochement caisse (carte) ↔ TPE — le contrôle clé de l'OS.        */
/* ------------------------------------------------------------------ */
export interface ReconRow {
  date: string;
  carteSaisie: number;
  tpeRegle: number | null;
  ecart: number | null; // saisie − TPE ; null si TPE inconnu
  /** Dernier jour du fichier TPE : règlement possiblement incomplet. */
  partial: boolean;
}

export function getReconciliation(): ReconRow[] {
  const settlements = getSettlementsByDay();
  const lastSettlementDay = [...settlements.keys()].sort().at(-1) ?? "";
  return getCaisseDays().map((d) => {
    const s = settlements.get(d.date);
    return {
      date: d.date,
      carteSaisie: d.carte,
      tpeRegle: s ? s.amount : null,
      ecart: s ? Math.round((d.carte - s.amount) * 100) / 100 : null,
      partial: d.date === lastSettlementDay,
    };
  });
}

/** Écarts ouverts (≥ 1 €, hors jour à règlement partiel). */
export function getOpenReconGaps(): ReconRow[] {
  return getReconciliation().filter(
    (r) => r.ecart !== null && Math.abs(r.ecart) >= 1 && !r.partial,
  );
}

/* ------------------------------------------------------------------ */
/* Soldes bancaires connus                                              */
/* ------------------------------------------------------------------ */
export interface Balances {
  revolut: { amount: number; asOf: string };
  tpe: { amount: number; asOf: string };
  fintro: null; // aucun solde dans les exports fournis — inconnu
  totalKnown: number;
}

export function getBalances(): Balances {
  // Revolut : le fichier est trié du plus récent au plus ancien —
  // la première ligne porte le solde courant du compte EUR Main.
  const rev = readExport("revolut_business_transactions_juin-juillet.csv");
  const latest = rev[0];
  const revolut = {
    amount: num(latest?.["Balance"]) ?? 0,
    asOf: latest?.["Date completed (UTC)"] || latest?.["Date started (UTC)"] || "",
  };
  // TPE : dernière ligne complétée du relevé marchand (déjà trié récent→ancien).
  const recon = readExport("merchant_reconciliation_raw.csv");
  const latestTpe = recon[0];
  const tpe = {
    amount: num(latestTpe?.["Balance"]) ?? 0,
    asOf: (latestTpe?.["Date & Time Completed (UTC)"] ?? "").slice(0, 10),
  };
  return {
    revolut,
    tpe,
    fintro: null,
    totalKnown: Math.round((revolut.amount + tpe.amount) * 100) / 100,
  };
}

/* ------------------------------------------------------------------ */
/* Frais TPE mesurés                                                    */
/* ------------------------------------------------------------------ */
export function getTpeFees(): { gross: number; fees: number; rate: number; days: number } {
  let gross = 0;
  let fees = 0;
  for (const r of readExport("merchant_reconciliation_raw.csv")) {
    if (r["State"] === "COMPLETED" && r["Type"] === "Settlement") {
      gross += num(r["Original amount"]) ?? 0;
      fees += Math.abs(num(r["Processing fee"]) ?? 0);
    }
  }
  const days = readExport("merchant_card_settlements_daily.csv").length;
  return {
    gross: Math.round(gross * 100) / 100,
    fees: Math.round(fees * 100) / 100,
    rate: gross ? fees / gross : 0,
    days,
  };
}

/* ------------------------------------------------------------------ */
/* Fintro juin : virements Takeaway (nets) + charges récurrentes.       */
/* ------------------------------------------------------------------ */
export interface TakeawayPayout {
  date: string;
  amount: number;
  reference: string;
}

export function getTakeawayPayouts(): TakeawayPayout[] {
  return readExport("fintro_extrait_juin2026_detail.csv")
    .filter((r) => r["Contrepartie"] === "TAKEAWAY.COM BE" && r["Sens"] === "Credit")
    .map((r) => ({
      date: r["Date"],
      amount: num(r["Montant"]) ?? 0,
      reference: r["Description"],
    }));
}

export interface ChargeLine {
  label: string;
  amount: number;
  detail: string;
}

/** Charges de juin mesurées sur l'extrait Fintro (regroupées). */
export function getChargesJuin(): ChargeLine[] {
  const rows = readExport("fintro_extrait_juin2026_detail.csv").filter(
    (r) => r["Sens"] === "Debit",
  );
  const groups: Array<{ label: string; match: (c: string, d: string) => boolean; detail: string }> = [
    { label: "Loyers (local + bubble)", match: (_c, d) => /LOYER/i.test(d), detail: "850 € + 525 €" },
    { label: "Carburant (FleetCor)", match: (c) => /fleetcor/i.test(c), detail: "domiciliations B2B" },
    { label: "Énergie (ENGIE + TotalEnergies)", match: (c) => /engie|totalenergies/i.test(c), detail: "élec + gaz" },
    { label: "Télécom (Proximus)", match: (c) => /proximus/i.test(c), detail: "facture mensuelle" },
    { label: "Déchets (Renewi)", match: (c) => /renewi/i.test(c), detail: "collecte horeca" },
    { label: "Assurance auto (Yuzzu)", match: (c) => /yuzzu/i.test(c), detail: "contrat 35434225" },
    { label: "Abonnements (Jims ×2)", match: (c) => /jims/i.test(c), detail: "2 × 44,99 € — doublon à vérifier" },
  ];
  return groups
    .map((g) => {
      const total = rows
        .filter((r) => g.match(r["Contrepartie"], r["Description"]))
        .reduce((a, r) => a + (num(r["Montant"]) ?? 0), 0);
      return { label: g.label, amount: Math.round(total * 100) / 100, detail: g.detail };
    })
    .filter((g) => g.amount > 0)
    .sort((a, b) => b.amount - a.amount);
}

/* ------------------------------------------------------------------ */
/* Fournisseurs payés par carte Revolut (juin → 6 juillet).             */
/* ------------------------------------------------------------------ */
export function getSupplierCardSpend(): Array<{ name: string; amount: number }> {
  const byName = new Map<string, number>();
  for (const r of readExport("revolut_business_transactions_juin-juillet.csv")) {
    if (r["Type"] !== "CARD_PAYMENT" || r["State"] !== "COMPLETED") continue;
    // Normalisation légère : « Oz Food Sa » et « Ozfood Sa » = même maison.
    const name = r["Description"].trim().replace(/^Oz\s?food.*/i, "OzFood");
    const amount = Math.abs(num(r["Total amount"]) ?? num(r["Amount"]) ?? 0);
    byName.set(name, (byName.get(name) ?? 0) + amount);
  }
  return [...byName.entries()]
    .map(([name, amount]) => ({ name, amount: Math.round(amount * 100) / 100 }))
    .sort((a, b) => b.amount - a.amount);
}

/* ------------------------------------------------------------------ */
/* Mouvements notables Revolut (avances, remboursements associés).      */
/* ------------------------------------------------------------------ */
export function getNotableTransfers(): Array<{ date: string; label: string; amount: number }> {
  return readExport("revolut_business_transactions_juin-juillet.csv")
    .filter(
      (r) =>
        r["Type"] === "TRANSFER" &&
        r["State"] === "COMPLETED" &&
        /avance|salaire|accompte|acompte/i.test(r["Reference"] ?? ""),
    )
    .map((r) => ({
      date: r["Date completed (UTC)"] || r["Date started (UTC)"],
      label: `${r["Description"]} — ${r["Reference"]}`,
      amount: num(r["Total amount"]) ?? 0,
    }));
}
