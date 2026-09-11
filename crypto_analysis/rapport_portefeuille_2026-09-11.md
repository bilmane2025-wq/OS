# Analyse du portefeuille crypto Revolut — 11 septembre 2026

Cadre : PLAN · EXECUTE · VERIFY. Chaque bloc est labellisé (CONFIRMÉ = donnée obtenue par outil, RÉDIGÉ = texte d'analyse, EN ATTENTE = dépend d'un événement externe).

## 0. Verdict en une page — RÉDIGÉ

Le portefeuille (154,73 $ au prix d'achat + 0,73 $ de devise) est un pari concentré sur un seul token narratif : **Venice (VVV) pèse 39 % du capital mais 66 % du risque**. Il a été acheté deux jours après son plus haut historique, après +37 % en une semaine, avec un RSI à 69. Le reste (LINK 37 %, BTC 10 %, ZK 10 %, XRP 4 %) est un panier à bêta élevé sur Bitcoin, acheté **cinq jours avant le FOMC le plus risqué de l'année** (probabilité de hausse de taux ~56 %), le jour de la publication du CPI d'août, dans un marché qui vient de perdre 4,4 % en 24 h.

Résultat brut au moment de l'analyse : **+1,6 %** (157,1 $ sur CoinGecko contre 155,3 $ affiché par Revolut, l'écart est le spread Revolut). Net des frais Revolut Standard (1,49 % par côté + spread), la position est en réalité **autour de −2 %** : il faut environ +3,5 % pour être à l'équilibre à la revente.

Trois décisions concrètes, dans l'ordre :

1. **VVV : fixer un seuil de sortie partielle maintenant.** Clôture journalière sous 18,4 $ (EMA20) = vendre la moitié. Au-dessus de 29,2 $ (ATH) = vendre un tiers pour ramener le poids sous 25 %.
2. **Ne rien acheter avant le 16 septembre 20 h (heure belge).** CPI aujourd'hui 14 h 30, vote Clarity Act le 15 à 20 h 15, FOMC le 16 à 20 h. Les trois peuvent chacun bouger le portefeuille de ±10 %.
3. **Sur Revolut, ne pas faire de micro-trades.** À 1,49 % par côté, un aller-retour de 20 $ coûte 0,60 $ + spread. Regrouper les ordres.

---

## 1. PLAN — RÉDIGÉ

1. Recenser les meilleurs dépôts GitHub crypto utilisables sans compte ni clé API, les cloner et les installer.
2. Collecter les données live : prix, historiques 365 j, dominance, Fear & Greed, funding, open interest, TVL, liquidité DEX, macro (taux, dollar, VIX).
3. Calculer : poids, contribution au risque, volatilité, bêta/corrélation BTC, RSI, moyennes mobiles, drawdowns, VaR, Monte Carlo 30/90 j, P&L vs prix d'achat.
4. Croiser avec le contexte macro (Fed, CPI, Clarity Act, flux ETF, cycle) et les catalyseurs propres à chaque actif.
5. Produire le rapport, le script reproductible, le snapshot de données ; commit, push, PR.

## 2. EXECUTE — outils installés — CONFIRMÉ

Tous clonés depuis GitHub et installés dans un venv Python 3.11 ou via npm. Aucun ne nécessite de login pour les données utilisées ici.

