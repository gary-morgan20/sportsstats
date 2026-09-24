"""International results (martj42/international_results on GitHub, updated regularly).

Used for national-team competitions such as the UEFA Nations League. Only full-time scores are
available, so first-half goals and corners can't be modelled for these matches.
"""
from __future__ import annotations

import time

import pandas as pd
import requests

from ..config import DATA_DIR

URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
CACHE = DATA_DIR / "international" / "results.csv"
UEFA_TOURNAMENTS = ("UEFA Nations League", "UEFA Euro", "UEFA Euro qualification")


def load_results(years_back: int = 4, friendly_weight: float = 0.5) -> pd.DataFrame:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    if not CACHE.exists() or time.time() - CACHE.stat().st_mtime > 12 * 3600:
        r = requests.get(URL, timeout=60)
        r.raise_for_status()
        CACHE.write_bytes(r.content)
    raw = pd.read_csv(CACHE, parse_dates=["date"])
    raw = raw.dropna(subset=["home_score", "away_score"])

    # European teams = anyone who played a UEFA competition in the last 6 years
    recent = raw[raw["date"] >= pd.Timestamp.now() - pd.DateOffset(years=6)]
    uefa = set(recent.loc[recent["tournament"].isin(UEFA_TOURNAMENTS), ["home_team", "away_team"]].stack())

    df = raw[(raw["date"] >= pd.Timestamp.now() - pd.DateOffset(years=years_back))
             & raw["home_team"].isin(uefa) & raw["away_team"].isin(uefa)]
    return pd.DataFrame({
        "Date": df["date"], "HomeTeam": df["home_team"], "AwayTeam": df["away_team"],
        "FTHG": df["home_score"].astype(int), "FTAG": df["away_score"].astype(int),
        "Neutral": df["neutral"].astype(str).str.upper().eq("TRUE"),
        # friendlies are played with rotated squads and less intensity, so count them less
        "Weight": df["tournament"].eq("Friendly").map({True: friendly_weight, False: 1.0}),
    }).reset_index(drop=True)
