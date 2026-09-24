"""Check which leagues, markets and bookmakers each data source actually returns.

    python probe.py                       # probes EPL, CHAMP, LIGUE1 on the odds APIs
    python probe.py --leagues EPL L2 EREDIVISIE

Uses few API credits: The Odds API ~ (2 + up to 7 extra markets) x regions per league.
Writes output/coverage_report.md.
"""
from __future__ import annotations

import argparse
from collections import defaultdict

from sportsstats.config import OUTPUT_DIR, api_key, load_config
from sportsstats.sources import football_data as fd
from sportsstats.sources.odds import APIFootball, OddsAPI, _save_raw
from sportsstats.value import market_group


def main():
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="*", default=["EPL", "CHAMP", "LIGUE1"])
    args = ap.parse_args()
    out = ["# Data coverage report", ""]

    # --- statistical history
    out += ["## football-data.co.uk (history)", "",
            "| League | Matches | Half-time goals | Corners | Closing odds 1X2 | Closing odds O/U 2.5 |",
            "|---|---|---|---|---|---|"]
    h = cfg["history"]
    for lg, L in cfg["leagues"].items():
        if not L.get("fd"):
            out.append(f"| {lg} | not covered | | | | |")
            continue
        try:
            df = fd.load_results(L["fd"], h["current_season"], h["seasons_back"])
        except Exception as e:  # noqa: BLE001
            out.append(f"| {lg} | error: {e} | | | | |")
            continue

        def pct(col):
            return f"{df[col].notna().mean():.0%}" if col in df else "no"
        out.append(f"| {lg} | {len(df)} | {pct('HTHG')} | {pct('HC')} | {pct('PSCH') if 'PSCH' in df else pct('AvgCH')} "
                   f"| {pct('AvgC>2.5')} |")
        print(f"history {lg}: {len(df)} matches")

    # --- The Odds API
    if key := api_key("ODDS_API_KEY"):
        api = OddsAPI(key, cfg["odds"]["odds_api_regions"])
        out += ["", "## The Odds API", ""]
        for lg in args.leagues:
            sport = cfg["leagues"][lg]["odds_api"]
            try:
                events = api.featured(sport)
                _save_raw(f"oddsapi_{lg}_featured", events)
                df = OddsAPI.parse(lg, events)
                extra_df = None
                if events:
                    ev = api.event(sport, events[0]["id"])
                    _save_raw(f"oddsapi_{lg}_event", ev)
                    extra_df = OddsAPI.parse(lg, ev)
                out += [f"### {lg}: {len(events)} upcoming matches", ""]
                out += _summarise(df, "Featured markets (all matches)")
                if extra_df is not None:
                    out += _summarise(extra_df, f"Extra markets (sample match: {events[0]['home_team']} v {events[0]['away_team']})")
                print(f"odds-api {lg}: ok")
            except Exception as e:  # noqa: BLE001
                out += [f"### {lg}: error {e}", ""]
        out.append(f"Credits remaining: {api.remaining}")
    else:
        out += ["", "## The Odds API", "", "No ODDS_API_KEY in .env - skipped."]

    # --- API-Football
    if key := api_key("API_FOOTBALL_KEY"):
        af = APIFootball(key)
        season = int("20" + h["current_season"][:2])
        out += ["", "## API-Football", ""]
        for lg in args.leagues:
            lid = cfg["leagues"][lg]["api_football"]
            try:
                resp = af.odds(lid, season)
                _save_raw(f"apifootball_{lg}_odds", resp)
                bets, books = defaultdict(set), set()
                for item in resp:
                    for bm in item.get("bookmakers", []):
                        books.add(bm["name"])
                        for b in bm.get("bets", []):
                            bets[b["name"]].add(bm["name"])
                out += [f"### {lg}: odds for {len(resp)} matches", "",
                        f"Bookmakers: {', '.join(sorted(books)) or 'none'}", "",
                        "| Bet type | Bookmakers quoting |", "|---|---|"]
                out += [f"| {b} | {len(s)} |" for b, s in sorted(bets.items())]
                out.append("")
                print(f"api-football {lg}: ok")
            except Exception as e:  # noqa: BLE001
                out += [f"### {lg}: error {e}", ""]
        out.append(f"Requests remaining today: {af.remaining}")
    else:
        out += ["", "## API-Football", "", "No API_FOOTBALL_KEY in .env - skipped."]

    OUTPUT_DIR.mkdir(exist_ok=True)
    p = OUTPUT_DIR / "coverage_report.md"
    p.write_text("\n".join(out), encoding="utf-8")
    print(f"\nWritten {p}")


def _summarise(df, title):
    if df.empty:
        return [f"**{title}:** nothing returned", ""]
    df = df.assign(group=df["market"].map(lambda m: market_group(m) or m))
    lines = [f"**{title}**", "", "| Your market | Outcomes seen | Bookmakers |", "|---|---|---|"]
    for grp, g in df.groupby("group"):
        lines.append(f"| {grp} | {', '.join(sorted(g['market'].unique())[:8])} | {', '.join(sorted(g['bookmaker'].unique()))} |")
    return lines + [""]


if __name__ == "__main__":
    main()
