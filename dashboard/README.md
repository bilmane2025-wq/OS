# Jarvis Command Center — dashboard Next.js

Centre de commandement de l'entreprise, adossé aux concepts de l'Enterprise OS
(le projet Python à la racine du dépôt) : les 8 KPI du MVP avec **nature +
score de confiance** sur chaque chiffre, **alertes sous budget d'attention**
(plafond 3, dédupliquées, jamais insistantes), **échelle d'autorité N0-N5**
sur les automatisations, **watchdog des sources**, et un **Jarvis** vif et
efficace pilotable au clavier (⌘K) comme à la voix.

## Lancer

```bash
cd dashboard
npm install
npm run dev        # http://localhost:3000
```

## Modules

| Route | Contenu |
|---|---|
| `/` | Vue instantanée — l'essentiel en 10 s : 8 KPI, revenus 14 j par canal, sollicitations, watchdog |
| `/revenus` | CA par canal, trésorerie vs seuil, food cost, commissions, dépendance fournisseur |
| `/emails` | Boîte triée (fournisseur / plateforme / banque / client / admin) + brouillons Jarvis |
| `/social` | Analytics Instagram · Facebook · TikTok · Google Business + planificateur de contenu |
| `/campagnes` | Budgets, ROAS, coût/commande + recommandations |
| `/automatisations` | Tâches automatisées (autorité N0-N5) + connecteurs inertes |
| `/alertes` | Sollicitations montrées / contenues, gravité·probabilité·impact·recommandation |
| `/equipe` | Présence, heures, volume traité |

## Jarvis

- **⌘K / Ctrl+K** ouvre la console. Texte ou micro (Web Speech API, `fr-FR`),
  réponse vocale optionnelle.
- Essayez : `rapport`, `le CA ?`, `trésorerie`, `food cost`, `alertes`,
  `va aux campagnes`, `planifie un post`.
- Moteur d'intentions 100 % local (`src/lib/jarvis.ts`) — le branchement d'un
  LLM se fait dans `src/app/api/jarvis/route.ts` sans changer le contrat.

## Personnalisation

Tout part de `src/lib/config.ts`, surchargeable par variables d'environnement :

```bash
NEXT_PUBLIC_BUSINESS_NAME="Chez Bilmane"
NEXT_PUBLIC_OPERATOR_NAME="Bilal"
```

## Brancher les vraies données

La couche `src/lib/mock/data.ts` est **le contrat** : chaque fonction
(`getKpis`, `getChannelDays`, `getEmails`, …) est le point de branchement d'un
connecteur réel — mêmes formes, mêmes garanties (jamais une valeur nue, `null`
plutôt qu'un zéro inventé). Les connecteurs correspondent à
`connectors_disabled/` de l'OS et restent **inertes** tant que leur clé n'est
pas posée (coffre M30) :

| Connecteur | Clé | Alimente |
|---|---|---|
| Uber Eats | `UBER_EATS_API_KEY` | commandes, commissions |
| Deliveroo | `DELIVEROO_API_KEY` | commandes, promotions |
| Banque (PSD2) | `BANK_API_KEY` | trésorerie, rapprochement |
| Comptabilité | `ACCOUNTING_API_KEY` | marge, food cost |
| Gmail | `GMAIL_OAUTH_CLIENT` | triage emails → inbox OS |
| Meta | `META_GRAPH_TOKEN` | analytics + publication (N4) |

Lois conservées de la Constitution de l'OS : les événements sont la seule
vérité · aucune valeur inventée · N5 = humain, toujours.
