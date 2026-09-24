"""Compare model probabilities with bookmaker prices and pick out value.

An "offer" is one price: (match, market, bookmaker, decimal odds).
For each match+market we keep the best price at your bookmakers and also work out the
market's own view (average price across all bookmakers with the margin removed), so the
shortlist shows both how far we disagree with the price and with the market as a whole.
"""
from __future__ import annotations

import pandas as pd

# Groups of outcomes that together cover every result, used to strip the bookmaker margin.
COMPLEMENTS = [
    ("home_win", "draw", "away_win"),
    ("dnb_home", "dnb_away"),
    ("btts_yes", "btts_no"),
]
for _l in (1.5, 2.5, 3.5):
    COMPLEMENTS.append((f"over_{_l}", f"under_{_l}"))
for _l in (0.5, 1.5):
    COMPLEMENTS.append((f"1h_over_{_l}", f"1h_under_{_l}"))
for _l in (7.5, 8.5, 9.5, 10.5, 11.5, 12.5):
    COMPLEMENTS.append((f"corners_over_{_l}", f"corners_under_{_l}"))

MARKET_GROUP = {  # which config market each outcome belongs to
    "home_win": "home_win", "away_win": "away_win", "draw": None,
    "dc_1X": "double_chance", "dc_X2": "double_chance", "dc_12": "double_chance",
    "dnb_home": "draw_no_bet", "dnb_away": "draw_no_bet",
    "btts_yes": "btts", "btts_no": "btts",
}


def market_group(key: str) -> str | None:
    if key in MARKET_GROUP:
        return MARKET_GROUP[key]
    if key.startswith("1h_"):
        return "first_half_goals"
    if key.startswith("corners_"):
        return "total_corners"
    for l in ("1.5", "2.5", "3.5"):
        if key in (f"over_{l}", f"under_{l}"):
            return f"over_under_{l}"
    return None


def fair_probs(avg_odds: dict[str, float]) -> dict[str, float]:
    """Remove the margin from average prices (proportional method)."""
    out = {}
    for group in COMPLEMENTS:
        if all(k in avg_odds for k in group):
            implied = [1 / avg_odds[k] for k in group]
            s = sum(implied)
            out.update({k: p / s for k, p in zip(group, implied)})
    if all(k in out for k in ("home_win", "draw", "away_win")):
        out.setdefault("dc_1X", out["home_win"] + out["draw"])
        out.setdefault("dc_X2", out["draw"] + out["away_win"])
        out.setdefault("dc_12", out["home_win"] + out["away_win"])
    return out


def find_value(offers: pd.DataFrame, predictions: dict[str, dict], cfg: dict) -> pd.DataFrame:
    """offers columns: match_id, league, kickoff, home, away, market, bookmaker, odds
    predictions: match_id -> {market: probability, ...}"""
    v = cfg["value"]
    wanted = set(cfg["markets"])
    mine = set(cfg["odds"].get("my_bookmakers") or [])
    comm = cfg["odds"].get("exchange_commission") or {}
    offers = offers.copy()
    # odds you actually get paid at: exchange winnings are reduced by commission
    offers["net_odds"] = [1 + (o - 1) * (1 - comm.get(b, 0)) for o, b in zip(offers["odds"], offers["bookmaker"])]
    rows = []
    for mid, g in offers.groupby("match_id"):
        probs = predictions.get(mid)
        if not probs:
            continue
        avg = g.groupby("market")["odds"].mean().to_dict()
        fair = fair_probs(avg)
        # only prices you can actually take count as "best odds"; others just inform the market average
        pool = g[g["bookmaker"].isin(mine)] if mine else g
        if pool.empty:
            continue
        best = pool.loc[pool.groupby("market")["net_odds"].idxmax()]
        first = g.iloc[0]
        for _, b in best.iterrows():
            mk = b["market"]
            if mk not in probs or market_group(mk) not in wanted:
                continue
            p, o = probs[mk], float(b["net_odds"])
            edge = p * o - 1
            kelly = max(0.0, edge / (o - 1)) * v["kelly_fraction"] if o > 1 else 0
            rows.append({
                "league": first["league"], "kickoff": first["kickoff"],
                "match": f"{first['home']} v {first['away']}",
                "market": mk, "bookmaker": b["bookmaker"], "best_odds": round(float(b["odds"]), 2),
                "net_odds": round(o, 2),
                "model_prob": round(p, 3), "fair_odds": round(1 / p, 2) if p > 0 else None,
                "market_prob": round(fair[mk], 3) if mk in fair else None,
                "edge": round(edge, 3), "stake_pct": round(100 * kelly, 2),
                "xg": f"{probs.get('xg_home', 0):.2f}-{probs.get('xg_away', 0):.2f}",
                "books_quoting": int((g["market"] == mk).sum()),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    in_range = df["best_odds"].between(v["min_odds"], v["max_odds"])
    df["value"] = (df["edge"] >= v["min_edge"]) & (df["edge"] <= v["max_edge"]) & in_range
    # a huge edge usually means the model is missing news (injuries, rotation), not a gift
    df["check"] = (df["edge"] > v["max_edge"]) & in_range
    return df.sort_values(["value", "edge"], ascending=[False, False]).reset_index(drop=True)
