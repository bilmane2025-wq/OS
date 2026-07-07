/**
 * Mini-parseur CSV (serveur uniquement) — gère les champs entre guillemets
 * avec virgules internes (export Revolut/TPE). Zéro dépendance externe,
 * conforme à l'esprit stdlib de l'OS.
 */
import fs from "node:fs";
import path from "node:path";

export function parseCsv(content: string): Array<Record<string, string>> {
  const lines = content.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const split = (line: string): string[] => {
    const out: string[] = [];
    let cur = "";
    let quoted = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (quoted && line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          quoted = !quoted;
        }
      } else if (ch === "," && !quoted) {
        out.push(cur);
        cur = "";
      } else {
        cur += ch;
      }
    }
    out.push(cur);
    return out;
  };
  const cols = split(lines[0]);
  return lines.slice(1).map((line) => {
    const cells = split(line);
    return Object.fromEntries(cols.map((c, i) => [c, cells[i] ?? ""]));
  });
}

/** Lit un export déposé dans src/data/exports (équivalent de l'inbox OS). */
export function readExport(filename: string): Array<Record<string, string>> {
  const file = path.join(process.cwd(), "src", "data", "exports", filename);
  return parseCsv(fs.readFileSync(file, "utf8"));
}

/** Nombre depuis un champ export ("" → null, jamais un zéro inventé). */
export function num(value: string | undefined): number | null {
  if (value === undefined || value.trim() === "") return null;
  const n = parseFloat(value.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}
