import { Meter } from "@/components/charts/Meter";
import { Card, SectionTitle } from "@/components/ui";
import { fmtNum } from "@/lib/format";
import { getTeam } from "@/lib/mock/data";

/** Équipe — présence, volume traité, productivité par personne. */
export default function EquipePage() {
  const team = getTeam();
  const onShift = team.filter((t) => t.onShift);
  const maxOrders = Math.max(...team.map((t) => t.ordersHandled));
  const totalHours = team.reduce((a, t) => a + t.hoursWeek, 0);
  const totalOrders = team.reduce((a, t) => a + t.ordersHandled, 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card className="!p-4">
          <div className="text-xs text-ink-3">En service maintenant</div>
          <div className="mt-1 text-2xl font-semibold">
            {onShift.length}
            <span className="text-sm font-normal text-ink-3"> / {team.length}</span>
          </div>
          <div className="mt-1 text-xs text-ink-2">{onShift.map((t) => t.name).join(", ")}</div>
        </Card>
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Heures planifiées / semaine</div>
          <div className="mt-1 text-2xl font-semibold">{totalHours} h</div>
        </Card>
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Commandes / heure (équipe, 30 j)</div>
          <div className="mt-1 text-2xl font-semibold">{fmtNum(totalOrders / (totalHours * 4.3))}</div>
        </Card>
      </div>

      <Card>
        <SectionTitle
          title="Volume traité par personne — 30 jours"
          sub="Le volume dépend du poste : comparer un cuisinier à un packagiste n'a de sens qu'à rôle égal."
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-xs text-ink-3">
                <th className="pb-2 font-normal">Personne</th>
                <th className="pb-2 font-normal">Rôle</th>
                <th className="pb-2 text-right font-normal">h / sem.</th>
                <th className="pb-2 text-right font-normal">Commandes</th>
                <th className="pb-2 pl-4 font-normal">Volume relatif</th>
                <th className="pb-2 text-right font-normal">Statut</th>
              </tr>
            </thead>
            <tbody>
              {team.map((t) => (
                <tr key={t.id} className="border-b border-hairline/50">
                  <td className="py-3 font-medium text-ink">{t.name}</td>
                  <td className="py-3 text-ink-2">{t.role}</td>
                  <td className="tnum py-3 text-right">{t.hoursWeek} h</td>
                  <td className="tnum py-3 text-right">{t.ordersHandled}</td>
                  <td className="py-3 pl-4">
                    <div className="w-36">
                      <Meter value={t.ordersHandled} max={maxOrders} color="var(--series-1)" />
                    </div>
                  </td>
                  <td className="py-3 text-right">
                    <span
                      className={`inline-flex items-center gap-1.5 text-xs ${t.onShift ? "text-good" : "text-ink-3"}`}
                    >
                      <span aria-hidden className="inline-block size-1.5 rounded-full bg-current" />
                      {t.onShift ? "en service" : "repos"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <SectionTitle title="Signaux de Jarvis" />
        <ul className="grid grid-cols-1 gap-3 text-xs leading-relaxed text-ink-2 md:grid-cols-2">
          <li className="rounded-xl border border-hairline bg-surface-2 p-3">
            <span className="font-medium text-ink">Vendredi soir sous-staffé</span> — le pic fait
            +45 % de commandes mais l&apos;équipe planifiée est celle d&apos;un mardi. C&apos;est le
            créneau où la note « rapidité » des avis Google décroche.
          </li>
          <li className="rounded-xl border border-hairline bg-surface-2 p-3">
            <span className="font-medium text-ink">Yassine frôle les 42 h</span> — au-delà du
            contrat. Soit un avenant, soit une redistribution des shifts du week-end.
          </li>
        </ul>
      </Card>
    </div>
  );
}
