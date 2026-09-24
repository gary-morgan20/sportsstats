"""The daily analysis: collect odds -> fit models -> price every market -> value table."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from .config import api_key
from .model import LeagueModels
from .sources import football_data as fd
from .sources.odds import APIFootball, OddsAPI, from_football_data
from .teams import TeamMatcher
from .value import find_value


def collect_offers(cfg, leagues, start, end, extra: bool, log=print) -> tuple[pd.DataFrame, dict]:
    frames, status = [], {}
    fd_map = {v["fd"]: k for k, v in cfg["leagues"].items() if v.get("fd") and k in leagues}

    try:
        frames.append(from_football_data(fd.load_fixtures(), fd_map))
        status["football-data"] = "ok"
    except Exception as e:  # noqa: BLE001
        status["football-data"] = f"failed: {e}"
    log(f"football-data fixtures: {status['football-data']}")

    if key := api_key("ODDS_API_KEY"):
        api = OddsAPI(key, cfg["odds"]["odds_api_regions"])
        reserve = cfg["odds"].get("odds_api_reserve_credits", 50)
        for lg in leagues:
            sport = cfg["leagues"][lg]["odds_api"]
            try:
                events = [e for e in api.featured(sport) if start <= e["commence_time"][:10] <= end]
                frames.append(OddsAPI.parse(lg, events))
                for ev in events if extra else []:
                    if api.remaining is not None and float(api.remaining) < reserve:
                        log("  The Odds API: credit reserve reached, skipping extra markets")
                        extra = False
                        break
                    frames.append(OddsAPI.parse(lg, api.event(sport, ev["id"])))
            except Exception as e:  # noqa: BLE001
                log(f"  The Odds API {lg}: {e}")
        status["the-odds-api"] = f"ok, {api.remaining} credits left"
        log(f"The Odds API: {status['the-odds-api']}")

    if key := api_key("API_FOOTBALL_KEY"):
        af = APIFootball(key)
        season = int("20" + cfg["history"]["current_season"][:2])
        for lg in leagues:
            lid = cfg["leagues"][lg]["api_football"]
            try:
                fx = af.fixtures(lid, season, start, end)
                if fx:
                    frames.append(af.parse(lg, af.odds(lid, season), fx))
            except Exception as e:  # noqa: BLE001
                log(f"  API-Football {lg}: {e}")
        status["api-football"] = f"ok, {af.remaining} requests left today"
        log(f"API-Football: {status['api-football']}")

    frames = [f for f in frames if not f.empty]
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), status


def analyse(cfg, leagues=None, days=3, extra=True, log=print) -> dict:
    leagues = leagues or list(cfg["leagues"])
    today = datetime.now(timezone.utc).date()
    start, end = str(today), str(today + timedelta(days=days))
    offers, status = collect_offers(cfg, leagues, start, end, extra, log)
    result = {"generated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "date": start,
              "sources": status, "table": pd.DataFrame(), "matches": 0, "skipped": []}
    if offers.empty:
        return result
    offers = offers[(offers["kickoff"].str[:10] >= start) & (offers["kickoff"].str[:10] <= end)]

    h = cfg["history"]
    preds, matched = {}, []
    for lg in leagues:
        lo = offers[offers["league"] == lg].copy()
        if lo.empty:
            continue
        code = cfg["leagues"][lg].get("fd")
        if not code:
            result["skipped"].append(f"{cfg['leagues'][lg]['name']}: no statistical history source yet")
            continue
        log(f"{lg}: fitting models")
        models = LeagueModels.build(fd.load_results(code, h["current_season"], h["seasons_back"]),
                                    h["decay_half_life_days"])
        if not models.ft:
            continue
        tm = TeamMatcher(models.ft.teams)
        lo["home"] = lo["home_src"].map(tm.match)
        lo["away"] = lo["away_src"].map(tm.match)
        tm.save_unmatched(lg)
        if tm.unmatched:
            result["skipped"].append(f"{lg}: unmatched team names {sorted(tm.unmatched)}")
        lo = lo.dropna(subset=["home", "away"])
        lo["match_id"] = lg + "|" + lo["kickoff"].str[:10] + "|" + lo["home"] + "|" + lo["away"]
        lo["kickoff"] = lo.groupby("match_id")["kickoff"].transform("min")
        for mid, g in lo.groupby("match_id"):
            p = models.predict(g["home"].iloc[0], g["away"].iloc[0], cfg["value"]["min_matches_per_team"])
            if p:
                preds[mid] = p
            else:
                result["skipped"].append(f"{g['home'].iloc[0]} v {g['away'].iloc[0]}: not enough history")
        matched.append(lo)

    if matched:
        result["table"] = find_value(pd.concat(matched, ignore_index=True), preds, cfg)
        result["matches"] = len(preds)
    return result
