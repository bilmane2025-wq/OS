import { Card, SectionTitle } from "@/components/ui";
import { fmtTime } from "@/lib/format";
import { getEmails, getIntegrations } from "@/lib/mock/data";
import type { EmailThread } from "@/lib/types";

const CATEGORY_STYLE: Record<EmailThread["category"], { label: string; color: string }> = {
  fournisseur: { label: "Fournisseur", color: "var(--series-5)" },
  plateforme: { label: "Plateforme", color: "var(--series-2)" },
  banque: { label: "Banque", color: "var(--series-1)" },
  client: { label: "Client", color: "var(--series-7)" },
  admin: { label: "Administratif", color: "var(--series-3)" },
};

/**
 * Emails — triage intelligent : chaque message porte l'action suggérée qui
 * alimente l'OS (dépôt inbox, import CSV, brouillon de réponse).
 */
export default function EmailsPage() {
  const emails = getEmails();
  const gmail = getIntegrations().find((i) => i.id === "gmail");
  const actionable = emails.filter((e) => e.needsAction);

  return (
    <div className="space-y-6">
      {gmail && !gmail.enabled && (
        <div className="flex items-center gap-3 rounded-2xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-ink-2">
          <span aria-hidden>🔌</span>
          <p>
            Connecteur <strong className="text-ink">Gmail inerte</strong> — les messages ci-dessous sont
            une simulation du triage. Posez <code className="rounded bg-surface-2 px-1">{gmail.envKey}</code> dans
            le coffre à secrets (M30) pour brancher la vraie boîte : même écran, vraies données.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <SectionTitle
            title="Boîte de réception triée"
            sub={`${actionable.length} messages demandent une action — le reste ne sollicite pas votre attention.`}
          />
          <ul className="divide-y divide-[var(--border)]">
            {emails.map((e) => {
              const cat = CATEGORY_STYLE[e.category];
              return (
                <li key={e.id} className="flex gap-3 py-3.5">
                  <span
                    aria-hidden
                    className="mt-1 inline-block size-2.5 shrink-0 rounded-full"
                    style={{ background: cat.color, opacity: e.unread ? 1 : 0.35 }}
                    title={cat.label}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className={`truncate text-sm ${e.unread ? "font-semibold text-ink" : "text-ink-2"}`}>
                        {e.from}
                      </span>
                      <span className="shrink-0 text-[11px] text-ink-3">{fmtTime(e.receivedAt)}</span>
                    </div>
                    <div className={`truncate text-sm ${e.unread ? "text-ink" : "text-ink-2"}`}>{e.subject}</div>
                    <div className="truncate text-xs text-ink-3">{e.snippet}</div>
                    {e.suggestedAction && (
                      <div className="mt-1.5 flex items-center gap-1.5 text-[11px]">
                        <span className="rounded-full border border-jarvis/40 bg-jarvis/10 px-2 py-0.5 text-jarvis">
                          Jarvis suggère
                        </span>
                        <span className="truncate text-ink-2">{e.suggestedAction}</span>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>

        <div className="space-y-6">
          <Card>
            <SectionTitle title="Règles de triage" sub="Chaque catégorie route vers le bon pipeline de l'OS." />
            <ul className="space-y-2.5 text-xs text-ink-2">
              {Object.entries(CATEGORY_STYLE).map(([key, cat]) => (
                <li key={key} className="flex items-center gap-2">
                  <span className="inline-block size-2.5 rounded-full" style={{ background: cat.color }} />
                  <span className="w-24 shrink-0 text-ink">{cat.label}</span>
                  <span className="text-ink-3">
                    {key === "fournisseur" && "PJ facture → parseur PDF → food cost"}
                    {key === "plateforme" && "CSV commandes → rapprochement ventes"}
                    {key === "banque" && "Relevé → trésorerie + réconciliation"}
                    {key === "client" && "Avis → brouillon de réponse Jarvis"}
                    {key === "admin" && "Échéances → rappels calendrier"}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <SectionTitle title="Brouillons en attente" sub="Rédigés par Jarvis, envoyés par vous — l'envoi reste N5." />
            <ul className="space-y-3 text-xs">
              <li className="rounded-xl border border-hairline bg-surface-2 p-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-ink">Relance Foodex — avoir 516,01 €</span>
                  <span className="rounded-full border border-jarvis/40 bg-jarvis/10 px-2 py-0.5 text-[10px] text-jarvis">RÉDIGÉ</span>
                </div>
                <p className="mt-1 italic text-ink-3">
                  « Bonjour, l&apos;avoir de 516,01 € (compte C64478) n&apos;apparaît toujours pas
                  sur nos relevés. Merci de confirmer sa date de crédit ou de nous transmettre la
                  note de crédit correspondante. »
                </p>
              </li>
              <li className="rounded-xl border border-hairline bg-surface-2 p-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-ink">Fintro — activation du flux CODA</span>
                  <span className="rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] text-warning">EN ATTENTE</span>
                </div>
                <p className="mt-1 italic text-ink-3">
                  « Bonjour M. Van Herle, le mandat CodaClean sur BE69 1431 3360 5578 est signé.
                  Pouvez-vous confirmer que le flux est actif ? Nous n&apos;avons encore rien
                  reçu. »
                </p>
              </li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
