"use client";

/**
 * Jauge-bande fine pour un ratio avec cible : la valeur est une barre à
 * bout arrondi, la cible un repère vertical. Le texte porte les chiffres —
 * la couleur ne signifie jamais seule (icône/étiquette à côté).
 */
export function Meter({
  value,
  target,
  max = 1,
  color = "var(--series-1)",
  targetLabel,
}: {
  value: number;
  target?: number;
  max?: number;
  color?: string;
  targetLabel?: string;
}) {
  const pct = Math.min(1, value / max) * 100;
  const tpct = target !== undefined ? Math.min(1, target / max) * 100 : null;
  return (
    <div className="relative h-2 w-full rounded-full bg-surface-3">
      <div
        className="absolute inset-y-0 left-0 rounded-full"
        style={{ width: `${pct}%`, background: color }}
      />
      {tpct !== null && (
        <div
          className="absolute -top-1 h-4 w-0.5 rounded bg-ink-2"
          style={{ left: `${tpct}%` }}
          title={targetLabel}
        />
      )}
    </div>
  );
}
