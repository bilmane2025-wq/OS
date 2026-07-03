import { NextResponse } from "next/server";
import { getKpis } from "@/lib/mock/data";

/**
 * GET /api/kpi — les 8 KPI du MVP avec nature + confiance.
 *
 * Point de branchement production : remplacer getKpis() par une lecture
 * de la projection `kpi` de l'Enterprise OS (SQLite eos.db, table kpi),
 * ou par l'appel HTTP au serveur local de l'OS (/detail?kpi=…).
 * Le contrat de réponse ne change pas.
 */
export async function GET() {
  return NextResponse.json({ kpis: getKpis(), source: "simulation" });
}
