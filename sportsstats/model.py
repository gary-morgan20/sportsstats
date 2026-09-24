"""Team-strength models that turn match history into probabilities for every market.

Goals (full time):  Dixon-Coles Poisson model with time decay. Gives a full score-line
                    grid, from which 1X2, double chance, DNB, over/under and BTTS all follow.
Goals (first half): same model fitted on half-time scores.
Corners:            attack/defence model on corners won, with over-dispersion
                    (negative binomial) because corner totals vary more than Poisson allows.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import nbinom, poisson

MAX_GOALS = 10


@dataclass
class TeamModel:
    teams: list[str]
    attack: dict[str, float]
    defence: dict[str, float]
    home_adv: float
    rho: float
    matches_per_team: dict[str, int]
    dispersion: float = 1.0  # variance / mean of match totals (corners)

    def rates(self, home: str, away: str) -> tuple[float, float]:
        lh = np.exp(self.home_adv + self.attack[home] + self.defence[away])
        la = np.exp(self.attack[away] + self.defence[home])
        return float(lh), float(la)

    def knows(self, team: str, min_matches: int) -> bool:
        return self.matches_per_team.get(team, 0) >= min_matches


def _tau(hg, ag, lh, la, rho):
    """Dixon-Coles low-score correction."""
    t = np.ones_like(lh)
    t = np.where((hg == 0) & (ag == 0), 1 - lh * la * rho, t)
    t = np.where((hg == 0) & (ag == 1), 1 + lh * rho, t)
    t = np.where((hg == 1) & (ag == 0), 1 + la * rho, t)
    t = np.where((hg == 1) & (ag == 1), 1 - rho, t)
    return t


def fit(df: pd.DataFrame, home_col: str, away_col: str, half_life_days: float,
        dixon_coles: bool = True, as_of: pd.Timestamp | None = None) -> TeamModel | None:
    df = df.dropna(subset=[home_col, away_col, "Date"])
    if as_of is not None:
        df = df[df["Date"] < as_of]
    if len(df) < 30:
        return None
    as_of = as_of or df["Date"].max() + pd.Timedelta(days=1)

    teams = sorted(set(df["HomeTeam"]) | set(df["AwayTeam"]))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    h = df["HomeTeam"].map(idx).to_numpy()
    a = df["AwayTeam"].map(idx).to_numpy()
    hg = df[home_col].to_numpy(dtype=float)
    ag = df[away_col].to_numpy(dtype=float)
    age = (as_of - df["Date"]).dt.days.to_numpy(dtype=float)
    w = 0.5 ** (age / half_life_days)

    def unpack(p):
        att = np.append(p[: n - 1], -p[: n - 1].sum())  # attacks sum to zero
        dfn = p[n - 1: 2 * n - 1]
        return att, dfn, p[2 * n - 1], (p[2 * n] if dixon_coles else 0.0)

    def nll(p):
        att, dfn, home, rho = unpack(p)
        lh = np.exp(home + att[h] + dfn[a])
        la = np.exp(att[a] + dfn[h])
        ll = poisson.logpmf(hg, lh) + poisson.logpmf(ag, la)
        if dixon_coles:
            ll = ll + np.log(np.clip(_tau(hg, ag, lh, la, rho), 1e-10, None))
        return -(w * ll).sum()

    mean_goals = np.log(max((hg.mean() + ag.mean()) / 2, 0.1))
    x0 = np.concatenate([np.zeros(n - 1), np.full(n, mean_goals), [0.2], [-0.05] if dixon_coles else []])
    bounds = [(-3, 3)] * (n - 1) + [(-3, 4)] * n + [(-1, 1)] + ([(-0.2, 0.2)] if dixon_coles else [])
    res = minimize(nll, x0, method="L-BFGS-B", bounds=bounds)
    att, dfn, home, rho = unpack(res.x)

    counts = pd.concat([df["HomeTeam"], df["AwayTeam"]]).value_counts().to_dict()
    totals = hg + ag
    disp = max(1.0, float(np.cov(totals, aweights=w) / np.average(totals, weights=w)))
    return TeamModel(teams, dict(zip(teams, att)), dict(zip(teams, dfn)), float(home), float(rho),
                     counts, disp)


def score_grid(m: TeamModel, home: str, away: str) -> np.ndarray:
    lh, la = m.rates(home, away)
    g = np.arange(MAX_GOALS + 1)
    grid = np.outer(poisson.pmf(g, lh), poisson.pmf(g, la))
    hh, aa = np.meshgrid(g, g, indexing="ij")
    grid = grid * _tau(hh, aa, np.full_like(grid, lh), np.full_like(grid, la), m.rho)
    return grid / grid.sum()


def goal_markets(grid: np.ndarray, prefix: str = "") -> dict[str, float]:
    n = grid.shape[0]
    hh, aa = np.meshgrid(range(n), range(n), indexing="ij")
    tot = hh + aa
    home, draw, away = grid[hh > aa].sum(), grid[hh == aa].sum(), grid[hh < aa].sum()
    out = {}
    if not prefix:
        out.update({
            "home_win": home, "draw": draw, "away_win": away,
            "dc_1X": home + draw, "dc_X2": draw + away, "dc_12": home + away,
            # draw no bet: stake returned on a draw, so the fair price uses p / (1 - draw)
            "dnb_home": home / (home + away), "dnb_away": away / (home + away),
            "btts_yes": grid[(hh > 0) & (aa > 0)].sum(),
        })
        out["btts_no"] = 1 - out["btts_yes"]
        lines = (1.5, 2.5, 3.5)
    else:
        lines = (0.5, 1.5)
    for line in lines:
        over = grid[tot > line].sum()
        out[f"{prefix}over_{line}"] = over
        out[f"{prefix}under_{line}"] = 1 - over
    return {k: float(v) for k, v in out.items()}


def corner_markets(m: TeamModel, home: str, away: str, lines=(8.5, 9.5, 10.5, 11.5)) -> dict[str, float]:
    lh, la = m.rates(home, away)
    mu = lh + la
    out = {"corners_expected": mu}
    for line in lines:
        k = int(np.floor(line))
        if m.dispersion > 1.05:  # negative binomial with variance = dispersion * mean
            r = mu / (m.dispersion - 1)
            under = nbinom.cdf(k, r, r / (r + mu))
        else:
            under = poisson.cdf(k, mu)
        out[f"corners_over_{line}"] = float(1 - under)
        out[f"corners_under_{line}"] = float(under)
    return out


@dataclass
class LeagueModels:
    ft: TeamModel | None
    ht: TeamModel | None
    corners: TeamModel | None

    @classmethod
    def build(cls, df: pd.DataFrame, half_life: float, as_of=None) -> "LeagueModels":
        ht = fit(df, "HTHG", "HTAG", half_life, True, as_of) if "HTHG" in df else None
        co = fit(df, "HC", "AC", half_life, False, as_of) if "HC" in df and df["HC"].notna().sum() > 100 else None
        return cls(fit(df, "FTHG", "FTAG", half_life, True, as_of), ht, co)

    def predict(self, home: str, away: str, min_matches: int) -> dict[str, float] | None:
        if not self.ft or not (self.ft.knows(home, min_matches) and self.ft.knows(away, min_matches)):
            return None
        probs = goal_markets(score_grid(self.ft, home, away))
        lh, la = self.ft.rates(home, away)
        probs.update({"xg_home": lh, "xg_away": la})
        if self.ht and home in self.ht.attack and away in self.ht.attack:
            probs.update(goal_markets(score_grid(self.ht, home, away), prefix="1h_"))
        if self.corners and home in self.corners.attack and away in self.corners.attack:
            probs.update(corner_markets(self.corners, home, away))
        return probs
