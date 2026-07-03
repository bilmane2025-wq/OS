/**
 * Modèle de domaine — miroir TypeScript des concepts de l'Enterprise OS :
 * jamais une valeur nue (nature + score de confiance sur chaque chiffre),
 * alertes actionnables (gravité / proba / impact / recommandation),
 * échelle d'autorité N0-N5 sur les automatisations.
 */

/** Nature d'une valeur — algèbre de confiance M13. */
export type Nature = "fait" | "estimation" | "hypothèse";

export interface Confidence {
  nature: Nature;
  /** 0..1 — propagé depuis les événements sources. */
  score: number;
}

export type Severity = "haute" | "moyenne" | "douce";

export interface Kpi {
  key: string;
  label: string;
  value: number | null; // null = pas de donnée : jamais un zéro inventé
  unit: "EUR" | "ratio" | "commandes/jour" | "nombre";
  confidence: Confidence;
  /** Variation vs période précédente (fraction, ex. 0.062 = +6,2 %). */
  delta: number | null;
  /** Série 14 jours pour sparkline. */
  history: number[];
  ruleVersion: number;
  computedAt: string;
}

export interface Alert {
  id: string;
  type: string;
  severity: Severity;
  message: string;
  recommendation: string; // loi 21 : toujours actionnable
  probability?: number;
  impact?: number;
  refs: string[];
  createdAt: string;
  state: "ouverte" | "traitée";
}

export interface AttentionBudget {
  shown: Alert[];
  suppressed: number;
  total: number;
  cap: number;
}

export type ChannelName = "Uber Eats" | "Deliveroo" | "Direct";

export interface ChannelDay {
  date: string; // ISO jour
  channel: ChannelName;
  revenue: number;
  orders: number;
  commission: number;
}

export interface EmailThread {
  id: string;
  from: string;
  subject: string;
  snippet: string;
  receivedAt: string;
  category: "fournisseur" | "plateforme" | "banque" | "client" | "admin";
  needsAction: boolean;
  suggestedAction?: string;
  unread: boolean;
}

export type SocialPlatform = "Instagram" | "Facebook" | "TikTok" | "Google Business";

export interface SocialStat {
  platform: SocialPlatform;
  followers: number;
  followersDelta: number;
  engagementRate: number; // fraction
  reach7d: number;
  topPost: string;
}

export interface ScheduledPost {
  id: string;
  platform: SocialPlatform;
  title: string;
  scheduledFor: string;
  status: "brouillon" | "planifié" | "publié";
  mediaType: "photo" | "vidéo" | "story" | "avis";
}

export interface Campaign {
  id: string;
  name: string;
  channel: string;
  status: "active" | "en pause" | "terminée";
  budget: number;
  spent: number;
  revenueAttributed: number;
  orders: number;
  startedAt: string;
  endsAt: string | null;
}

/** Échelle d'autorité N0-N5 (loi 16) : N5 = humain exclusivement. */
export type Authority = 0 | 1 | 2 | 3 | 4 | 5;

export interface Automation {
  id: string;
  name: string;
  description: string;
  authority: Authority;
  /** true = la transition est irréversible/matérielle → plancher N5. */
  requiresHuman: boolean;
  enabled: boolean;
  lastRun: string | null;
  runsThisWeek: number;
  status: "ok" | "attention" | "erreur" | "inerte";
}

export interface TeamMember {
  id: string;
  name: string;
  role: string;
  hoursWeek: number;
  ordersHandled: number;
  onShift: boolean;
}

export interface SourceHealth {
  sourceId: string;
  label: string;
  expectedEveryDays: number;
  lastSeen: string | null;
  status: "fraîche" | "en retard" | "muette";
}

export interface IntegrationSlot {
  id: string;
  label: string;
  kind: "ventes" | "banque" | "comptabilité" | "email" | "social";
  /** Inerte tant que la clé n'est pas posée dans le coffre (M30). */
  enabled: boolean;
  envKey: string;
  note: string;
}

export interface JarvisReply {
  text: string;
  /** Navigation suggérée par la commande, le cas échéant. */
  navigateTo?: string;
  /** Aparté facultatif — l'esprit de l'assistant. */
  quip?: string;
}