| Dépôt | Étoiles | Usage | Login ? |
|---|---|---|---|
| ccxt/ccxt (pip 4.5.78) | 30k+ | Données publiques de 100+ exchanges | Non (endpoints publics) |
| ranaroussi/yfinance (pip 1.7.0) | 15k+ | Macro (actions, taux, DXY) | Non, **mais Yahoo bloqué par le proxy de la session** |
| man-c/pycoingecko (pip 3.2.0) | 1k+ | CoinGecko API publique | Non |
| atilaahmettaner/tradingview-mcp | 4 414 | Screeners TradingView, TA, backtests (MCP) | Non |
| nirholas/cryptocurrency.cv | 307 | Agrégateur d'actus 300+ sources, MCP hébergé | Non |
| BlockRunAI/awesome-finance-mcp | 209 | Liste curatée des MCP finance (FRED, Yahoo, DexPaprika…) | Liste |
| badkk/awesome-crypto-mcp-servers | 144 | Liste curatée des MCP crypto | Liste |
| kukapay/crypto-indicators-mcp (npm, 113 paquets) | 130 | 50+ indicateurs TA + stratégies BUY/SELL/HOLD | Non |
| kukapay/crypto-feargreed-mcp | 52 | Fear & Greed live + historique | Non |
| kukapay/crypto-sentiment-mcp | 47 | Sentiment social | Non (source Santiment, quota gratuit) |
| kukapay/whale-tracker-mcp | 56 | Transactions baleines | Clé Whale Alert requise pour l'usage réel |
| kukapay/defi-yields-mcp | 16 | Rendements DeFi via DefiLlama | Non |
| kukapay/crypto-portfolio-mcp | 10 | Suivi d'allocation | Non |
| kukapay/funding-rates-mcp | 8 | Funding multi-exchanges via ccxt | Non |
| kukapay/crypto-liquidations-mcp | 8 | Flux de liquidations Binance | Non (mais Binance géo-bloqué ici) |
| kukapay/token-minter-mcp | 21 | Cloné pour inventaire, non utilisé | — |

APIs publiques directement interrogées : CoinGecko, alternative.me (Fear & Greed), OKX (funding), DefiLlama (TVL), DexScreener (liquidité VVV sur Base), CoinPaprika, FRED (taux US, dollar, VIX).

Limites rencontrées — CONFIRMÉ : Binance Futures et Bybit refusent la région du serveur (open interest et ratio long/short indisponibles) ; Yahoo Finance coupé par le proxy (S&P 500 repris de la presse, non vérifié par outil) ; pandas-ta et ta non installables sur Python 3.11 dans cet environnement, les indicateurs ont été recalculés à la main (numpy/pandas).

## 3. EXECUTE — portefeuille au prix d'achat — CONFIRMÉ (capture) / calculs CONFIRMÉ

| Actif | Quantité | Prix d'achat | Valeur | Poids | Prix CoinGecko | P&L brut |
|---|---|---|---|---|---|---|
| Venice Token (VVV) | 2,63 | 23,11 $ | 60,78 $ | 39,3 % | 23,49 $ | +1,6 % |
| Chainlink (LINK) | 5,044 | 11,34 $ | 57,20 $ | 37,0 % | 11,48 $ | +1,2 % |
| Bitcoin (BTC) | 0,00020 | 75 956 $ | 15,19 $ | 9,8 % | 76 774 $ | +1,1 % |
| ZKsync (ZK) | 1 659,93 | 0,0092 $ | 15,27 $ | 9,9 % | 0,00947 $ | +3,0 % |
| XRP | 4,21 | 1,32 $ | 5,56 $ | 3,6 % | 1,34 $ | +1,5 % |
| Devise | — | — | 0,73 $ | 0,5 % | — | — |
| **Total** | | | **154,73 $** | 100 % | **157,14 $** | **+1,6 %** |

Revolut affiche 155,34 $ : l'écart de 1,8 $ avec CoinGecko correspond au spread intégré dans le prix de revente Revolut. C'est la vraie valeur liquidative.

## 4. EXECUTE — risque et quant (365 j de données journalières CoinGecko) — CONFIRMÉ

**Structure du risque**

| Mesure | Valeur |
|---|---|
| Volatilité annualisée du portefeuille (cov. 90 j) | 60,9 % |
| Contribution au risque : VVV / LINK / ZK / BTC / XRP | 66 % / 22 % / 6 % / 4 % / 2 % |
| Nombre effectif de positions (1/HHI) | 3,2 |
| VaR 1 jour à 95 % (historique 180 j, poids actuels) | −5,1 % |
| CVaR 95 % (perte moyenne dans les 5 % pires jours) | −8,0 % |
| Pire / meilleur jour sur 180 j avec ce mix | −12,3 % / +12,4 % |
| Drawdown max de ce mix sur 1 an | −54,9 % |
| Monte Carlo 30 j (20 000 tirages, drift nul) : p5 / médiane / p95 | −25 % / 0 % / +33 % |
| Monte Carlo 90 j : p5 / médiane / p95 | −39 % / 0 % / +65 % |
| P(perte > 20 % à 90 j) / P(gain > 20 % à 90 j) | 23 % / 27 % |

