import { Card, SectionTitle } from "@/components/ui";
import { getTeam } from "@/lib/mock/data";
import { KAMEHA } from "@/lib/profile";

/**
 * Équipe — profil réel Kameha Poke. Les heures, rôles et volumes non
 * fournis sont affichés « inconnu » : donnée manquante = anomalie,
 * jamais un chiffre inventé.
 */
export default function EquipePage() {
  const team = getTeam();

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Effectif connu</div>
          <div className="mt-1 text-2xl font-semibold">
            {team.length}
            <span className="text-sm font-normal text-ink-3"> + « autres » (inconnu)</span>
          </div>
        </Card>
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Heures planifiées / semaine</div>
          <div className="mt-1 text-2xl font-semibold text-ink-3">inconnu</div>
          <div className="mt-1 text-[11px] text-ink-3">Aucun contrat horaire fourni au profil.</div>
        </Card>
        <Card className="!p-4">
          <div className="text-xs text-ink-3">Commandes / jour (historique mesuré)</div>
          <div className="mt-1 text-2xl font-semibold">≈15</div>
          <div className="mt-1 text-[11px] text-ink-3">3 970 commandes / 267 j — volume à staffer.</div>
        </Card>
      </div>

      <Card>
        <SectionTitle
          title="Personnes connues"
          sub={`${KAMEHA.name} — ${KAMEHA.legalName}. Le profil signale « autres : inconnu » : la liste est incomplète.`}
        />
        <ul className="space-y-3">
          {team.map((t) => (
            <li key={t.id} className="flex flex-col gap-1.5 rounded-xl border border-hairline bg-surface-2 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="text-sm font-medium text-ink">{t.name}</div>
                <div className="text-xs text-ink-3">
                  {t.role ?? "rôle : inconnu"}
                  {t.note && ` · ${t.note}`}
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs text-ink-3">
                <span>{t.hoursWeek !== null ? `${t.hoursWeek} h/sem.` : "heures : inconnues"}</span>
                <span>
                  {t.onShift === null ? "présence : inconnue" : t.onShift ? "en service" : "repos"}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <SectionTitle title="Ce que Jarvis attend pour activer ce module" />
        <ul className="grid grid-cols-1 gap-3 text-xs leading-relaxed text-ink-2 md:grid-cols-3">
          <li className="rounded-xl border border-hairline bg-surface-2 p-3">
            <span className="font-medium text-ink">La liste complète de l&apos;équipe</span> — le profil
            mentionne « autres : inconnu ». Prénoms, rôles, heures contractuelles.
          </li>
          <li className="rounded-xl border border-hairline bg-surface-2 p-3">
            <span className="font-medium text-ink">Les horaires d&apos;ouverture et jours de pic</span> —
            inconnus au profil. Sans eux, impossible de croiser staffing et volume (≈15 cmd/j mesuré).
          </li>
          <li className="rounded-xl border border-hairline bg-surface-2 p-3">
            <span className="font-medium text-ink">Le suivi Article 61</span> — le contrat CPAS de
            Sacha Debast a ses propres échéances administratives : dates à fournir pour les rappels.
          </li>
        </ul>
      </Card>
    </div>
  );
}
