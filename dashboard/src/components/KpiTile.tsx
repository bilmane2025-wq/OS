"use client";

import { Sparkline } from "./charts/Sparkline";
import { ConfidenceBadge, Delta } from "./ui";
import { fmtEur, fmtNum, fmtPct } from "@/lib/format";
import type { Kpi } from "@/lib/types";

function display(kpi: Kpi): string {
  if (kpi.value === null) return "—";
  switch (kpi.unit) {
    case "EUR":
      return kpi.key === "ticket_moyen" ? fmtEur(kpi.value, true) : fmtEur(kpi.value);
    case "ratio":
      return fmtPct(kpi.value);
    case "commandes/jour":
      return fmtNum(kpi.value);
    default:
      return fmtNum(kpi.value);
  }
}

/** Les ratios de coût baissent = bien (food cost, dépendance). */
const GOOD_WHEN_DOWN = new Set(["food_cost", "dependance_fournisseur", "commission"]);

export function KpiTile({ kpi, accent = "var(--series-1)" }: { kpi: Kpi; accent?: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-hairline bg-surface-1 p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs text-ink-3">{kpi.label}</span>
        <ConfidenceBadge confidence={kpi.confidence} />
      </div>
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-2xl font-semibold leading-tight text-ink">{display(kpi)}</div>
          <div className="mt-1 flex items-center gap-2">
            <Delta value={kpi.delta} goodWhenDown={GOOD_WHEN_DOWN.has(kpi.key)} />
            <span className="text-[10px] text-ink-3">vs 7 j précédents</span>
          </div>
        </div>
        <Sparkline data={kpi.history} color={accent} />
      </div>
    </div>
  );
}
