import Link from "next/link";
import { KpiTile } from "@/components/KpiTile";
import { StackedBars } from "@/components/charts/StackedBars";
import { Card, Legend, SectionTitle, SeverityPill } from "@/components/ui";
import { BUSINESS } from "@/lib/config";
import { getAttention, getChannelDays, getKpis, getSources } from "@/lib/mock/data";

/**
 * Vue instantanée — la règle des 10 secondes : l'essentiel de
 * l'entreprise d'un seul regard, alertes sous budget d'attention.
 */
export default function InstantView() {
  const kpis = getKpis();
  const attention = getAttention();
  const days = getChannelDays(14);
  const sources = getSources();

  const kpiOrder = ["ca", "marge", "tresorerie", "food_cost", "ticket_moyen", "commandes_jour", "commission", "dependance_fournisseur"];
  const ordered = kpiOrder
    .map((k) => kpis.find((x) => x.key === k))
    .filter((k): k is NonNullable<typeof k> => Boolean(k));

  // Un canal = une série, couleur fixée à l'entité (jamais recyclée).
  const labels = [...new Set(days.map((d) => d.date))].sort();
  const dayLabel = (isoDay: string) =>
    new Date(isoDay).toLocaleDateString(BUSINESS.locale, { day: "numeric", month: "short" });
  const series = [
    { name: "Direct", color: "var(--series-1)" },
    { name: "Deliveroo", color: "var(--series-3)" },
    { name: "Uber Eats", color: "var(--series-2)" },
  ].map((s) => ({
    ...s,
    values: labels.map(
      (day) => days.find((d) => d.date === day && d.channel === s.name)?.revenue ?? 0,
    ),
  }));

  const lateSources = sources.filter((s) => s.status !== "fraîche");

  return (
    <div className="space-y-6">
      {/* Rangée héro : les 8 KPI du MVP, confiance visible sur chacun */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {ordered.map((kpi, i) => (
          <KpiTile
            key={kpi.key}
            kpi={kpi}
            accent={`var(--series-${(i % 8) + 1})`}
          />
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Revenus 14 jours par canal */}
        <Card className="lg:col-span-2">
          <SectionTitle
            title="Revenus par canal — 14 jours"
            sub="Empilement par canal de vente ; le direct ne paie pas de commission."
            right={
              <Legend
                items={[
                  { name: "Direct", color: "var(--series-1)" },
                  { name: "Deliveroo", color: "var(--series-3)" },
                  { name: "Uber Eats", color: "var(--series-2)" },
                ]}
              />
            }
          />
          <StackedBars
            labels={labels.map(dayLabel)}
            series={series}
            format="eur"
          />
        </Card>

        {/* Sollicitations sous budget d'attention */}
        <Card>
          <SectionTitle
            title="Sollicitations"
            sub={`Budget d'attention : ${attention.shown.length}/${attention.cap} montrées · ${attention.suppressed} contenues`}
            right={
              <Link href="/alertes" className="text-xs text-jarvis hover:underline">
                tout voir →
              </Link>
            }
          />
          <ul className="space-y-3">
            {attention.shown.map((a) => (
              <li key={a.id} className="rounded-xl border border-hairline bg-surface-2 p-3">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <SeverityPill severity={a.severity} />
                  <span className="truncate text-[10px] text-ink-3">{a.type}</span>
                </div>
                <p className="text-xs leading-relaxed text-ink-2">{a.message}</p>
                <p className="mt-1.5 text-[11px] text-ink-3">
                  <span className="text-jarvis">→</span> {a.recommendation}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {/* Fraîcheur des sources (watchdog) */}
      {lateSources.length > 0 && (
        <Card>
          <SectionTitle
            title="Watchdog des sources"
            sub="Une donnée manquante ne déclenche jamais une fausse alerte KPI — elle est réclamée ici."
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {lateSources.map((s) => (
              <div key={s.sourceId} className="flex items-center gap-3 rounded-xl border border-hairline bg-surface-2 p-3 text-xs">
                <span aria-hidden className="grid size-7 shrink-0 place-items-center rounded-full bg-warning/15 text-warning">
                  ⏱
                </span>
                <div className="min-w-0">
                  <div className="truncate font-medium text-ink">{s.label}</div>
                  <div className="text-ink-3">
                    attendue tous les {s.expectedEveryDays} j — statut : {s.status}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
