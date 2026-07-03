"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { BUSINESS, JARVIS } from "@/lib/config";
import { ask, type JarvisContext } from "@/lib/jarvis";
import type { AttentionBudget, Kpi } from "@/lib/types";

/* ------------------------------------------------------------------ */
/* Navigation                                                           */
/* ------------------------------------------------------------------ */
const NAV = [
  { href: "/", label: "Vue instantanée", icon: "◉", hint: "l'essentiel en 10 s" },
  { href: "/revenus", label: "Revenus & ventes", icon: "€" },
  { href: "/emails", label: "Emails", icon: "✉" },
  { href: "/social", label: "Social & contenu", icon: "▶" },
  { href: "/campagnes", label: "Campagnes", icon: "◎" },
  { href: "/automatisations", label: "Automatisations", icon: "⚙" },
  { href: "/alertes", label: "Insights & alertes", icon: "!" },
  { href: "/equipe", label: "Équipe", icon: "☰" },
];

/* ------------------------------------------------------------------ */
/* Contexte Jarvis : l'instantané de données sert le moteur d'intention */
/* ------------------------------------------------------------------ */
const JarvisDataContext = createContext<JarvisContext>({
  kpis: [],
  attention: { shown: [], suppressed: 0, total: 0, cap: 3 },
});

interface ChatMessage {
  role: "user" | "jarvis";
  text: string;
  quip?: string;
}

/* Types minimaux Web Speech API (absents de lib.dom pour SpeechRecognition). */
interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start(): void;
  stop(): void;
}

function getSpeechRecognition(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as
    | (new () => SpeechRecognitionLike)
    | null;
}

function JarvisOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ctx = useContext(JarvisDataContext);
  const router = useRouter();
  const [input, setInput] = useState("");
  const [log, setLog] = useState<ChatMessage[]>([
    {
      role: "jarvis",
      text: `Jarvis en ligne. ${ctx.attention.total} sollicitation(s) sous surveillance. Posez votre question — clavier ou micro.`,
    },
  ]);
  const [listening, setListening] = useState(false);
  const [speak, setSpeak] = useState(JARVIS.speakByDefault);
  // Capacité navigateur : lue hors React (false côté serveur, stable côté client).
  const voiceSupported = useSyncExternalStore(
    () => () => {},
    () => getSpeechRecognition() !== null,
    () => false,
  );
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [log]);

  const submit = useCallback(
    (raw: string) => {
      const q = raw.trim();
      if (!q) return;
      const reply = ask(ctx, q);
      setLog((l) => [...l, { role: "user", text: q }, { role: "jarvis", text: reply.text, quip: reply.quip }]);
      setInput("");
      if (speak && typeof window !== "undefined" && "speechSynthesis" in window) {
        const utt = new SpeechSynthesisUtterance(reply.text);
        utt.lang = JARVIS.voiceLang;
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utt);
      }
      if (reply.navigateTo) {
        router.push(reply.navigateTo);
      }
    },
    [ctx, router, speak],
  );

  const toggleMic = useCallback(() => {
    if (listening) {
      recRef.current?.stop();
      setListening(false);
      return;
    }
    const Rec = getSpeechRecognition();
    if (!Rec) return;
    const rec = new Rec();
    rec.lang = JARVIS.voiceLang;
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      const transcript = e.results[0]?.[0]?.transcript ?? "";
      if (transcript) submit(transcript);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  }, [listening, submit]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-[12vh] backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal
      aria-label="Console Jarvis"
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-2xl border border-hairline bg-surface-1 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="jarvis-pulse inline-block size-2.5 rounded-full bg-jarvis" aria-hidden />
            <span className="text-sm font-semibold">Jarvis</span>
            <span className="text-xs text-ink-3">— commandes texte & voix</span>
          </div>
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-ink-3">
            <input
              type="checkbox"
              checked={speak}
              onChange={(e) => setSpeak(e.target.checked)}
              className="accent-[var(--jarvis)]"
            />
            réponse vocale
          </label>
        </div>

        <div ref={logRef} className="max-h-72 space-y-3 overflow-y-auto px-4 py-3 text-sm">
          {log.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : ""}>
              <span
                className={
                  m.role === "user"
                    ? "inline-block rounded-xl bg-surface-3 px-3 py-1.5 text-ink"
                    : "inline-block rounded-xl border border-hairline bg-surface-2 px-3 py-1.5 text-ink-2"
                }
              >
                {m.text}
              </span>
              {m.quip && <p className="mt-1 text-xs italic text-ink-3">{m.quip}</p>}
            </div>
          ))}
        </div>

        <form
          className="flex items-center gap-2 border-t border-hairline px-3 py-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit(input);
          }}
        >
          <button
            type="button"
            onClick={toggleMic}
            disabled={!voiceSupported}
            title={voiceSupported ? "Parler à Jarvis" : "Reconnaissance vocale non disponible dans ce navigateur"}
            aria-label="Activer le micro"
            className={`grid size-9 shrink-0 place-items-center rounded-full border border-hairline transition ${
              listening ? "bg-jarvis text-white" : "bg-surface-2 text-ink-2 hover:bg-surface-3"
            } disabled:opacity-40`}
          >
            <span className={listening ? "jarvis-listening" : ""} aria-hidden>
              🎙
            </span>
          </button>
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder='Essayez « rapport », « le CA ? », « va aux alertes »…'
            className="flex-1 rounded-xl border border-hairline bg-surface-2 px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-jarvis"
          />
          <button
            type="submit"
            className="rounded-xl bg-jarvis px-4 py-2 text-sm font-medium text-white transition hover:opacity-90"
          >
            Envoyer
          </button>
        </form>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Coquille : sidebar + topbar + overlay Jarvis                         */
