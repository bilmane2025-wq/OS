import { NextResponse } from "next/server";
import {
  getBalances,
  getCaisseDays,
  getChargesJuin,
  getNotableTransfers,
  getReconciliation,
  getSupplierCardSpend,
  getTakeawayPayouts,
  getTpeFees,
} from "@/lib/real/finance";

/**
 * GET /api/finance — LE contrat de données pour le front (Claude Design).
 *
 * Tout est calculé depuis les exports réels de src/data/exports/ :
 * - caisse : 8 journaux quotidiens (Tkw / carte / cash / total / fdc)
 * - reconciliation : écarts caisse ↔ règlements TPE, jour par jour
 * - balances : soldes connus (Revolut, TPE) — fintro: null = inconnu
 * - tpeFees : frais TPE mesurés (taux effectif)
 * - takeawayPayouts : virements NETS reçus (extrait Fintro juin)
 * - chargesJuin : charges récurrentes regroupées (extrait Fintro)
 * - suppliersCard : dépenses fournisseurs par carte Revolut
 * - notableTransfers : avances/acomptes équipe repérés
 *
 * Pour rafraîchir : déposer les nouveaux exports dans src/data/exports/
 * (mêmes noms de fichiers) — aucun code à changer.
 */
export async function GET() {
  return NextResponse.json({
    asOf: "2026-07-06",
    caisse: getCaisseDays(),
    reconciliation: getReconciliation(),
    balances: getBalances(),
    tpeFees: getTpeFees(),
    takeawayPayouts: getTakeawayPayouts(),
    chargesJuin: getChargesJuin(),
    suppliersCard: getSupplierCardSpend(),
    notableTransfers: getNotableTransfers(),
    source: "exports-reels",
  });
}
