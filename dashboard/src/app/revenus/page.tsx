import { LineChart } from "@/components/charts/LineChart";
import { Meter } from "@/components/charts/Meter";
import { Card, ConfidenceBadge, Legend, SectionTitle } from "@/components/ui";
import { BUSINESS } from "@/lib/config";
import { fmtEur, fmtNum, fmtPct } from "@/lib/format";
import { getChannelDays, getKpis } from "@/lib/mock/data";
import type { ChannelName } from "@/lib/types";

/** Revenus & ventes — CA, commandes, commissions, food cost par canal. */
export default function RevenusPage() {
  const days = getChannelDays();
  const kpis = getKpis();
  const kpi = (k: string) => kpis.find((x) => x.key === k);

  const labels = [...new Set(days.map((d) => d.date))].sort();
  const dayLabel = (isoDay: string) =>
    new Date(isoDay).toLocaleDateString(BUSINESS.locale, { day: "numeric", month: "short" });

  const channels: Array<{ name: ChannelName; color: string }> = [
    { name: "Carte (TPE)", color: "var(--series-1)" },
    { name: "Espèces", color: "var(--series-2)" },
    { name: "Takeaway.com", color: "var(--series-3)" },
  ];

  const revenueSeries = channels.map((c) => ({
    name: c.name,
    color: c.color,
    values: labels.map(
      (day) => days.find((d) => d.date === day && d.channel === c.name)?.revenue ?? 0,
    ),
  }));

  const treso = kpi("tresorerie");
  const foodCost = kpi("food_cost");
  const commission = kpi("commission");
  const ca = kpi("ca");

  // Répartition 7 derniers jours par canal
  const last7 = labels.slice(-7);
  const perChannel = channels.map((c) => {
    const rows = days.filter((d) => last7.includes(d.date) && d.channel === c.name);
    const revenue = rows.reduce((a, r) => a + r.revenue, 0);
    const orders = rows.reduce((a, r) => a + r.orders, 0);
    const comm = rows.reduce((a, r) => a + r.commission, 0);
    return { ...c, revenue, orders, commission: comm, net: revenue - comm };
  });
  const totalRevenue = perChannel.reduce((a, c) => a + c.revenue, 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <SectionTitle
            title="Revenus quotidiens par mode d'encaissement — réels"
            sub="Journal de caisse 28/06 → 05/07. Un mode = une couleur, fixée à l'entité."
            right={<Legend items={channels} />}
          />
          <LineChart
            labels={labels.map(dayLabel)}
            series={revenueSeries}
            format="eur"
          />
        </Card>

        <Card>
          <SectionTitle title="Trésorerie" sub={`Seuil d'alerte : ${fmtEur(BUSINESS.cashAlertThreshold)}`} />
          {treso && (
            <>
              <div className="mb-2 flex items-center gap-3">
                <span className="text-3xl font-semibold">{fmtEur(treso.value)}</span>
                <ConfidenceBadge confidence={treso.confidence} />
              </div>
              <LineChart
                labels={labels.map(dayLabel)}
                series={[{ name: "Trésorerie", color: "var(--series-1)", values: treso.history }]}
                format="eur"
                height={160}
                baseline={BUSINESS.cashAlertThreshold}
                baselineLabel="seuil"
              />
              <p className="mt-2 text-xs text-ink-3">
                Mesuré : Revolut 668,34 € (06/07) + solde TPE 281,16 €. Les deux comptes Fintro
                restent inconnus (CODA inactif) alors que ~15 000 € de crédits y sont entrés fin
                juin — position réelle à confirmer, pas à supposer.
              </p>
            </>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <SectionTitle
            title="Répartition par mode — 7 jours réels"
            sub="Le net déduit la commission Takeaway.com (≈23,3 % estimé). Frais TPE mesurés à part : 1,01 %."
          />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-xs text-ink-3">
                  <th className="pb-2 font-normal">Canal</th>
                  <th className="pb-2 text-right font-normal">CA</th>
                  <th className="pb-2 text-right font-normal">Commandes</th>
                  <th className="pb-2 text-right font-normal">Commission</th>
                  <th className="pb-2 text-right font-normal">Net</th>
                  <th className="pb-2 pl-4 font-normal">Part du CA</th>
                </tr>
              </thead>
              <tbody>
                {perChannel.map((c) => (
                  <tr key={c.name} className="border-b border-hairline/50">
                    <td className="py-2.5">
                      <span className="inline-flex items-center gap-2">
                        <span className="inline-block size-2.5 rounded-full" style={{ background: c.color }} />
                        {c.name}
                      </span>
                    </td>
                    <td className="tnum py-2.5 text-right">{fmtEur(c.revenue)}</td>
                    <td className="tnum py-2.5 text-right">{c.orders}</td>
                    <td className="tnum py-2.5 text-right text-ink-2">
                      {c.commission ? `− ${fmtEur(c.commission)}` : "0 €"}
                    </td>
                    <td className="tnum py-2.5 text-right font-medium">{fmtEur(c.net)}</td>
                    <td className="py-2.5 pl-4">
                      <div className="flex items-center gap-2">
                        <div className="w-24">
                          <Meter value={c.revenue} max={totalRevenue} color={c.color} />
                        </div>
                        <span className="tnum text-xs text-ink-3">
                          {fmtPct(c.revenue / totalRevenue)}
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <SectionTitle title="Coûts sous surveillance" />
          <div className="space-y-5">
            {foodCost && (
              <div>
                <div className="mb-1.5 flex items-center justify-between text-sm">
                  <span className="text-ink-2">Food cost</span>
                  <span className="flex items-center gap-2">
                    <span className="font-semibold">{fmtPct(foodCost.value)}</span>
                    <ConfidenceBadge confidence={foodCost.confidence} />
                  </span>
                </div>
                <Meter value={foodCost.value ?? 0} target={0.28} max={0.5} color="var(--series-3)" targetLabel="référence 28 %" />
                <p className="mt-1 text-[11px] text-ink-3">
                  32 % mesuré sur 267 j. Cible non définie au profil — 28 % = référence métier.
                </p>
              </div>
            )}
            {commission && ca && (
              <div>
                <div className="mb-1.5 flex items-center justify-between text-sm">
                  <span className="text-ink-2">Commissions / CA</span>
                  <span className="font-semibold">
                    {fmtPct((commission.value ?? 0) / (ca.value ?? 1))}
                  </span>
                </div>
                <Meter
                  value={(commission.value ?? 0) / (ca.value ?? 1)}
                  max={0.5}
                  color="var(--series-2)"
                />
                <p className="mt-1 text-[11px] text-ink-3">
                  {fmtEur(commission.value)} prélevés cette semaine par Takeaway.com (taux estimé, à
                  confirmer sur le prochain relevé).
                </p>
              </div>
            )}
            {(() => {
              const dep = kpi("dependance_fournisseur");
              return dep ? (
                <div>
                  <div className="mb-1.5 flex items-center justify-between text-sm">
                    <span className="text-ink-2">Dépendance {BUSINESS.mainSupplier}</span>
                    <span className="font-semibold">{fmtPct(dep.value)}</span>
                  </div>
                  <Meter value={dep.value ?? 0} target={0.4} max={1} color="var(--series-5)" targetLabel="cible < 40 %" />
                  <p className="mt-1 text-[11px] text-ink-3">
                    {fmtNum((dep.value ?? 0) * 100)} % des achats chez un seul fournisseur.
                  </p>
                </div>
              ) : null;
            })()}
          </div>
        </Card>
      </div>
    </div>
  );
}
