"""Render the daily results as a static website in docs/ (served by GitHub Pages).

docs/index.html          latest day
docs/days/<date>.html    each day's page (archive)
docs/data/<date>.json    the full priced-markets table, for results tracking later
"""
from __future__ import annotations

import html
import json
from datetime import datetime

import pandas as pd

from .config import ROOT

DOCS = ROOT / "docs"

LABELS = {
    "home_win": "Home win", "away_win": "Away win", "draw": "Draw",
    "dc_1X": "Double chance 1X", "dc_X2": "Double chance X2", "dc_12": "Double chance 12",
    "dnb_home": "Draw no bet: home", "dnb_away": "Draw no bet: away",
    "btts_yes": "BTTS yes", "btts_no": "BTTS no",
}
BOOK_NAMES = {"betfair_ex_uk": "Betfair Exchange", "betfair_sb_uk": "Betfair Sportsbook", "bet365": "bet365",
              "williamhill": "William Hill", "skybet": "Sky Bet", "paddypower": "Paddy Power",
              "ladbrokes_uk": "Ladbrokes", "coral": "Coral", "betfred_uk": "Betfred", "betvictor": "BetVictor",
              "sport888": "888sport", "betway": "Betway", "boylesports": "BoyleSports", "unibet_uk": "Unibet",
              "virginbet": "Virgin Bet", "livescorebet": "LiveScore Bet", "betano_uk": "Betano", "leovegas": "LeoVegas",
              "casumo": "Casumo", "grosvenor": "Grosvenor", "smarkets": "Smarkets", "matchbook": "Matchbook",
              "pinnacle": "Pinnacle"}


def label(mk: str) -> str:
    if mk in LABELS:
        return LABELS[mk]
    p = mk.split("_")
    if mk.startswith("1h_"):
        return f"1st half {p[1]} {p[2]}"
    if mk.startswith("corners_"):
        return f"Corners {p[1]} {p[2]}"
    return f"Goals {p[0]} {p[1]}"


def book(b: str) -> str:
    return BOOK_NAMES.get(b, b.replace("_", " ").title())


def e(x) -> str:
    return html.escape(str(x))


def _kick(k: str) -> str:
    try:
        return datetime.strptime(k[:16], "%Y-%m-%d %H:%M").strftime("%H:%M")
    except ValueError:
        return ""


def _day_label(day: str, today: str) -> str:
    d = datetime.strptime(day, "%Y-%m-%d")
    rel = {0: "Today · ", 1: "Tomorrow · "}.get((d - datetime.strptime(today, "%Y-%m-%d")).days, "")
    return rel + d.strftime("%A %d %B")


def _by_day(df: pd.DataFrame, today: str, render_rows, wrap_cls: str) -> str:
    """One section per date (header), rows inside ordered by kick-off time."""
    out = []
    df = df.assign(_day=df["kickoff"].str[:10])
    for day, g in df.groupby("_day", sort=True):
        out.append(f'<section class="day"><h3 class="dayh">{e(_day_label(day, today))}</h3>'
                   f'<div class="{wrap_cls}">{render_rows(g)}</div></section>')
    return "".join(out)


def _net(r) -> str:
    n = r.get("net_odds")
    return f"<br>net {n:.2f}" if n is not None and pd.notna(n) and abs(n - r["best_odds"]) > 0.005 else ""


def _pick_card(r, cls="") -> str:
    mp = f"{r['market_prob']:.0%}" if pd.notna(r["market_prob"]) else "–"
    return f"""<article class="pick {cls}" data-league="{e(r['league'])}">
  <div class="pick-top"><span class="lg">{e(r['league'])}</span><span class="ko">{e(_kick(r['kickoff']))}</span></div>
  <h3>{e(r['match'])}</h3>
  <div class="mk">{e(label(r['market']))}</div>
  <dl>
    <div><dt>Best odds</dt><dd class="big">{r['best_odds']:.2f}</dd><dd class="sub">{e(book(r['bookmaker']))}{_net(r)}</dd></div>
    <div><dt>Fair odds</dt><dd class="big">{r['fair_odds']:.2f}</dd><dd class="sub">model {r['model_prob']:.0%}</dd></div>
    <div><dt>Edge</dt><dd class="big edge">{r['edge']:+.0%}</dd><dd class="sub">market {mp}</dd></div>
  </dl>
  <div class="foot">xG {e(r['xg'])} · stake {r['stake_pct']:.1f}% · {int(r['books_quoting'])} bookmaker(s)</div>
</article>"""


