"""Run the analysis on this computer and print the shortlist (the website does this automatically).

    python run.py
    python run.py --days 1 --leagues EPL LIGUE1 --no-extra
"""
import argparse

from sportsstats.config import load_config
from sportsstats.pipeline import analyse


def main():
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=cfg["site"]["days_ahead"])
    ap.add_argument("--leagues", nargs="*", default=list(cfg["leagues"]))
    ap.add_argument("--no-extra", action="store_true")
    a = ap.parse_args()
    r = analyse(cfg, a.leagues, a.days, not a.no_extra)
    t = r["table"]
    picks = t[t["value"]] if not t.empty else t
    print(f"\n{r['matches']} matches analysed, {len(t)} priced markets, {len(picks)} value picks.")
    if not picks.empty:
        print(picks[["kickoff", "match", "market", "bookmaker", "best_odds", "fair_odds", "edge"]].to_string(index=False))


if __name__ == "__main__":
    main()
