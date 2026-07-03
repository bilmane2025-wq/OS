import { Card, SectionTitle } from "@/components/ui";
import { fmtCompact, fmtPct } from "@/lib/format";
import { getIntegrations, getScheduledPosts, getSocialStats } from "@/lib/mock/data";
import type { ScheduledPost, SocialPlatform } from "@/lib/types";

const PLATFORM_COLOR: Record<SocialPlatform, string> = {
  Instagram: "var(--series-7)",
  Facebook: "var(--series-1)",
  TikTok: "var(--series-5)",
  "Google Business": "var(--series-3)",
};

const STATUS_STYLE: Record<ScheduledPost["status"], string> = {
  brouillon: "border-warning/40 text-warning",
  planifié: "border-jarvis/40 text-jarvis",
  publié: "border-good/40 text-good",
};

/** Social & contenu — analytics par plateforme + planificateur éditorial. */
export default function SocialPage() {
  const stats = getSocialStats();
  const posts = getScheduledPosts().sort(
    (a, b) => new Date(a.scheduledFor).getTime() - new Date(b.scheduledFor).getTime(),
  );
  const meta = getIntegrations().find((i) => i.id === "meta");

  return (
    <div className="space-y-6">
      {meta && !meta.enabled && (
        <div className="flex items-center gap-3 rounded-2xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-ink-2">
          <span aria-hidden>🔌</span>
          <p>
            <strong className="text-ink">meta_api inerte</strong> — analytics simulées et publication
            en mode brouillon. Posez <code className="rounded bg-surface-2 px-1">{meta.envKey}</code> pour
            activer la publication planifiée (autorité N4, approbation humaine conservée).
          </p>
        </div>
      )}

      {/* Tuiles par plateforme */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.platform} className="!p-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="inline-block size-2.5 rounded-full" style={{ background: PLATFORM_COLOR[s.platform] }} />
              <span className="text-sm font-medium">{s.platform}</span>
            </div>
            <dl className="space-y-1.5 text-xs">
              {s.followers > 0 && (
                <div className="flex justify-between">
                  <dt className="text-ink-3">Abonnés</dt>
                  <dd className="tnum">
                    {fmtCompact(s.followers)}
                    <span className={`ml-1.5 ${s.followersDelta >= 0.05 ? "text-good" : "text-ink-3"}`}>
                      {fmtPct(s.followersDelta, true)}
                    </span>
                  </dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-ink-3">Portée 7 j</dt>
                <dd className="tnum">{fmtCompact(s.reach7d)}</dd>
              </div>
              {s.engagementRate > 0 && (
                <div className="flex justify-between">
                  <dt className="text-ink-3">Engagement</dt>
                  <dd className="tnum">{fmtPct(s.engagementRate)}</dd>
                </div>
              )}
            </dl>
            <p className="mt-2.5 border-t border-hairline pt-2 text-[11px] leading-snug text-ink-3">
              {s.topPost}
            </p>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Planificateur */}
        <Card className="lg:col-span-2">
          <SectionTitle
            title="Planificateur de contenu"
            sub="Les brouillons attendent votre approbation — la publication automatique est une autorité N4."
          />
          <ul className="space-y-2.5">
            {posts.map((p) => (
              <li key={p.id} className="flex items-center gap-3 rounded-xl border border-hairline bg-surface-2 px-3.5 py-3">
                <span
                  aria-hidden
                  className="inline-block size-2.5 shrink-0 rounded-full"
                  style={{ background: PLATFORM_COLOR[p.platform] }}
                  title={p.platform}
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-ink">{p.title}</div>
                  <div className="text-[11px] text-ink-3">
                    {p.platform} · {p.mediaType} ·{" "}
                    {new Date(p.scheduledFor).toLocaleDateString("fr-BE", {
                      weekday: "long",
                      day: "numeric",
                      month: "long",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </div>
                </div>
                <span className={`shrink-0 rounded-full border bg-surface-1 px-2.5 py-0.5 text-[10px] font-medium ${STATUS_STYLE[p.status]}`}>
                  {p.status}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        {/* Conseil éditorial Jarvis */}
        <Card>
          <SectionTitle title="Lecture de Jarvis" sub="Proactivité niveau 2 : des recommandations, pas du bruit." />
          <ul className="space-y-3 text-xs leading-relaxed text-ink-2">
            <li className="rounded-xl border border-hairline bg-surface-2 p-3">
              <span className="font-medium text-ink">TikTok surperforme</span> — +11,2 % d&apos;abonnés en
              une semaine avec la vidéo « dressage du tajine ». Le format coulisses × 15 s est votre
              meilleur levier de portée gratuite : doublez la cadence.
            </li>
            <li className="rounded-xl border border-hairline bg-surface-2 p-3">
              <span className="font-medium text-ink">Vendredi = pic de commandes</span> — publiez le
              reel du plat de la semaine le jeudi 18 h pour capter la décision du lendemain.
            </li>
            <li className="rounded-xl border border-hairline bg-surface-2 p-3">
              <span className="font-medium text-ink">Deliveroo le confirme</span> : des photos de menu
              récentes convertissent 24 % mieux. Une séance photo alimente les quatre plateformes et
              la campagne « Menu été ».
            </li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
