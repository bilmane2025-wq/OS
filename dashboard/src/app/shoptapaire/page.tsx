import { Meter } from "@/components/charts/Meter";
import { Card, SectionTitle } from "@/components/ui";
import { fmtEur, fmtPct } from "@/lib/format";
import { SHOP_TA_PAIRE } from "@/lib/profile";

/**
 * Shop Ta Paire — seconde entité (side-venture sneakers, informel).
 * Patrimoine STRICTEMENT séparé de Kameha (règle sacrée du profil).
 * Chiffres : économie unitaire connue ; le reste vit dans l'Airtable
 * (base appRvWC0OPKv4LmH6) dont le connecteur n'est pas encore branché.
 */
export default function ShopTaPairePage() {
  const e = SHOP_TA_PAIRE.economics;
  const margePct = e.margeUnitaire / e.venteMoyenne; // 48 %
  const stockCost = e.stockConnu * e.achatMoyen;
  const stockPotential = e.stockConnu * e.venteMoyenne;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 rounded-2xl border border-jarvis/30 bg-jarvis/10 px-4 py-3 text-sm text-ink-2">
        <span aria-hidden>◈</span>
        <p>
          <strong className="text-ink">Entité séparée.</strong> Shop Ta Paire ne se mélange jamais
          avec Kameha Poke — comptes, trésorerie et marges distincts (séparation des patrimoines :
          sacrée). Équipe : {SHOP_TA_PAIRE.team.join(", ")}.
        </p>
      </div>

      {/* Économie unitaire connue */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Stock connu</div>
          <div className="mt-1 text-2xl font-semibold">≈{e.stockConnu} paires</div>
          <div className="mt-1 text-[11px] text-ink-3">{e.stockMarques}</div>
        </Card>
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Achat moyen → vente moyenne</div>
          <div className="mt-1 text-2xl font-semibold">
            {fmtEur(e.achatMoyen)} <span className="text-sm text-ink-3">→</span> {fmtEur(e.venteMoyenne)}
          </div>
        </Card>
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Marge unitaire</div>
          <div className="mt-1 text-2xl font-semibold">{fmtEur(e.margeUnitaire)}</div>
          <div className="mt-1 text-[11px] text-ink-3">{fmtPct(margePct)} du prix de vente</div>
        </Card>
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Valeur du stock (si tout part)</div>
          <div className="mt-1 text-2xl font-semibold">{fmtEur(stockPotential)}</div>
          <div className="mt-1 text-[11px] text-ink-3">
            coût immobilisé {fmtEur(stockCost)} · marge potentielle {fmtEur(stockPotential - stockCost)}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <SectionTitle
            title="KPI attendus"
            sub="Définis au profil — calculés dès que l'Airtable est branchée."
          />
          <ul className="space-y-3">
            {SHOP_TA_PAIRE.kpis.map((k) => (
              <li key={k} className="flex items-center justify-between rounded-xl border border-hairline bg-surface-2 px-3.5 py-3 text-sm">
                <span className="capitalize text-ink">{k}</span>
                <span className="text-xs text-ink-3">en attente du connecteur</span>
              </li>
            ))}
          </ul>
          <div className="mt-4">
            <div className="mb-1.5 flex items-center justify-between text-xs text-ink-3">
              <span>Rotation du stock</span>
              <span>inconnue — jamais estimée sans données</span>
            </div>
            <Meter value={0} max={1} color="var(--series-5)" />
          </div>
        </Card>

        <Card>
          <SectionTitle
            title="Connecteur Airtable"
            sub="La vérité de cette entité vit déjà dans Airtable — il ne manque que la clé."
          />
          <div className="rounded-xl border border-hairline bg-surface-2 p-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium text-ink">Base {SHOP_TA_PAIRE.airtable.baseId}</span>
              <span className="rounded-full border border-hairline px-2 py-0.5 text-[10px] text-ink-3">
                inerte
              </span>
            </div>
            <ul className="mt-3 grid grid-cols-2 gap-2 text-xs text-ink-2">
              {SHOP_TA_PAIRE.airtable.tables.map((t) => (
                <li key={t} className="rounded-lg border border-hairline bg-surface-1 px-2.5 py-1.5">
                  {t}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-ink-3">
              Posez <code className="rounded bg-surface-1 px-1">AIRTABLE_PAT</code> dans le coffre :
              stock, précommandes, arrivages et commandes remonteront ici en lecture seule (N1) —
              l&apos;écriture restera dans Airtable.
            </p>
          </div>
          <p className="mt-4 text-xs leading-relaxed text-ink-3">
            Inconnues au profil : banque dédiée et canaux de vente. Tant que rien n&apos;est fourni,
            Jarvis n&apos;affiche ni CA ni trésorerie pour cette entité.
          </p>
        </Card>
      </div>
    </div>
  );
}
