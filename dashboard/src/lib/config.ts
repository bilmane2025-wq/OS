/**
 * Profil de l'entreprise — le point unique de personnalisation.
 *
 * Valeurs issues de src/data/business-profile.json (Kameha Poke /
 * AYBI GROUP SRL, Wavre) : canaux réels Site web · Takeaway.com ·
 * Comptoir, fournisseur dominant iFood (~48 % du food cost mesuré).
 * Tout est surchargeable par variable d'environnement NEXT_PUBLIC_*.
 */
export const BUSINESS = {
  name: process.env.NEXT_PUBLIC_BUSINESS_NAME ?? "Kameha Poke",
  legalName: "AYBI GROUP SRL",
  city: "Wavre",
  operator: process.env.NEXT_PUBLIC_OPERATOR_NAME ?? "Bilal",
  currency: "EUR" as const,
  locale: "fr-BE" as const,
  timezone: "Europe/Brussels",
  /** Canaux de vente réels (profil validé — Uber Eats : onboarding bloqué). */
  channels: ["Site web", "Takeaway.com", "Comptoir"] as const,
  /** Fournisseur dominant surveillé par le KPI dependance_fournisseur. */
  mainSupplier: "iFood",
  /**
   * Seuil d'alerte trésorerie : INCONNU au profil — 2 000 € est le seuil
   * provisoire hérité de la règle seed de l'OS, à confirmer par Bilal.
   */
  cashAlertThreshold: 2000,
  cashAlertProvisional: true,
  /** Écart max encaissement/vente avant anomalie (règle reconciliation/*). */
  reconciliationThreshold: 0.05,
  /** Budget d'attention : plafond provisoire (dailyCap inconnu au profil). */
  attentionCap: 3,
  /** Food cost cible : inconnue au profil — 28 % = référence métier, à valider. */
  foodCostTargetProvisional: 0.28,
};

export const JARVIS = {
  name: "Jarvis",
  /** Voix de synthèse préférée (Web Speech API). */
  voiceLang: "fr-FR",
  /** Réponses vocales activées par défaut ? */
  speakByDefault: false,
  /** Ton (profil) : direct, sans politesse excessive, labels d'état. */
  tone: "direct",
  statusLabels: ["RÉDIGÉ", "ENVOYÉ", "CONFIRMÉ", "EN ATTENTE"] as const,
};