Lecture : le portefeuille est en fait « VVV + un panier BTC-bêta ». BTC, censé être l'ancre, ne pèse que 4 % du risque. La corrélation VVV/BTC à 90 j n'est que 0,26, ce qui diversifie sur le papier, mais c'est une diversification vers un risque idiosyncratique (narratif IA) et non vers un actif défensif.

**Par actif (indicateurs journaliers, 90 j sauf mention)**

| | BTC | LINK | VVV | ZK | XRP |
|---|---|---|---|---|---|
| RSI 14 | 53,6 | 52,6 | **68,9** | 52,3 | 51,1 |
| vs SMA50 | +9 % | +15 % | **+60 %** | +10 % | +11 % |
| vs SMA200 | +10 % | +25 % | **+98 %** | **−35 %** | +5 % |
| Vol. annualisée 30 j | 47 % | 81 % | **151 %** | 92 % | 89 % |
| Bêta BTC 90 j | 1,00 | 1,24 | 0,84 | 1,14 | 1,44 |
| Corrélation BTC 90 j | 1,00 | 0,76 | 0,26 | 0,59 | 0,87 |
| 7 j / 30 j / 1 an | −5 % / +21 % / −34 % | −3 % / +31 % / −53 % | +37 % / +104 % / +757 % | 0 % / +28 % / −85 % | −8 % / +31 % / −56 % |
| Distance à l'ATH | −39 % (126 080 $) | −78 % (52,7 $) | −19 % (29,19 $, le 9 sept.) | **−97 %** (0,32 $) | −63 % (3,65 $) |
| Funding OKX (8 h) | +0,010 % | ~0 % | +0,005 % | +0,003 % | — |

Funding neutre partout : pas d'euphorie à levier, pas de squeeze imminent. Le marché dérivés n'est pas la source du risque cette semaine, la macro l'est.

## 5. EXECUTE — contexte macro — CONFIRMÉ (outil) sauf mention

