import { Card, SectionTitle, SeverityPill } from "@/components/ui";
import { fmtEur } from "@/lib/format";
import { getAlerts, getAttention, getSources } from "@/lib/mock/data";

/**
 * Insights & alertes — tout ce qui dépasse le budget d'attention reste
 * consultable ici : contenu, jamais perdu, jamais insistant.
 */
export default function AlertesPage() {
  const attention = getAttention();
  const all = getAlerts();
  const sources = getSources();
  const shownIds = new Set(attention.shown.map((a) => a.id));
  const contained = all.filter((a) => !shownIds.has(a.id));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-hairline bg-surface-1 px-5 py-4 text-sm">
        <span className="jarvis-pulse inline-block size-2.5 rounded-full bg-jarvis" aria-hidden />
        <p className="text-ink-2">
          <strong className="text-ink">{attention.total} sollicitations</strong> après déduplication ·{" "}
          {attention.shown.length} montrées (plafond {attention.cap}) · {attention.suppressed} contenues.
          L&apos;attention du dirigeant est une ressource finie — jamais optimisée pour l&apos;engagement.
        </p>
      </div>

      <Card>
        <SectionTitle
          title="Sous budget d'attention"
          sub="Chaque alerte est actionnable par construction : gravité, probabilité, impact, recommandation."
        />
        <ul className="space-y-3">
          {attention.shown.map((a) => (
            <li key={a.id} className="rounded-xl border border-hairline bg-surface-2 p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <SeverityPill severity={a.severity} />
                <span className="text-[11px] text-ink-3">{a.type}</span>
                {a.probability !== undefined && (
                  <span className="ml-auto text-[11px] text-ink-3">
                    probabilité {Math.round(a.probability * 100)} %
                    {a.impact !== undefined && ` · impact ~${fmtEur(a.impact)}`}
                  </span>
                )}
              </div>
              <p className="text-sm text-ink">{a.message}</p>
              <div className="mt-2.5 flex items-start gap-2 rounded-lg border border-jarvis/25 bg-jarvis/5 px-3 py-2">
                <span className="text-jarvis" aria-hidden>→</span>
                <p className="text-xs leading-relaxed text-ink-2">{a.recommendation}</p>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <SectionTitle
            title="Contenues (hors budget)"
            sub="Dédupliquées ou au-delà du plafond — comptées, consultables, silencieuses."
          />
          {contained.length === 0 ? (
            <p className="text-sm text-ink-3">Rien en réserve. Journée calme.</p>
          ) : (
            <ul className="space-y-2.5">
              {contained.map((a) => (
                <li key={a.id} className="flex items-start gap-3 rounded-xl border border-hairline bg-surface-2 px-3.5 py-3">
                  <SeverityPill severity={a.severity} />
                  <div className="min-w-0">
                    <p className="text-xs text-ink-2">{a.message}</p>
                    <p className="mt-0.5 text-[11px] text-ink-3">→ {a.recommendation}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <SectionTitle
            title="Fraîcheur des sources"
            sub="Le watchdog M33 réclame la donnée manquante — un KPI muet ne déclenche jamais de fausse alerte."
          />
          <ul className="space-y-2.5">
            {sources.map((s) => (
              <li key={s.sourceId} className="flex items-center gap-3 rounded-xl border border-hairline bg-surface-2 px-3.5 py-3 text-xs">
                <span
                  aria-hidden
                  className={`inline-block size-2 rounded-full ${
                    s.status === "fraîche" ? "bg-good" : s.status === "en retard" ? "bg-warning" : "bg-critical"
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium text-ink">{s.label}</div>
                  <div className="text-ink-3">attendue tous les {s.expectedEveryDays} j</div>
                </div>
                <span className={s.status === "fraîche" ? "text-good" : "text-warning"}>{s.status}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
