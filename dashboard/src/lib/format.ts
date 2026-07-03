import { BUSINESS } from "./config";
import type { Confidence, Nature } from "./types";

const eur = new Intl.NumberFormat(BUSINESS.locale, {
  style: "currency",
  currency: BUSINESS.currency,
  maximumFractionDigits: 0,
});

const eurCents = new Intl.NumberFormat(BUSINESS.locale, {
  style: "currency",
  currency: BUSINESS.currency,
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const num = new Intl.NumberFormat(BUSINESS.locale, { maximumFractionDigits: 1 });

export function fmtEur(value: number | null, cents = false): string {
  if (value === null) return "—";
  return cents ? eurCents.format(value) : eur.format(value);
}

export function fmtNum(value: number | null): string {
  if (value === null) return "—";
  return num.format(value);
}

export function fmtPct(fraction: number | null, signed = false): string {
  if (fraction === null) return "—";
  const pct = fraction * 100;
  const sign = signed && pct > 0 ? "+" : "";
  return `${sign}${num.format(pct)} %`;
}

export function fmtCompact(value: number | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat(BUSINESS.locale, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

export function fmtDay(iso: string): string {
  return new Date(iso).toLocaleDateString(BUSINESS.locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(BUSINESS.locale, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export const NATURE_LABEL: Record<Nature, string> = {
  fait: "fait",
  estimation: "estimation",
  hypothèse: "hypothèse",
};

/** Libellé court d'une confiance : « fait · 96 % ». */
export function fmtConfidence(c: Confidence): string {
  return `${NATURE_LABEL[c.nature]} · ${Math.round(c.score * 100)} %`;
}