| Indicateur | Valeur | Source |
|---|---|---|
| Fed funds : probabilité de **hausse** de 25 pb au FOMC des 15-16 sept. | ~56 % (pic 62 %) | CME FedWatch via presse — RÉDIGÉ |
| US 10 ans / 2 ans | 4,83 % / 4,43 % (2 ans au plus haut depuis janv. 2025) | FRED DGS10, DGS2 |
| Dollar (indice large) | 118,1 | FRED DTWEXBGS |
| VIX | 16,5 (en hausse depuis 14,3 le 3 sept.) | FRED VIXCLS |
| Emplois non agricoles août | +162 k contre +53 k attendus | presse — RÉDIGÉ |
| CPI août (publié aujourd'hui 14 h 30 heure belge) | attendu +0,4 % m/m, 3,4 % a/a, core 2,4 % | presse — EN ATTENTE |
| S&P 500 | 7 673 (8 sept., −0,6 %) | presse — RÉDIGÉ |
| Capitalisation crypto totale | 2,64 T$, **−4,4 % sur 24 h** | CoinGecko |
| Dominance BTC / ETH | 58,5 % / 11,3 % | CoinGecko |
| Fear & Greed | 56 (Greed), contre 74 il y a deux semaines et 29 il y a un mois | alternative.me |
| Altcoin Season Index | 34-37 (« Bitcoin season », seuil altseason = 75) | presse — RÉDIGÉ |
| Flux ETF Bitcoin spot | +3,8 Md$ sur 3 semaines, meilleure série de 2026 ; 731 M$ le 3 sept. | presse — RÉDIGÉ |
| Clarity Act (structure de marché) | vote de clôture au Sénat le 15 sept. 14 h 15 ET ; Galaxy estime à ~10 % la probabilité d'adoption en 2026 | presse — RÉDIGÉ |
| Cycle | ATH BTC 126 k$ le 6 oct. 2025 ; 2026 = année post-sommet du cycle de 4 ans ; plus bas 2026 à 58,6 k$ | CoinGecko + presse |

**Lecture macro — RÉDIGÉ.** Le régime est « inflation collante + Fed potentiellement en hausse + dollar fort + taux réels élevés ». C'est le pire régime pour les altcoins à faible capitalisation. Deux signaux contraires le nuancent : les flux ETF Bitcoin restent massivement positifs (le capital institutionnel achète les creux) et le Fear & Greed est redescendu de 74 à 56, ce qui purge une partie de l'excès. Le marché altcoin est en « Bitcoin season » : sur 90 jours, la majorité des 50 premières capitalisations sous-performent BTC. Dans ce régime, détenir 90 % d'altcoins revient à parier contre la tendance de fond.

La semaine à venir concentre trois binaires : CPI (aujourd'hui), Clarity Act (15), FOMC (16). Si le CPI sort chaud et la Fed monte, BTC teste 72-73 k$ (support suivant après 75-76,5 k$) et les alts perdent typiquement 2 à 3 fois plus. Si le CPI est conforme et la Fed reste à 4,5 %, le soulagement ramène BTC vers 80,6-82 k$.

## 6. EXECUTE — analyse par actif — RÉDIGÉ (faits CONFIRMÉ par outil ou presse citée)

### Venice Token (VVV) — 39 % du capital, 66 % du risque

Faits : capitalisation 1,13 Md$, FDV 1,90 Md$ (59 % de l'offre en circulation), rang 69. ATH 29,19 $ le 9 septembre, prix d'achat 23,11 $ deux jours après. +104 % sur 30 j, +757 % sur 1 an. RSI 69, prix 98 % au-dessus de la SMA200. Volatilité 30 j 151 % annualisée. Liquidité DEX principale (Aerodrome, Base) 14,1 M$ ; sur 24 h, 7 570 achats contre 3 708 ventes, la pression acheteuse tient encore.

Catalyseurs réels : chiffre d'affaires annualisé 100 M$ franchi le 17 août ; rachat-brûlage (33,7 M VVV brûlés = 42 % de l'offre effective) ; émissions réduites à 2,5 M/an le 1er sept. et 2 M/an le 1er oct. ; dérivés Kalshi (régulé CFTC) le 4 sept. ; trésorerie TenX Protocols ; narratif « IA privée » dopé par la polémique OpenAI et l'IPO Anthropic (visée mi-octobre, valorisation ~965 Md$).

Risques : c'est un token de narratif. Le rallye est adossé à l'IPO Anthropic : tout report ou déception la fait se dénouer vite (les tokens IA ont déjà fait ce mouvement en juin). Déblocage de 312 500 VVV le 27 septembre (~7,3 M$, 0,65 % de l'offre circulante, absorbable mais sur un token qui a triplé). Structure technique de « blow-off » potentielle : +60 % au-dessus de la SMA50 est le niveau où les corrections de 30-40 % arrivent sans changement fondamental.

Position : la thèse fondamentale est parmi les meilleures du portefeuille (revenus réels, brûlage, émissions en baisse). Le problème n'est pas l'actif, c'est **le timing et la taille**. À 39 % après un x2 mensuel, l'espérance est asymétrique vers le bas à court terme.

### Chainlink (LINK) — 37 % du capital, 22 % du risque

Faits : 11,48 $, rang 17, capitalisation 8,6 Md$, 748 M LINK en circulation sur 1 Md. −78 % de l'ATH (52,7 $). Rallye de 8,3 $ à 12,5 $ la semaine dernière, prises de bénéfices depuis (−3 % sur 7 j). RSI 52, +25 % au-dessus de la SMA200 : tendance intermédiaire haussière, pas surchauffée. Bêta 1,24, corrélation BTC 0,76.

Catalyseurs : Circle Arc mainnet le 16 septembre avec Chainlink comme oracle officiel ; partenariat Bottomline (600+ banques, 16 T$/an, sans pilote confirmé) ; Coinbase choisit Chainlink pour les actions tokenisées sur Base ; Schwab liste LINK ; Chainlink Reserve à 5,48 M LINK convertis depuis les revenus (Payment Abstraction).

Risques : la corrélation 0,76 avec BTC fait que LINK ne protège pas contre un FOMC hostile. Le partenariat Bottomline est une annonce, pas un flux. La Reserve est symboliquement forte mais petite (48 M$ contre 8,6 Md$ de capitalisation).

Position : c'est le meilleur actif « qualité » du portefeuille : revenus on-chain, adoption institutionnelle prouvée, valorisation encore −78 % de l'ATH. À conserver. Le catalyseur du 16 septembre tombe le même jour que le FOMC : ne pas confondre le mouvement macro avec la réaction à Arc.

### Bitcoin (BTC) — 10 % du capital, 4 % du risque

Faits : 76 774 $, −39 % de l'ATH, +21 % sur 30 j, −5 % sur 7 j. Au-dessus des SMA50 (70,4 k$) et SMA200 (70,0 k$), RSI 54. Supports 75-76,5 k$ puis 72-73 k$ ; résistances 80,6-82,2 k$. Funding 0,01 % : neutre.

Position : c'est l'actif le plus liquide, le plus institutionnalisé (ETF > 103 Md$ d'actifs, +3,8 Md$ en 3 semaines), et le seul dont le drawdown est déjà « fait » (−53 % max sur 1 an contre −90 % pour ZK). Il est sous-pondéré. Dans un régime « Bitcoin season », c'est l'actif à surpondérer, pas à réduire à 10 %.

### ZKsync (ZK) — 10 % du capital, 6 % du risque

Faits : 0,00947 $, −97 % de l'ATH, −87,5 % du plus haut 1 an, −35 % sous la SMA200. Capitalisation 98 M$, FDV 199 M$ : **la moitié de l'offre reste à débloquer**, 0,8 % de l'offre totale chaque mois jusqu'en juin 2028 (168 M ZK/mois ≈ 1,6 M$, soit 1,6 % de la capitalisation circulante en pression vendeuse mensuelle). TVL ZKsync Era : **15 M$**, contre 5,5 Md$ pour Base et 1,4 Md$ pour Arbitrum. En termes d'usage, la chaîne est marginale.

Catalyseurs : roadmap 2026 (confidentialité, interopérabilité native, frais cross-chain payés en ZK depuis la v31), Deutsche Bank / Project Dama 2, listing Revolut (mai) et Bitstamp (juin). L'actif rebondit de +28 % sur 30 j depuis un plancher extrême.

Position : ticket de loterie. Le ratio FDV/TVL (13x) est le plus mauvais du portefeuille. Si la thèse est « rebond d'un L2 massacré », 5 % suffisent ; à 10 % avec un déblocage mensuel structurel, c'est une position qui exige un catalyseur précis pour justifier son coût de portage.

### XRP — 4 % du capital, 2 % du risque

Faits : 1,34 $, −63 % de l'ATH, bêta 1,44 et corrélation 0,87 avec BTC : c'est le proxy BTC le plus pur du portefeuille, avec plus de volatilité. Ripple libère 1 Md XRP d'escrow le 1er de chaque mois (absorbé en septembre). Catalyseurs : Mastercard intègre RLUSD (9 sept.), parts d'ETF XRP utilisées en collatéral institutionnel.

Position : à 5,56 $ la ligne est trop petite pour compter et redondante avec BTC. Soit la monter à une taille utile, soit la fusionner dans BTC pour économiser un spread.

## 7. EXECUTE — scénarios à 7 jours — RÉDIGÉ (ordres de grandeur dérivés des bêtas et des volatilités CONFIRMÉ)

| Scénario | Probabilité (estimée) | BTC | Portefeuille | Ce qui le déclenche |
|---|---|---|---|---|
| CPI chaud + Fed monte à 4,75 % le 16 | ~40 % | 72-73 k$ (−5 à −6 %) | **−12 à −18 %** | 10 ans > 4,9 %, dollar > 119, VVV corrige 25-35 % |
| CPI conforme + Fed maintient | ~45 % | 80-82 k$ (+5 à +7 %) | **+6 à +12 %** | LINK profite d'Arc mainnet, VVV retest ATH 29 $ |
| Clarity Act passe la clôture le 15 | ~30 % (indépendant) | +2 à +4 % | +4 à +8 % | LINK et XRP surperforment (tokens « institutionnels ») |
| IPO Anthropic reportée / mal reçue (mi-oct.) | ~30 % | neutre | **−10 à −15 %** via VVV seul | les tokens IA se dénouent ensemble |

## 8. EXECUTE — recommandations — RÉDIGÉ (aucune n'est exécutée, aucun ordre n'a été passé)

1. **VVV, règle de sortie écrite avant l'événement.** Clôture journalière < 18,4 $ (EMA20) → vendre 50 %. Prix > 29,2 $ (ATH) → vendre 33 %. Cible de poids : 20-25 %. Ne pas « moyenner à la baisse » sur un token à 151 % de volatilité.
2. **Rééquilibrer vers BTC après le FOMC, pas avant.** Cible : BTC 30-40 %, LINK 30 %, VVV 20-25 %, ZK ≤ 5 %, XRP 0 ou ≥ 10 %. Attendre la clôture du 16 septembre pour connaître le régime.
3. **Frais Revolut Standard : 1,49 % par côté + spread.** Sur 155 $, un rééquilibrage complet coûte 4-5 $ (3 %). Faire un seul passage de rééquilibrage, pas cinq. Revolut X (le hub pro) est nettement moins cher si les montants grossissent.
4. **Calendrier à surveiller (heure belge)** : 11 sept. 14 h 30 CPI ; 15 sept. 20 h 15 vote Clarity ; 16 sept. 20 h FOMC + conférence Warsh 20 h 30 + Arc mainnet ; ~17 sept. déblocage mensuel ZK ; 27 sept. déblocage VVV ; 1er oct. baisse d'émissions VVV ; mi-octobre IPO Anthropic.
5. **Taille du portefeuille.** À 155 $, le rendement attendu en euros ne couvre pas le temps de gestion. L'utilité réelle est l'apprentissage : tenir un journal (prix, raison d'achat, règle de sortie) pour chaque ligne. Ce rapport en est la première entrée.

## 9. VERIFY — état honnête

| Élément | État |
|---|---|
| Dépôts GitHub clonés et installés (16 dépôts, venv + npm) | CONFIRMÉ |
| Données prix/historiques/dominance/F&G/funding/TVL/DEX/FRED | CONFIRMÉ par appels d'outil |
| Calculs quant (script `analyse_portefeuille.py`, snapshot JSON) | CONFIRMÉ, reproductibles |
| Chiffres macro issus de la presse (FedWatch, payrolls, S&P, flux ETF, Clarity Act, altseason index) | RÉDIGÉ d'après sources web, non vérifiés par API |
| Open interest / ratio long-short Binance-Bybit | NON OBTENU (géo-blocage) |
| CPI d'août, FOMC, vote Clarity, IPO Anthropic | EN ATTENTE |
| Prix d'achat | pris de la capture d'écran (hypothèse utilisateur : achat il y a 30 min) |
| Ordres, ventes, rééquilibrage | RIEN N'A ÉTÉ EXÉCUTÉ, recommandations seulement |
| Rapport, script, snapshot commités et poussés sur `claude/crypto-portfolio-analysis-prow59` | voir PR |

Ce document est une analyse, pas un conseil en investissement personnalisé.