def _match_block(g: pd.DataFrame) -> str:
    first = g.iloc[0]
    n_val = int(g["value"].sum())
    badge = f'<span class="badge">{n_val} value</span>' if n_val else ""
    rows = []
    for _, r in g.sort_values("market").iterrows():
        cls = "v" if r["value"] else ("c" if r["check"] else "")
        rows.append(f"<tr class='{cls}'><td>{e(label(r['market']))}</td><td class=n>{r['model_prob']:.0%}</td>"
                    f"<td class=n>{r['fair_odds']:.2f}</td><td class=n>{r['best_odds']:.2f}</td>"
                    f"<td>{e(book(r['bookmaker']))}</td><td class=n>{r['edge']:+.0%}</td></tr>")
    return f"""<details class="match" data-league="{e(first['league'])}">
<summary><span class="ko">{e(_kick(first['kickoff']))}</span><span class="lgt">{e(first['league'])}</span><span class="teams">{e(first['match'])}</span>
<span class="xg">xG {e(first['xg'])}</span>{badge}</summary>
<div class="tw"><table><thead><tr><th>Market</th><th class=n>Model</th><th class=n>Fair</th><th class=n>Best</th>
<th>Bookmaker</th><th class=n>Edge</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></details>"""


def render(result: dict, cfg: dict, archive: list[str]) -> str:
    t = result["table"]
    v = cfg["value"]
    title = cfg["site"]["title"]
    has = not t.empty
    picks = t[t["value"]] if has else t
    checks = t[t["check"]] if has else t
    leagues = sorted(t["league"].unique()) if has else []
    names = {k: L["name"] for k, L in cfg["leagues"].items()}

    today = result["date"]

    def cards(cls=""):
        return lambda g: "".join(_pick_card(r, cls) for _, r in
                                 g.sort_values(["kickoff", "match", "edge"], ascending=[True, True, False]).iterrows())

    pick_html = _by_day(picks, today, cards(), "grid") or \
        '<p class="empty">No selections met the value threshold today.</p>'
    check_html = _by_day(checks, today, cards("chk"), "grid") or '<p class="empty">None.</p>'
    match_html = _by_day(t, today, lambda g: "".join(
        _match_block(m) for _, m in g.groupby(["kickoff", "league", "match"], sort=True)), "list") if has else ""
    chips = '<button class="chip on" data-f="all">All</button>' + "".join(
        f'<button class="chip" data-f="{e(l)}" title="{e(names.get(l, l))}">{e(l)}</button>' for l in leagues)
    src = " · ".join(f"{e(k)}: {e(s)}" for k, s in result["sources"].items())
    skipped = "".join(f"<li>{e(s)}</li>" for s in result["skipped"][:40])
    arch = "".join(f'<a href="days/{d}.html">{e(d)}</a>' for d in archive)
    gen = result["generated"].replace("T", " ")[:16]

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}: {e(result['date'])}</title>
<style>
:root{{--bg:#f7f7f5;--card:#fff;--ink:#1c1c1a;--mute:#6b6b66;--line:#e4e3de;--acc:#0b7a3b;--accbg:#e5f4ea;--warn:#9a6200;--warnbg:#fbf1dc}}
@media (prefers-color-scheme:dark){{:root{{--bg:#131412;--card:#1c1d1b;--ink:#ecebe6;--mute:#9a9a93;--line:#2e2f2c;--acc:#4cc27c;--accbg:#173222;--warn:#e0a84a;--warnbg:#33290f}}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:20px 16px 60px}}
header h1{{margin:0;font-size:24px}} .src{{font-size:12px}} header p{{margin:4px 0 0;color:var(--mute);font-size:13px}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:120px}}
.stat b{{display:block;font-size:22px}} .stat span{{color:var(--mute);font-size:12px}}
h2{{font-size:18px;margin:28px 0 10px}} h2 small{{color:var(--mute);font-weight:400;font-size:13px}}
.chips{{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 4px}}
.chip{{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:99px;padding:5px 12px;font-size:13px;cursor:pointer}}
.chip.on{{background:var(--ink);color:var(--bg);border-color:var(--ink)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px}}
.pick{{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:10px;padding:12px 14px}}
.pick.chk{{border-left-color:var(--warn)}}
.pick-top{{display:flex;justify-content:space-between;font-size:12px;color:var(--mute)}}
.lg{{font-weight:600;letter-spacing:.03em}} .pick h3{{margin:4px 0 2px;font-size:16px}}
.mk{{font-weight:600;color:var(--acc)}} .chk .mk{{color:var(--warn)}}
dl{{display:grid;grid-template-columns:repeat(3,1fr);margin:10px 0 6px;gap:6px}} dl div{{margin:0}}
dt{{font-size:11px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}} dd{{margin:0}}
.big{{font-size:20px;font-weight:650;font-variant-numeric:tabular-nums}} .edge{{color:var(--acc)}} .chk .edge{{color:var(--warn)}}
.sub{{font-size:12px;color:var(--mute)}} .foot{{font-size:12px;color:var(--mute);border-top:1px solid var(--line);padding-top:6px}}
.empty{{color:var(--mute)}}
@media (max-width:600px){{header h1{{font-size:20px}} .stat{{min-width:0;flex:1 1 40%}}}}
.dayh{{font-size:14px;margin:18px 0 8px;padding-bottom:4px;border-bottom:1px solid var(--line);color:var(--mute);text-transform:uppercase;letter-spacing:.05em}}
.lgt{{font-size:11px;font-weight:600;color:var(--mute);border:1px solid var(--line);border-radius:4px;padding:0 5px;letter-spacing:.03em}}
.match{{background:var(--card);border:1px solid var(--line);border-radius:8px;margin-bottom:6px}}
.match summary{{display:flex;gap:12px;align-items:center;padding:9px 12px;cursor:pointer;flex-wrap:wrap}}
.match .ko{{color:var(--mute);font-size:13px;min-width:44px;font-variant-numeric:tabular-nums}} .teams{{font-weight:600;flex:1}} .xg{{color:var(--mute);font-size:13px}}
.badge{{background:var(--accbg);color:var(--acc);border-radius:99px;padding:1px 8px;font-size:12px;font-weight:600}}
.tw{{overflow-x:auto;padding:0 12px 10px}}
table{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}}
th,td{{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}} th{{color:var(--mute);font-weight:500}}
.n{{text-align:right}} tr.v td{{background:var(--accbg)}} tr.c td{{background:var(--warnbg)}}
.note{{color:var(--mute);font-size:13px}} .arch a{{display:inline-block;margin:0 10px 6px 0;color:var(--ink)}}
details.info{{margin-top:28px;color:var(--mute);font-size:13px}}
</style></head><body><main>
<header><h1>{e(title)} · {e(datetime.strptime(result['date'], '%Y-%m-%d').strftime('%A %d %B %Y'))}</h1>
<p>Updated {e(gen)} UTC · kick-offs in Paris time · next {cfg['site']['days_ahead']} days of fixtures</p>
<p class="src">{src}</p></header>
<div class="stats">
<div class="stat"><b>{len(picks)}</b><span>value picks</span></div>
<div class="stat"><b>{result['matches']}</b><span>matches analysed</span></div>
<div class="stat"><b>{len(t)}</b><span>markets priced</span></div>
<div class="stat"><b>{len(checks)}</b><span>to check manually</span></div></div>
<div class="chips">{chips}</div>

<h2>Value picks <small>edge {v['min_edge']:.0%}–{v['max_edge']:.0%}, odds {v['min_odds']}–{v['max_odds']}</small></h2>
{pick_html}

<h2>Check manually <small>edge above {v['max_edge']:.0%}: usually the model is missing team news</small></h2>
{check_html}

<h2>All matches <small>tap a match for every market</small></h2>
{match_html or '<p class="empty">No matches with odds in this window.</p>'}

<h2>Previous days</h2><div class="arch">{arch}</div>

<details class="info"><summary>How to read this page</summary>
<p><b>Fair odds</b> = 1 ÷ model probability. <b>Best odds</b> = highest UK price (bookmakers and Betfair Exchange). Exchange prices are compared after commission (shown as <b>net</b>).
<b>Edge</b> = model probability × best odds (after any commission) − 1. <b>Market</b> = the bookmakers' average price with their margin removed.
<b>Stake</b> = {v['kelly_fraction']:g} Kelly as % of bankroll, for guidance only. <b>xG</b> = model's expected goals, home–away.
The model knows nothing about injuries, suspensions or rotation.</p>
<p>Sources: {src}</p><ul>{skipped}</ul></details>
</main>
<script>
document.querySelectorAll('.chip').forEach(b=>b.onclick=()=>{{
 document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',c===b));
 const f=b.dataset.f;
 document.querySelectorAll('[data-league]').forEach(el=>{{ if(!el.classList.contains('chip')) el.style.display=(f==='all'||el.dataset.league===f)?'':'none'; }});
 document.querySelectorAll('section.day').forEach(sec=>{{ sec.style.display=[...sec.querySelectorAll('[data-league]')].some(x=>x.style.display!=='none')?'':'none'; }});
}});
</script></body></html>"""


def write_site(result: dict, cfg: dict) -> None:
    day = result["date"]
    (DOCS / "days").mkdir(parents=True, exist_ok=True)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    t = result["table"]
    payload = {k: v for k, v in result.items() if k != "table"}
    payload["rows"] = json.loads(t.to_json(orient="records")) if not t.empty else []
    (DOCS / "data" / f"{day}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")

    keep = cfg["site"]["archive_days"]
    days = sorted({p.stem for p in (DOCS / "data").glob("*.json")}, reverse=True)
    for old in days[keep:]:
        for p in (DOCS / "data" / f"{old}.json", DOCS / "days" / f"{old}.html"):
            p.unlink(missing_ok=True)
    days = days[:keep]

    page = render(result, cfg, days)
    (DOCS / "days" / f"{day}.html").write_text(page.replace('href="days/', 'href="'), encoding="utf-8")
    (DOCS / "index.html").write_text(page, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
