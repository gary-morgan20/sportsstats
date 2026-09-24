"""Odds sources. Each returns a DataFrame of offers with columns:
league, kickoff, home_src, away_src, bookmaker, market, odds, source

Market keys (shared with model.py):
  home_win draw away_win | dc_1X dc_X2 dc_12 | dnb_home dnb_away | btts_yes btts_no
  over_2.5 under_2.5 ... | 1h_over_0.5 ... | corners_over_9.5 ...
"""
from __future__ import annotations

import json
import re
import time

import pandas as pd
import requests

from ..config import DATA_DIR

COLS = ["league", "kickoff", "home_src", "away_src", "bookmaker", "market", "odds", "source"]
RAW = DATA_DIR / "raw"
LOCAL_TZ = "Europe/Paris"


def to_local(ts: str, source_tz: str = "UTC") -> str:
    """'2026-09-26T14:00:00Z' (or UK local time for football-data) -> '2026-09-26 16:00' Paris time."""
    t = pd.Timestamp(ts)
    t = t.tz_localize(source_tz) if t.tzinfo is None else t
    return t.tz_convert(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")


def _save_raw(name: str, payload) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{name}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- football-data fixtures.csv
# UK bookmakers use the same keys as The Odds API so prices from both sources line up.
# Pinnacle, bwin etc. are non-UK: they feed the market average but never count as "best odds".
# Column prefixes as used in football-data files from 2026/27 (older files use WH, LB, PS ... - kept too).
FD_BOOKS = {"B365": "bet365", "BFD": "betfred_uk", "BV": "betvictor", "PP": "paddypower", "SKB": "skybet",
            "BFE": "betfair_ex_uk", "WH": "williamhill", "LB": "ladbrokes_uk", "CL": "coral", "SK": "skybet",
            "BW": "bwin", "IW": "interwetten", "PS": "pinnacle", "1XB": "1xbet"}
FD_OU = {"B365": "bet365", "BFE": "betfair_ex_uk", "BV": "betvictor", "P": "pinnacle", "1XB": "1xbet"}


def from_football_data(fixtures: pd.DataFrame, fd_to_league: dict[str, str]) -> pd.DataFrame:
    rows = []
    for _, r in fixtures.iterrows():
        league = fd_to_league.get(r.get("Div"))
        if not league:
            continue
        tm = r.get("Time") if isinstance(r.get("Time"), str) else "12:00"
        kickoff = to_local(f"{r['Date']:%Y-%m-%d} {tm}", "Europe/London")
        base = [league, kickoff, r["HomeTeam"], r["AwayTeam"]]
        for pre, book in FD_BOOKS.items():
            for suf, mk in (("H", "home_win"), ("D", "draw"), ("A", "away_win")):
                o = r.get(pre + suf)
                if pd.notna(o) and o > 1:
                    rows.append(base + [book, mk, float(o), "football-data"])
        for pre, book in FD_OU.items():
            for suf, mk in ((">2.5", "over_2.5"), ("<2.5", "under_2.5")):
                o = r.get(pre + suf)
                if pd.notna(o) and o > 1:
                    rows.append(base + [book, mk, float(o), "football-data"])
    return pd.DataFrame(rows, columns=COLS)


# ---------------------------------------------------------------- The Odds API
class OddsAPI:
    BASE = "https://api.the-odds-api.com/v4"
    FEATURED = ["h2h", "totals"]
    EXTRA = ["btts", "draw_no_bet", "double_chance", "alternate_totals", "totals_h1",
             "alternate_totals_corners", "totals_corners"]

    def __init__(self, key: str, regions: list[str]):
        self.key, self.regions = key, ",".join(regions)
        self.remaining = None

    def _get(self, path: str, **params):
        params.update(apiKey=self.key, oddsFormat="decimal", dateFormat="iso")
        r = requests.get(f"{self.BASE}{path}", params=params, timeout=30)
        self.remaining = r.headers.get("x-requests-remaining", self.remaining)
        if r.status_code == 422:  # market not offered for this sport
            return []
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    def featured(self, sport: str, start: str | None = None, end: str | None = None):
        """Match result + totals. Only matches kicking off between start and end are requested, and
        The Odds API charges nothing when no matches come back, so quiet leagues cost 0 credits."""
        window = {}
        if start and end:
            window = {"commenceTimeFrom": f"{start}T00:00:00Z", "commenceTimeTo": f"{end}T23:59:59Z"}
        return self._get(f"/sports/{sport}/odds", regions=self.regions, markets=",".join(self.FEATURED), **window)

    def event(self, sport: str, event_id: str, markets: list[str] | None = None):
        return self._get(f"/sports/{sport}/events/{event_id}/odds", regions=self.regions,
                         markets=",".join(markets or self.EXTRA))

    @staticmethod
    def parse(league: str, events) -> pd.DataFrame:
        if isinstance(events, dict):
            events = [events]
        rows = []
        for ev in events:
            home, away = ev["home_team"], ev["away_team"]
            base = [league, to_local(ev["commence_time"]), home, away]
            for bm in ev.get("bookmakers", []):
                for m in bm.get("markets", []):
                    for o in m.get("outcomes", []):
                        mk = _odds_api_key(m["key"], o, home, away)
                        if mk:
                            rows.append(base + [bm["key"], mk, float(o["price"]), "the-odds-api"])
        return pd.DataFrame(rows, columns=COLS)


def _odds_api_key(market: str, o: dict, home: str, away: str) -> str | None:
    name = o.get("name", "")
    low = name.lower()
    pt = o.get("point")
    if market in ("h2h", "h2h_3_way"):
        return {home: "home_win", away: "away_win"}.get(name, "draw" if low == "draw" else None)
    if market in ("totals", "alternate_totals"):
        return f"{low}_{pt}" if pt is not None and low in ("over", "under") else None
    if market == "totals_h1":
        return f"1h_{low}_{pt}" if pt is not None else None
    if market in ("totals_corners", "alternate_totals_corners"):
        return f"corners_{low}_{pt}" if pt is not None else None
    if market == "btts":
        return {"yes": "btts_yes", "no": "btts_no"}.get(low)
    if market == "draw_no_bet":
        return {home: "dnb_home", away: "dnb_away"}.get(name)
    if market == "double_chance":
        has_h, has_a, has_d = home.lower() in low, away.lower() in low, "draw" in low
        if has_h and has_d: return "dc_1X"
        if has_a and has_d: return "dc_X2"
        if has_h and has_a: return "dc_12"
    return None


# ---------------------------------------------------------------- API-Football
class APIFootball:
    BASE = "https://v3.football.api-sports.io"
    BET_MAP = {  # API-Football bet name -> function(value) -> market key
        "Match Winner": lambda v: {"Home": "home_win", "Draw": "draw", "Away": "away_win"}.get(v),
        "Home/Away": lambda v: {"Home": "dnb_home", "Away": "dnb_away"}.get(v),
        "Double Chance": lambda v: {"Home/Draw": "dc_1X", "Draw/Away": "dc_X2", "Home/Away": "dc_12"}.get(v),
        "Both Teams Score": lambda v: {"Yes": "btts_yes", "No": "btts_no"}.get(v),
        "Goals Over/Under": lambda v: _ou(v, ""),
        "Goals Over/Under First Half": lambda v: _ou(v, "1h_"),
        "Corners Over Under": lambda v: _ou(v, "corners_"),
        "Total Corners (3 way)": lambda v: None,
    }

    BOOKS = {"bet365": "bet365", "william hill": "williamhill", "betfair": "betfair_ex_uk",
             "paddy power": "paddypower", "ladbrokes": "ladbrokes_uk", "coral": "coral", "betfred": "betfred_uk",
             "betvictor": "betvictor", "888sport": "sport888", "betway": "betway", "unibet": "unibet_uk",
             "sky bet": "skybet", "boylesports": "boylesports", "pinnacle": "pinnacle"}

    def __init__(self, key: str):
        self.key = key
        self.remaining = None

    def _get(self, path: str, **params):
        r = requests.get(f"{self.BASE}{path}", params=params, headers={"x-apisports-key": self.key}, timeout=30)
        self.remaining = r.headers.get("x-ratelimit-requests-remaining", self.remaining)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        if data.get("errors"):
            raise RuntimeError(f"API-Football {path}: {data['errors']}")
        time.sleep(0.3)
        return data

    def fixtures(self, league_id: int, season: int, date_from: str, date_to: str):
        return self._get("/fixtures", league=league_id, season=season, **{"from": date_from, "to": date_to})["response"]

    def odds(self, league_id: int, season: int, date: str | None = None):
        out, page = [], 1
        while True:
            params = dict(league=league_id, season=season, page=page)
            if date:
                params["date"] = date
            d = self._get("/odds", **params)
            out += d["response"]
            if page >= d.get("paging", {}).get("total", 1):
                return out
            page += 1

    def parse(self, league: str, odds_resp, fixtures_resp) -> pd.DataFrame:
        fx = {f["fixture"]["id"]: f for f in fixtures_resp}
        rows = []
        for item in odds_resp:
            f = fx.get(item["fixture"]["id"])
            if not f:
                continue
            base = [league, to_local(f["fixture"]["date"]),
                    f["teams"]["home"]["name"], f["teams"]["away"]["name"]]
            for bm in item.get("bookmakers", []):
                book = self.BOOKS.get(bm["name"].lower(), re.sub(r"\W+", "_", bm["name"].lower()).strip("_"))
                for bet in bm.get("bets", []):
                    fn = self.BET_MAP.get(bet["name"])
                    if not fn:
                        continue
                    for v in bet.get("values", []):
                        mk = fn(str(v["value"]))
                        if mk:
                            rows.append(base + [book, mk, float(v["odd"]), "api-football"])
        return pd.DataFrame(rows, columns=COLS)


def _ou(v: str, prefix: str) -> str | None:
    m = re.match(r"(Over|Under)\s+([\d.]+)", v)
    return f"{prefix}{m.group(1).lower()}_{float(m.group(2))}" if m else None
