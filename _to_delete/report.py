"""Write the shortlist as a simple self-contained HTML page."""
from __future__ import annotations

import html

import pandas as pd

LABELS = {
    "home_win": "Home win", "away_win": "Away win", "draw": "Draw",
    "dc_1X": "Double chance 1X", "dc_X2": "Double chance X2", "dc_12": "Double chance 12",
    "dnb_home": "Draw no bet - home", "dnb_away": "Draw no bet - away",
    "btts_yes": "BTTS yes", "btts_no": "BTTS no",
}


def label(mk: str) -> str:
    if mk in LABELS:
        return LABELS[mk]
    parts = mk.split("_")
    if mk.startswith("1h_"):
        return f"1st half {parts[1]} {parts[2]} goals"
    if mk.startswith("corners_"):
        return f"Corners {parts[1]} {parts[2]}"
    return f"Goals {parts[0]} {parts[1]}"


def write_html(df: pd.DataFrame, path: str, cfg: dict) -> None:
    v = cfg["value"]
    picks = df[df["value"]] if not df.empty else df
    checks = df[df["check"]] if not df.empty else df
    body = _rows(picks) or "<tr><td colspan=12>No selections met the value threshold.</td></tr>"
    check_body = _rows(checks) or "<tr><td colspan=12>None.</td></tr>"
    page = _PAGE.format(n=len(picks), min_edge=f"{v['min_edge']:.0%}", max_edge=f"{v['max_edge']:.0%}",
                        min_odds=v["min_odds"], max_odds=v["max_odds"], kelly=f"{v['kelly_fraction']:g}",
                        body=body, check_body=check_body)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def _rows(picks: pd.DataFrame) -> str:
    rows = []
    for _, r in picks.iterrows():
        mp = f"{r['market_prob']:.0%}" if pd.notna(r["market_prob"]) else "-"
        rows.append(
            f"<tr><td>{html.escape(str(r['kickoff']))}</td><td>{r['league']}</td>"
            f"<td>{html.escape(r['match'])}</td><td>{label(r['market'])}</td>"
            f"<td>{r['bookmaker']}</td><td class=n>{r['best_odds']:.2f}</td><td class=n>{r['fair_odds']:.2f}</td>"
            f"<td class=n>{r['model_prob']:.0%}</td><td class=n>{mp}</td>"
            f"<td class='n e'>{r['edge']:+.0%}</td><td class=n>{r['stake_pct']:.1f}%</td><td>{r['xg']}</td></tr>")
    return "\n".join(rows)


_HEAD = """<tr><th>Kick-off</th><th>League</th><th>Match</th><th>Market</th><th>Bookmaker</th>
<th class=n>Odds</th><th class=n>Fair odds</th><th class=n>Model</th><th class=n>Market</th>
<th class=n>Edge</th><th class=n>Stake</th><th>xG</th></tr>"""

_PAGE = """<!doctype html><html><head><meta charset=utf-8><title>SportsStats shortlist</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;color:#1d1d1f;background:#fff}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin-bottom:32px}}
th,td{{padding:6px 10px;border-bottom:1px solid #e5e5e5;text-align:left}}
th{{background:#f5f5f7}} .n{{text-align:right}} .e{{font-weight:600;color:#0a7d34}}
p.note{{color:#666;font-size:13px}}
</style></head><body>
<h1>Value shortlist</h1>
<p class=note>{n} selections with edge {min_edge} to {max_edge} and odds {min_odds}-{max_odds}.
Fair odds = 1 / model probability. Market = bookmakers' average price with the margin removed.
Stake = {kelly} Kelly, as % of bankroll (for information only).</p>
<table><thead>""" + _HEAD + """</thead><tbody>{body}</tbody></table>
<h2>Check manually</h2>
<p class=note>Edge above {max_edge}. Usually the model is missing news (injuries, suspensions, rotation) -
check team news on Flashscore / SofaScore before treating any of these as value.</p>
<table><thead>""" + _HEAD + """</thead><tbody>{check_body}</tbody></table>
</body></html>"""
