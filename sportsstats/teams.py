"""Match team names across sources ("Man United" vs "Manchester United FC").

Unmatched names are written to data/unmatched_teams.txt; add them to team_aliases.yaml
(e.g.  "Manchester United": "Man United") using the football-data.co.uk spelling as the value.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

import yaml

from .config import DATA_DIR, ROOT

_STOP = {"fc", "cf", "afc", "sc", "ac", "as", "ss", "us", "sv", "vfb", "vfl", "rc", "cd", "ud", "sd",
         "fk", "sk", "club", "de", "calcio", "the", "1", "04", "05", "1846", "1899", "1900", "1907"}
_SUBS = {"manchester": "man", "united": "utd", "saint": "st", "wolverhampton": "wolves",
         "wanderers": "", "hotspur": "", "albion": "", "athletic": "ath", "borussia": "",
         "internazionale": "inter", "munchen": "munich", "sporting": "sp", "olympique": ""}


def _aliases() -> dict[str, str]:
    p = ROOT / "team_aliases.yaml"
    if p.exists():
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    words = [_SUBS.get(w, w) for w in s.split() if w not in _STOP]
    return " ".join(w for w in words if w)


class TeamMatcher:
    def __init__(self, known: list[str]):
        self.known = list(known)
        self.by_norm = {norm(k): k for k in self.known}
        self.aliases = _aliases()
        self.unmatched: set[str] = set()

    def match(self, name: str) -> str | None:
        if name in self.known:
            return name
        if name in self.aliases:
            return self.aliases[name]
        n = norm(name)
        if n in self.by_norm:
            return self.by_norm[n]
        # one name contained in the other ("psg" / "paris sg") - only if that points to exactly one team,
        # so "Ireland" can never be matched to "Northern Ireland" by accident
        hits = {k for k_norm, k in self.by_norm.items() if n and k_norm and (n in k_norm or k_norm in n)}
        if len(hits) == 1:
            return hits.pop()
        if len(hits) > 1:
            self.unmatched.add(name)
            return None
        close = difflib.get_close_matches(n, list(self.by_norm), n=1, cutoff=0.75)
        if close:
            return self.by_norm[close[0]]
        self.unmatched.add(name)
        return None

    def save_unmatched(self, league: str) -> None:
        if not self.unmatched:
            return
        DATA_DIR.mkdir(exist_ok=True)
        with open(DATA_DIR / "unmatched_teams.txt", "a", encoding="utf-8") as f:
            for u in sorted(self.unmatched):
                f.write(f"{league}\t{u}\n")
