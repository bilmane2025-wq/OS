import { Card, SectionTitle } from "@/components/ui";
import { fmtEur, fmtPct } from "@/lib/format";
import { KAMEHA } from "@/lib/profile";

/**
 * Campagnes — INCONNUES au profil (section 4 en attente). Aucune campagne
 * inventée : l'écran expose plutôt les opportunités calculées depuis les
 * données mesurées, prêtes à devenir des campagnes réelles.
 */
export default function CampagnesPage() {
  const h = KAMEHA.historique;
  const commissionRate = KAMEHA.takeawayCommissionRate;
  const takeawayShare = KAMEHA.channelSplit["Takeaway.com"];
  // Économie potentielle : chaque tranche de 10 % du CA Takeaway migrée
  // vers le site web économise la commission (~23,3 % estimé).
  const monthlyCa = (h.ca / h.days) * 30;
  const shiftSavings = monthlyCa * takeawayShare * 0.1 * commissionRate;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 rounded-2xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-ink-2">
        <span aria-hidden>◌</span>
        <p>
          <strong className="text-ink">Aucune campagne enregistrée</strong> — la section marketing du
          profil est <span className="text-warning">[EN ATTENTE]</span>. Rien n&apos;est inventé :
          dès qu&apos;une campagne existe (nom, canal, budget, période), elle se suit ici avec ROAS
          et coût/commande.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Dépense marketing connue</div>
          <div className="mt-1 text-2xl font-semibold text-ink-3">inconnu</div>
        </Card>
        <Card className="!p-4">
          <div className="text-xs text-ink-3">CA mensuel moyen (mesuré)</div>
          <div className="mt-1 text-2xl font-semibold">{fmtEur(monthlyCa)}</div>
        </Card>
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Clients récurrents (mesuré)</div>
          <div className="mt-1 text-2xl font-semibold">{fmtPct(h.recurrentsPct)}</div>
        </Card>
      </div>

      <Card>
        <SectionTitle
          title="Opportunités calculées — prêtes à devenir des campagnes"
          sub="Basées uniquement sur les chiffres mesurés du jumeau financier (267 jours)."
        />
        <ul className="grid grid-cols-1 gap-3 text-xs leading-relaxed text-ink-2 md:grid-cols-3">
          <li className="rounded-xl border border-hairline bg-surface-2 p-4">
            <div className="mb-1 text-sm font-medium text-ink">Migration Takeaway → site web</div>
            Takeaway.com pèse {fmtPct(takeawayShare)} du CA et prélève ≈{fmtPct(commissionRate)}.
            Déplacer 10 % de ce volume vers le site (déjà canal n°1) ={" "}
            <strong className="text-ink">≈{fmtEur(shiftSavings)}/mois</strong> de commission
            économisée. Mécanique : flyer + code promo « direct » dans chaque sac Takeaway.
          </li>
          <li className="rounded-xl border border-hairline bg-surface-2 p-4">
            <div className="mb-1 text-sm font-medium text-ink">Programme récurrents</div>
            {fmtPct(h.recurrentsPct)} des {h.clients.toLocaleString("fr-BE")} clients sont déjà
            récurrents (mesuré). Une carte de fidélité digitale sur le canal direct est la campagne
            au meilleur rapport coût/effet pour un ticket moyen de {fmtEur(h.ticketMoyen)}.
          </li>
          <li className="rounded-xl border border-hairline bg-surface-2 p-4">
            <div className="mb-1 text-sm font-medium text-ink">Ramadan (période connue)</div>
            Seule période commerciale identifiée au profil. Paniers famille + précommande sur le
            site web : à chiffrer dès que les données de la période équivalente sont dans le jumeau.
          </li>
        </ul>
      </Card>

      <Card>
        <SectionTitle title="Pour activer ce module" />
        <p className="text-sm leading-relaxed text-ink-2">
          Donnez à Jarvis : les campagnes passées ou en cours (canal, budget, période, résultat si
          connu), et l&apos;accès aux gestionnaires publicitaires le cas échéant. Le tracker
          calculera ROAS, coût/commande et — spécificité maison — la{" "}
          <strong className="text-ink">marge réelle par commande boostée</strong> : food cost 32 %
          mesuré + commission {fmtPct(commissionRate)} déduits, pas juste le CA brut.
        </p>
      </Card>
    </div>
  );
}
