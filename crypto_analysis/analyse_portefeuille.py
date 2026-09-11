"""Analyse quantitative reproductible du portefeuille crypto (CoinGecko, sans cle API).

Usage :
    python -m venv venv && ./venv/bin/pip install pandas numpy requests
    ./venv/bin/python crypto_analysis/analyse_portefeuille.py

Sorties : indicateurs par actif, contribution au risque, VaR, Monte Carlo,
P&L par rapport aux prix d'achat. Aucune ecriture, aucun ordre.
"""
import json
import time

import numpy as np
import pandas as pd
import requests

CG = "https://api.coingecko.com/api/v3"
IDS = {"BTC": "bitcoin", "LINK": "chainlink", "VVV": "venice-token", "ZK": "zksync", "XRP": "ripple"}
# Positions au prix d'achat (capture Revolut du 11/09/2026 04:44).
QTY = {"VVV": 2.63, "LINK": 5.044, "BTC": 0.00020, "ZK": 1659.93, "XRP": 4.21}
BUY = {"VVV": 23.11, "LINK": 11.34, "BTC": 75956, "ZK": 0.0092, "XRP": 1.32}
CASH = 0.73


def fetch_history(coin_id, days=365):
    r = requests.get(f"{CG}/coins/{coin_id}/market_chart",
                     params={"vs_currency": "usd", "days": days, "interval": "daily"}, timeout=30)
    r.raise_for_status()
    ser = pd.Series({pd.to_datetime(t, unit="ms").normalize(): p for t, p in r.json()["prices"]})
    return ser[~ser.index.duplicated(keep="last")]


def rsi(close, n=14):
    d = close.diff()
    up, dn = d.clip(lower=0), -d.clip(upper=0)
    return 100 - 100 / (1 + up.ewm(alpha=1 / n, adjust=False).mean() / dn.ewm(alpha=1 / n, adjust=False).mean())


def main():
    px = {}
    for sym, cid in IDS.items():
        px[sym] = fetch_history(cid)
        time.sleep(3)  # respect du rate limit public CoinGecko
    df = pd.DataFrame(px).dropna()
    r = np.log(df / df.shift(1)).dropna()

    val = {s: QTY[s] * BUY[s] for s in QTY}
    tot = sum(val.values()) + CASH
    w = {s: val[s] / tot for s in QTY}
    cols = list(df.columns)
    wv = np.array([w[s] for s in cols])

    stats = {}
    for s in cols:
        c, rs = df[s], r[s]
        stats[s] = {
            "last": float(c.iloc[-1]), "rsi14": float(rsi(c).iloc[-1]),
            "vs_sma50_pct": float(c.iloc[-1] / c.rolling(50).mean().iloc[-1] - 1) * 100,
            "vs_sma200_pct": float(c.iloc[-1] / c.rolling(200).mean().iloc[-1] - 1) * 100,
            "ema20": float(c.ewm(span=20).mean().iloc[-1]),
            "vol30_ann_pct": float(rs[-30:].std() * np.sqrt(365)) * 100,
            "beta_btc_90d": float(np.cov(rs[-90:], r["BTC"][-90:])[0, 1] / np.var(r["BTC"][-90:])),
            "corr_btc_90d": float(rs[-90:].corr(r["BTC"][-90:])),
            "maxdd_1y_pct": float((c / c.cummax() - 1).min()) * 100,
        }

    cov90 = r[-90:].cov() * 365
    pvol = float(np.sqrt(wv @ cov90.values @ wv))
    ctr = wv * (cov90.values @ wv / pvol) / pvol
    pr = r[-180:] @ wv
    var95 = float(np.percentile(pr, 5))
    cvar95 = float(pr[pr <= var95].mean())

    rng = np.random.default_rng(42)
    L = np.linalg.cholesky(r[-90:].cov().values)
    mc = {}
    for H in (30, 90):
        sims = rng.standard_normal((20000, H, len(wv))) @ L.T
        pv = np.exp((sims @ wv).sum(axis=1))
        mc[H] = {"p5": float(np.percentile(pv, 5)) - 1, "med": float(np.median(pv)) - 1,
                 "p95": float(np.percentile(pv, 95)) - 1, "p_loss20": float((pv < 0.8).mean())}

    cur = sum(QTY[s] * stats[s]["last"] for s in QTY) + CASH
    out = {"total_achat": tot, "valeur_actuelle": cur, "pnl_pct": (cur / tot - 1) * 100,
           "poids": w, "vol_portefeuille_ann_pct": pvol * 100,
           "contribution_risque": {s: float(ctr[i]) for i, s in enumerate(cols)},
           "var95_1j_pct": var95 * 100, "cvar95_1j_pct": cvar95 * 100, "monte_carlo": mc, "actifs": stats}
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
