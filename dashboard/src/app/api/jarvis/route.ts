import { NextResponse } from "next/server";
import { ask } from "@/lib/jarvis";
import { getAttention, getKpis } from "@/lib/mock/data";

/**
 * POST /api/jarvis — { question: string } → JarvisReply.
 *
 * Aujourd'hui : moteur d'intentions local (zéro appel externe).
 * Branchement production : déléguer à un LLM (API Claude) avec le même
 * contrat de réponse — le client ne voit aucune différence. La clé vit
 * dans le coffre à secrets, jamais dans le code.
 */
export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const question = typeof body?.question === "string" ? body.question : "";
  if (!question.trim()) {
    return NextResponse.json({ error: "question manquante" }, { status: 400 });
  }
  const reply = ask({ kpis: getKpis(), attention: getAttention() }, question);
  return NextResponse.json({ reply, engine: "intents-local" });
}
