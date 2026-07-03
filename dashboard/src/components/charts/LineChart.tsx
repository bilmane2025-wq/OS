"use client";

import { useRef, useState } from "react";
import { formatBy, type ValueFormat } from "./StackedBars";

export interface LineSeries {
  name: string;
  color: string;
  values: number[];
}

/**
 * Courbes 2 px multi-séries : crosshair + tooltip au survol, marqueurs
 * cerclés surface au point actif, étiquettes directes en bout de ligne.
 */
export function LineChart({
  labels,
  series,
  height = 220,
  format = "eur",
  baseline,
  baselineLabel,
}: {
  labels: string[];
  series: LineSeries[];
  height?: number;
  format?: ValueFormat;
  /** Ligne de seuil horizontale facultative (ex. seuil trésorerie). */
  baseline?: number;
  baselineLabel?: string;
}) {
  const formatValue = (v: number) => formatBy(format, v);
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const width = 640;
  const padL = 8;
  // Une seule série : le titre la nomme, pas d'étiquette directe ni de
  // réserve à droite (règle : pas de légende pour une série unique).
  const showEndLabels = series.length > 1;
  const padR = showEndLabels ? 86 : 16;
  const padB = 22;
  const plotH = height - padB - 8;
  const n = labels.length;

  const all = series.flatMap((s) => s.values).concat(baseline !== undefined ? [baseline] : []);
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const x = (i: number) => padL + (i / (n - 1)) * (width - padL - padR);
  const y = (v: number) => 8 + (1 - (v - min) / span) * plotH;

  function onMove(e: React.MouseEvent) {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const fx = ((e.clientX - rect.left) / rect.width) * width;
    const i = Math.round(((fx - padL) / (width - padL - padR)) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, i)));
  }

  return (
    <div className="relative">
      <svg
        ref={ref}
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label={series.map((s) => s.name).join(", ")}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <line key={f} x1={padL} x2={width - padR} y1={8 + plotH * (1 - f)} y2={8 + plotH * (1 - f)} stroke="var(--grid)" strokeWidth={1} />
        ))}
        <line x1={padL} x2={width - padR} y1={8 + plotH} y2={8 + plotH} stroke="var(--baseline)" strokeWidth={1} />

        {baseline !== undefined && (
          <g>
            <line
              x1={padL}
              x2={width - padR}
              y1={y(baseline)}
              y2={y(baseline)}
              stroke="var(--status-critical)"
              strokeWidth={1}
              strokeDasharray="4 4"
            />
            {baselineLabel && (
              <text x={width - padR + 6} y={y(baseline) + 3} fontSize={10} fill="var(--status-critical)">
                {baselineLabel}
              </text>
            )}
          </g>
        )}

        {series.map((s) => {
          const d = s.values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
          const last = s.values[s.values.length - 1];
          return (
            <g key={s.name}>
              <path d={d} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {showEndLabels && (
                <text x={x(n - 1) + 8} y={y(last) + 3} fontSize={11} fill="var(--ink-secondary)">
                  {s.name}
                </text>
              )}
            </g>
          );
        })}

        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={8} y2={8 + plotH} stroke="var(--baseline)" strokeWidth={1} />
            {series.map((s) => (
              <circle
                key={s.name}
                cx={x(hover)}
                cy={y(s.values[hover])}
                r={4}
                fill={s.color}
                stroke="var(--surface-1)"
                strokeWidth={2}
              />
            ))}
          </g>
        )}

        {labels.map((label, i) =>
          i % Math.ceil(n / (height < 200 ? 4 : 7)) === 0 ? (
            <text key={label} x={x(i)} y={height - 6} textAnchor="middle" fontSize={10} fill="var(--ink-muted)">
              {label}
            </text>
          ) : null,
        )}
      </svg>

      {hover !== null && (
        <div
          className="pointer-events-none absolute top-0 z-10 rounded-lg border border-hairline bg-surface-3 px-3 py-2 text-xs shadow-xl"
          style={{
            left: `${(x(hover) / width) * 100}%`,
            transform: x(hover) > width / 2 ? "translateX(-108%)" : "translateX(10px)",
          }}
        >
          <div className="mb-1 font-medium text-ink">{labels[hover]}</div>
          {series.map((s) => (
            <div key={s.name} className="flex items-center gap-2 text-ink-2">
              <span className="inline-block size-2 rounded-full" style={{ background: s.color }} />
              <span className="flex-1">{s.name}</span>
              <span className="tnum ml-3">{formatValue(s.values[hover])}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
