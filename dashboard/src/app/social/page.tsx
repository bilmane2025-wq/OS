import { Card, SectionTitle } from "@/components/ui";
import type { SocialPlatform } from "@/lib/types";

const PLATFORMS: Array<{ name: SocialPlatform | "WhatsApp Business"; color: string }> = [
  { name: "Instagram", color: "var(--series-7)" },
  { name: "Facebook", color: "var(--series-1)" },
  { name: "TikTok", color: "var(--series-5)" },
  { name: "Google Business", color: "var(--series-3)" },
  { name: "WhatsApp Business", color: "var(--series-4)" },
];

/**
 * Social & contenu — section 4 du profil EN ATTENTE : handles inconnus.
 * Aucune statistique inventée ; l'écran affiche ce qu'il attend.
 * Seul actif réel : le Reels Tracker (3 reels seedés côté analyse).
 */
export default function SocialPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 rounded-2xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-ink-2">
        <span aria-hidden>◌</span>
        <p>
          <strong className="text-ink">Comptes sociaux : inconnus au profil.</strong> Aucun chiffre
          n&apos;est affiché tant que les @handles ne sont pas fournis — règle maison : jamais une
          valeur inventée. Statut de la section : <span className="text-warning">[EN ATTENTE]</span>
        </p>
      </div>

      <Card>
        <SectionTitle
          title="Plateformes à renseigner"
          sub="Donnez le @handle (ou « pas de compte ») pour chaque plateforme — l'écran s'activera à mesure."
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {PLATFORMS.map((p) => (
            <div key={p.name} className="rounded-xl border border-dashed border-hairline bg-surface-2 p-4">
              <div className="mb-2 flex items-center gap-2">
                <span className="inline-block size-2.5 rounded-full" style={{ background: p.color }} />
                <span className="text-sm font-medium">{p.name}</span>
              </div>
              <div className="text-xs text-ink-3">@handle : inconnu</div>
              <div className="mt-1 text-xs text-ink-3">qui publie : inconnu</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <SectionTitle
            title="Reels Tracker"
            sub="Le seul actif contenu déjà en place : 3 reels seedés côté analyse."
          />
          <p className="text-sm leading-relaxed text-ink-2">
            Le Reels Tracker suit la performance des formats vidéo. Dès que le compte Instagram est
            renseigné (et le jeton Meta posé dans le coffre), ses métriques — vues, rétention,
            conversions vers le site web — s&apos;afficheront ici, canal par canal.
          </p>
          <p className="mt-3 rounded-xl border border-hairline bg-surface-2 p-3 text-xs text-ink-3">
            Levier identifié : le site web est le canal n°1 (≈48 % du CA, 0 % de commission). Chaque
            contenu qui pousse vers la commande directe plutôt que Takeaway.com économise ≈23 % de
            commission — le social est ici un outil de marge, pas de vanité.
          </p>
        </Card>

        <Card>
          <SectionTitle title="Périodes commerciales" sub="Connues au profil — calendrier à compléter." />
          <ul className="space-y-2.5 text-sm text-ink-2">
            <li className="flex items-center gap-3 rounded-xl border border-hairline bg-surface-2 px-3.5 py-3">
              <span aria-hidden className="text-ink-3">◆</span>
              Ramadan — période commerciale majeure (dates 2027 à planifier à l&apos;avance).
            </li>
            <li className="flex items-center gap-3 rounded-xl border border-dashed border-hairline bg-surface-2 px-3.5 py-3 text-ink-3">
              <span aria-hidden>+</span>
              Autres périodes : « à compléter » au profil — fêtes locales Wavre, rentrée, été ?
            </li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
