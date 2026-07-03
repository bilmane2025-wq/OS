/**
 * Profil de l'entreprise — le point unique de personnalisation.
 *
 * Les valeurs par défaut reflètent l'Enterprise OS existant (vente via
 * Uber Eats / Deliveroo, fournisseur principal Foodex, comptes en EUR,
 * exposition EUR/MAD). Tout est surchargeable par variable d'environnement
 * NEXT_PUBLIC_* sans toucher au code.
 */
export const BUSINESS = {
  name: process.env.NEXT_PUBLIC_BUSINESS_NAME ?? "Bilmane Food Ops",
  operator: process.env.NEXT_PUBLIC_OPERATOR_NAME ?? "Patron",
  currency: "EUR" as const,
  locale: "fr-BE" as const,
  timezone: "Europe/Brussels",
  /** Canaux de vente réels du système (règles categorization/* du corpus). */
  channels: ["Uber Eats", "Deliveroo", "Direct"] as const,
  /** Fournisseur dominant surveillé par le KPI dependance_fournisseur. */
  mainSupplier: "Foodex",
  /** Seuil d'alerte trésorerie (règle alert-threshold/tresorerie-basse). */
  cashAlertThreshold: 2000,
  /** Écart max encaissement/vente avant anomalie (règle reconciliation/*). */
  reconciliationThreshold: 0.05,
  /** Budget d'attention : plafond de sollicitations montrées (M27). */
  attentionCap: 3,
  /** Taux EUR/MAD du corpus de règles (fx-rate/eur-mad). */
  fxEurMad: 10.9,
};

export const JARVIS = {
  name: "Jarvis",
  /** Voix de synthèse préférée (Web Speech API). */
  voiceLang: "fr-FR",
  /** Réponses vocales activées par défaut ? */
  speakByDefault: false,
};
