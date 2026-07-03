"use client";

import { useState } from "react";
import { fmtEur, fmtNum } from "@/lib/format";

export type ValueFormat = "eur" | "num";

export function formatBy(format: ValueFormat, v: number): string {
  return format === "eur" ? fmtEur(v) : fmtNum(v);
}

export interface StackedSeries {
  name: string;
  color: string; // var(--series-n)
  values: number[];
}

/**
 * Colonnes empilées : segments séparés par un espaceur de 2 px couleur
 * surface, extrémité haute arrondie 4 px, survol par colonne avec tooltip.
 */
export function StackedBars({
  labels,
  series,
  height = 200,
  format = "eur",
}: {
  labels: string[];
  series: StackedSeries[];
  height?: number;
  format?: ValueFormat;
}) {
  const formatValue = (v: number) => formatBy(format, v);
  const [hover, setHover] = useState<number | null>(null);
  const width = 640;
  const padL = 8;
  const padB = 22;
  const plotH = height - padB - 6;
  const n = labels.length;
  const totals = labels.map((_, i) => series.reduce((a, s) => a + s.values[i], 0));
  const maxTotal = Math.max(...totals) || 1;
  const slot = (width - padL * 2) / n;
  const barW = Math.min(28, slot * 0.58);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label="Revenus par canal et par jour"
        onMouseLeave={() => setHover(null)}
      >
        {/* grille hairline */}
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <line
            key={f}
            x1={padL}
            x2={width - padL}
            y1={6 + plotH * (1 - f)}
            y2={6 + plotH * (1 - f)}
            stroke="var(--grid)"
            strokeWidth={1}
          />
        ))}
        {labels.map((label, i) => {
          const x = padL + slot * i + (slot - barW) / 2;
          let yCursor = 6 + plotH;
          return (
            <g key={label}>
              {/* zone de survol plus large que la marque */}
              <rect
                x={padL + slot * i}
                y={0}
                width={slot}
                height={height - padB}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
              />
              {series.map((s, si) => {
                const h = (s.values[i] / maxTotal) * plotH;
                if (h <= 0) return null;
                yCursor -= h;
                const isTop = si === series.length - 1;
                const y = yCursor;
                return (
                  <rect
                    key={s.name}
                    x={x}
                    y={y + (isTop ? 0 : 1)}
                    width={barW}
                    height={Math.max(1, h - (isTop ? 0 : 2))}
                    rx={isTop ? 4 : 0}
                    fill={s.color}
                    opacity={hover === null || hover === i ? 1 : 0.45}
                    style={{ pointerEvents: "none" }}
                  />
                );
              })}
              <text
                x={padL + slot * i + slot / 2}
                y={height - 6}
                textAnchor="middle"
                fontSize={10}
                fill="var(--ink-muted)"
              >
                {label}
              </text>
            </g>
          );
        })}
        <line x1={padL} x2={width - padL} y1={6 + plotH} y2={6 + plotH} stroke="var(--baseline)" strokeWidth={1} />
      </svg>

      {hover !== null && (
        <div
          className="pointer-events-none absolute top-0 z-10 rounded-lg border border-hairline bg-surface-3 px-3 py-2 text-xs shadow-xl"
          style={{ left: `${(hover / n) * 100}%`, transform: hover > n / 2 ? "translateX(-105%)" : "translateX(8%)" }}
        >
          <div className="mb-1 font-medium text-ink">{labels[hover]}</div>
          {series
            .slice()
            .reverse()
            .map((s) => (
              <div key={s.name} className="flex items-center gap-2 text-ink-2">
                <span className="inline-block size-2 rounded-full" style={{ background: s.color }} />
                <span className="flex-1">{s.name}</span>
                <span className="tnum ml-3">{formatValue(s.values[hover])}</span>
              </div>
            ))}
          <div className="mt-1 border-t border-hairline pt-1 text-ink">
            Total <span className="tnum float-right ml-3">{formatValue(totals[hover])}</span>
          </div>
        </div>
      )}
    </div>
  );
}
