import { NextResponse } from "next/server";
import { getAttention } from "@/lib/mock/data";

/**
 * GET /api/attention — sollicitations sous budget d'attention (M27).
 * Branchement production : anomalies ouvertes + alertes de seuil de l'OS.
 */
export async function GET() {
  return NextResponse.json({ attention: getAttention(), source: "simulation" });
}
