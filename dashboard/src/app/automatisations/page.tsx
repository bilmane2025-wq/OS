import { Card, SectionTitle } from "@/components/ui";
import { fmtTime } from "@/lib/format";
import { getAutomations, getIntegrations } from "@/lib/mock/data";
import type { Automation } from "@/lib/types";

const STATUS_STYLE: Record<Automation["status"], { label: string; icon: string; cls: string }> = {
  ok: { label: "opérationnelle", icon: "●", cls: "text-good" },
  attention: { label: "attention", icon: "◆", cls: "text-warning" },
  erreur: { label: "erreur", icon: "▲", cls: "text-critical" },
  inerte: { label: "inerte", icon: "○", cls: "text-ink-3" },
};

/**
 * Automatisations — chaque tâche porte son niveau d'autorité N0-N5.
 * N5 = humain exclusivement : plancher architectural, jamais contournable.
 */
export default function AutomatisationsPage() {
  const automations = getAutomations();
  const integrations = getIntegrations();

  return (
    <div className="space-y-6">
      <Card>
        <SectionTitle
          title="Tâches automatisées"
          sub="L'échelle N0-N5 borne ce que chaque automate a le droit de faire seul. Les transitions matérielles exigent N5 : vous."
        />
        <ul className="space-y-3">
          {automations.map((a) => {
            const s = STATUS_STYLE[a.status];
            return (
              <li key={a.id} className="flex flex-col gap-2 rounded-xl border border-hairline bg-surface-2 p-4 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-ink">{a.name}</span>
                    <span
                      className="rounded-full border border-hairline bg-surface-1 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-ink-2"
                      title="Niveau d'autorité requis (échelle N0-N5)"
                    >
                      N{a.authority}
                    </span>
                    {a.requiresHuman && (
                      <span className="rounded-full border border-jarvis/40 bg-jarvis/10 px-2 py-0.5 text-[10px] text-jarvis">
                        approbation humaine
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ink-3">{a.description}</p>
                </div>
                <div className="flex shrink-0 items-center gap-4 text-xs sm:flex-col sm:items-end sm:gap-1">
                  <span className={`inline-flex items-center gap-1.5 font-medium ${s.cls}`}>
                    <span aria-hidden className="text-[9px]">{s.icon}</span>
                    {s.label}
                  </span>
                  <span className="text-ink-3">
                    {a.lastRun
                      ? `dernier run ${fmtTime(a.lastRun)} · ${a.runsThisWeek} cette semaine`
                      : "jamais exécutée"}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      </Card>

      <Card>
        <SectionTitle
          title="Connecteurs"
          sub="Inertes par défaut (Constitution : zéro appel sortant sans clé). Posez la clé dans le coffre M30 pour éveiller chacun."
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {integrations.map((i) => (
            <div key={i.id} className="rounded-xl border border-hairline bg-surface-2 p-4">
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-sm font-medium text-ink">{i.label}</span>
                <span
                  className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                    i.enabled ? "border-good/40 text-good" : "border-hairline text-ink-3"
                  }`}
                >
                  {i.enabled ? "actif" : "inerte"}
                </span>
              </div>
              <p className="text-xs leading-relaxed text-ink-3">{i.note}</p>
              <code className="mt-2 inline-block rounded bg-surface-1 px-1.5 py-0.5 text-[10px] text-ink-2">
                {i.envKey}
              </code>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
