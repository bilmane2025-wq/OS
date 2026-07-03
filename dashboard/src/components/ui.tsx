import type { ReactNode } from "react";
import type { Confidence, Severity } from "@/lib/types";
import { fmtConfidence } from "@/lib/format";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-2xl border border-hairline bg-surface-1 p-5 ${className}`}>
      {children}
    </section>
  );
}

export function SectionTitle({
  title,
  sub,
  right,
}: {
  title: string;
  sub?: string;
  right?: ReactNode;
}) {
  return (
    <header className="mb-4 flex items-start justify-between gap-4">
      <div>
        <h2 className="text-sm font-semibold tracking-wide text-ink">{title}</h2>
        {sub && <p className="mt-0.5 text-xs text-ink-3">{sub}</p>}
      </div>
      {right}
    </header>
  );
}

/**
 * Badge de confiance — jamais une valeur nue : chaque chiffre porte sa
 * nature (fait / estimation / hypothèse) et son score.
 */
export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const tone =
    confidence.nature === "fait"
      ? "text-ink-2"
      : confidence.nature === "estimation"
        ? "text-warning"
        : "text-serious";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border border-hairline bg-surface-2 px-2 py-0.5 text-[10px] ${tone}`}
      title="Nature et score de confiance propagés depuis les événements sources"
    >
      {confidence.nature !== "fait" && <span aria-hidden>≈</span>}
      {fmtConfidence(confidence)}
    </span>
  );
}

const SEVERITY_STYLE: Record<Severity, { label: string; icon: string; cls: string }> = {
  haute: { label: "haute", icon: "▲", cls: "text-critical border-critical/40" },
  moyenne: { label: "moyenne", icon: "◆", cls: "text-serious border-serious/40" },
  douce: { label: "douce", icon: "●", cls: "text-warning border-warning/40" },
};

/** Pastille de gravité : icône + libellé, jamais la couleur seule. */
export function SeverityPill({ severity }: { severity: Severity }) {
  const s = SEVERITY_STYLE[severity];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border bg-surface-2 px-2 py-0.5 text-[10px] font-medium ${s.cls}`}>
      <span aria-hidden className="text-[8px]">{s.icon}</span>
      {s.label}
    </span>
  );
}

export function Legend({ items }: { items: Array<{ name: string; color: string }> }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
      {items.map((it) => (
        <span key={it.name} className="inline-flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-full" style={{ background: it.color }} />
          {it.name}
        </span>
      ))}
    </div>
  );
}

export function Delta({ value, goodWhenDown = false }: { value: number | null; goodWhenDown?: boolean }) {
  if (value === null) return null;
  const up = value > 0;
  const good = goodWhenDown ? !up : up;
  return (
    <span className={`inline-flex items-center gap-0.5 whitespace-nowrap text-xs font-medium ${good ? "text-good" : "text-critical"}`}>
      <span aria-hidden>{up ? "↑" : "↓"}</span>
      {`${Math.abs(value * 100).toFixed(1).replace(".", ",")} %`}
    </span>
  );
}