/* ------------------------------------------------------------------ */
export function Shell({
  kpis,
  attention,
  children,
}: {
  kpis: Kpi[];
  attention: AttentionBudget;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [jarvisOpen, setJarvisOpen] = useState(false);
  const [clock, setClock] = useState<string | null>(null);

  useEffect(() => {
    const tick = () =>
      setClock(
        new Date().toLocaleTimeString(BUSINESS.locale, { hour: "2-digit", minute: "2-digit" }),
      );
    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setJarvisOpen((v) => !v);
      }
      if (e.key === "Escape") setJarvisOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const urgent = attention.shown.filter((a) => a.severity === "haute").length;

  return (
    <JarvisDataContext.Provider value={{ kpis, attention }}>
      <div className="flex min-h-dvh">
        {/* -------- Sidebar -------- */}
        <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-hairline bg-surface-1 px-3 py-4 md:flex">
          <div className="mb-6 flex items-center gap-2.5 px-2">
            <span className="jarvis-pulse grid size-8 place-items-center rounded-full border border-jarvis/50 bg-jarvis/10 text-jarvis">
              ◉
            </span>
            <div>
              <div className="text-sm font-semibold leading-tight">{BUSINESS.name}</div>
              <div className="text-[10px] uppercase tracking-widest text-ink-3">
                Jarvis · Enterprise OS
              </div>
            </div>
          </div>

          <nav className="flex-1 space-y-0.5">
            {NAV.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${
                    active
                      ? "bg-jarvis/15 font-medium text-ink"
                      : "text-ink-2 hover:bg-surface-2 hover:text-ink"
                  }`}
                >
                  <span
                    aria-hidden
                    className={`grid size-5 place-items-center text-xs ${active ? "text-jarvis" : "text-ink-3"}`}
                  >
                    {item.icon}
                  </span>
                  <span className="flex-1">{item.label}</span>
                  {item.href === "/alertes" && urgent > 0 && (
                    <span className="grid size-5 place-items-center rounded-full bg-critical text-[10px] font-bold text-white">
                      {urgent}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>

          <div className="mt-4 rounded-xl border border-hairline bg-surface-2 p-3 text-[11px] leading-relaxed text-ink-3">
            <div className="mb-1 flex items-center gap-1.5 text-ink-2">
              <span className="inline-block size-1.5 rounded-full bg-good" aria-hidden />
              Boucle vivante : active
            </div>
            Budget d&apos;attention : {attention.shown.length}/{attention.cap} montrées,{" "}
            {attention.suppressed} contenues.
          </div>
        </aside>

        {/* -------- Colonne principale -------- */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-40 flex items-center justify-between gap-3 border-b border-hairline bg-page/85 px-4 py-3 backdrop-blur md:px-8">
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold">
                {NAV.find((n) => n.href === pathname)?.label ?? "Command center"}
              </h1>
              <p className="text-xs text-ink-3">
                {new Date().toLocaleDateString(BUSINESS.locale, {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                })}
                {clock && ` · ${clock}`} · {BUSINESS.timezone}
              </p>
            </div>
            <button
              onClick={() => setJarvisOpen(true)}
              className="flex shrink-0 items-center gap-2 rounded-full border border-jarvis/40 bg-jarvis/10 px-4 py-2 text-sm text-ink transition hover:bg-jarvis/20"
            >
              <span className="jarvis-pulse inline-block size-2 rounded-full bg-jarvis" aria-hidden />
              Parler à Jarvis
              <kbd className="rounded border border-hairline bg-surface-2 px-1.5 text-[10px] text-ink-3">
                ⌘K
              </kbd>
            </button>
          </header>

          <main className="flex-1 px-4 py-6 md:px-8">{children}</main>

          <footer className="border-t border-hairline px-4 py-3 text-center text-[11px] text-ink-3 md:px-8">
            Les événements sont la seule vérité · aucune valeur inventée · N5 = humain, toujours.
          </footer>
        </div>
      </div>

      <JarvisOverlay open={jarvisOpen} onClose={() => setJarvisOpen(false)} />
    </JarvisDataContext.Provider>
  );
}
