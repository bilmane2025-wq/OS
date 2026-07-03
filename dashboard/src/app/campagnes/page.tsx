import { Meter } from "@/components/charts/Meter";
import { Card, SectionTitle } from "@/components/ui";
import { fmtEur } from "@/lib/format";
import { getCampaigns } from "@/lib/mock/data";
import type { Campaign } from "@/lib/types";

const STATUS_STYLE: Record<Campaign["status"], { label: string; cls: string }> = {
  active: { label: "active", cls: "border-good/40 text-good" },
  "en pause": { label: "en pause", cls: "border-warning/40 text-warning" },
  terminée: { label: "terminée", cls: "border-hairline text-ink-3" },
};

/** Campagnes marketing — budget, dépense, ROAS, coût par commande. */
export default function CampagnesPage() {
  const campaigns = getCampaigns();
  const active = campaigns.filter((c) => c.status !== "terminée");
  const totalSpent = active.reduce((a, c) => a + c.spent, 0);
  const totalRevenue = active.reduce((a, c) => a + c.revenueAttributed, 0);

  return (
    <div className="space-y-6">
      {/* Synthèse */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Dépense en cours</div>
          <div className="mt-1 text-2xl font-semibold">{fmtEur(totalSpent)}</div>
        </Card>
        <Card className="!p-4">
          <div className="text-xs text-ink-3">CA attribué</div>
          <div className="mt-1 text-2xl font-semibold">{fmtEur(totalRevenue)}</div>
        </Card>
        <Card className="!p-4">
          <div className="text-xs text-ink-3">ROAS global (campagnes en cours)</div>
          <div className="mt-1 text-2xl font-semibold">
            ×{(totalRevenue / (totalSpent || 1)).toFixed(1).replace(".", ",")}
          </div>
        </Card>
      </div>

      <Card>
        <SectionTitle
          title="Suivi des campagnes"
          sub="CA attribué : estimation par codes promo et fenêtres d'attribution — pas un fait comptable."
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-xs text-ink-3">
                <th className="pb-2 font-normal">Campagne</th>
                <th className="pb-2 font-normal">Statut</th>
                <th className="pb-2 pl-4 font-normal">Budget consommé</th>
                <th className="pb-2 text-right font-normal">CA attribué</th>
                <th className="pb-2 text-right font-normal">Commandes</th>
                <th className="pb-2 text-right font-normal">Coût / commande</th>
                <th className="pb-2 text-right font-normal">ROAS</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => {
                const status = STATUS_STYLE[c.status];
                const roas = c.revenueAttributed / (c.spent || 1);
                return (
                  <tr key={c.id} className="border-b border-hairline/50">
                    <td className="py-3">
                      <div className="font-medium text-ink">{c.name}</div>
                      <div className="text-[11px] text-ink-3">{c.channel}</div>
                    </td>
                    <td className="py-3">
                      <span className={`rounded-full border bg-surface-2 px-2.5 py-0.5 text-[10px] font-medium ${status.cls}`}>
                        {status.label}
                      </span>
                    </td>
                    <td className="py-3 pl-4">
                      <div className="flex items-center gap-2">
                        <div className="w-28">
                          <Meter
                            value={c.spent}
                            max={c.budget}
                            color={c.spent / c.budget > 0.9 ? "var(--status-serious)" : "var(--series-1)"}
                          />
                        </div>
                        <span className="tnum whitespace-nowrap text-xs text-ink-3">
                          {fmtEur(c.spent)} / {fmtEur(c.budget)}
                        </span>
                      </div>
                    </td>
                    <td className="tnum py-3 text-right">{fmtEur(c.revenueAttributed)}</td>
                    <td className="tnum py-3 text-right">{c.orders}</td>
                    <td className="tnum py-3 text-right">{fmtEur(c.spent / (c.orders || 1), true)}</td>
                    <td className={`tnum py-3 text-right font-medium ${roas >= 3 ? "text-good" : roas < 2 ? "text-serious" : ""}`}>
                      ×{roas.toFixed(1).replace(".", ",")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <SectionTitle title="Recommandations de Jarvis" />
        <ul className="grid grid-cols-1 gap-3 text-xs leading-relaxed text-ink-2 md:grid-cols-3">
          <li className="rounded-xl border border-hairline bg-surface-2 p-3">
            <span className="font-medium text-ink">« Menu été » tient un ROAS ×4,3</span> — le budget
            restant (163 €) sera consommé avant la fin : préparez la reconduction maintenant plutôt
            que de couper l&apos;élan.
          </li>
          <li className="rounded-xl border border-hairline bg-surface-2 p-3">
            <span className="font-medium text-ink">Boost Uber Eats sous la barre</span> — ROAS ×3,4
            mais coût/commande à 7,24 € sur un ticket moyen de ~25 € déjà grevé de 30 % de
            commission. La marge réelle par commande boostée est mince : à re-calculer avec le food
            cost avant de prolonger.
          </li>
          <li className="rounded-xl border border-hairline bg-surface-2 p-3">
            <span className="font-medium text-ink">Le précédent Ramadan a fait ×5,2</span> — les
            paniers famille sont votre meilleure campagne historique. Le même mécanique (offre
            groupée + WhatsApp) mérite un test estival.
          </li>
        </ul>
      </Card>
    </div>
  );
}
