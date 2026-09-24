"""football-data.co.uk: free historical results, half-time goals, corners and closing odds.

Files are cached in data/football_data/. Past seasons are downloaded once; the current
season and the fixtures file are refreshed if older than 12 hours.
"""
from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
import requests

from ..config import DATA_DIR

BASE = "https://www.football-data.co.uk"
CACHE = DATA_DIR / "football_data"
HEADERS = {"User-Agent": "SportsStats personal research tool"}


def season_codes(current: str, back: int) -> list[str]:
    """'2627', 3 -> ['2324', '2425', '2526', '2627']"""
    start = int(current[:2])
    return [f"{(start - i) % 100:02d}{(start - i + 1) % 100:02d}" for i in range(back, -1, -1)]


def _get(url: str, dest: Path, max_age_h: float | None) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (max_age_h is None or time.time() - dest.stat().st_mtime < max_age_h * 3600):
        return dest
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code == 404:
        return dest if dest.exists() else None
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def _read(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    df = pd.read_csv(io.StringIO(text), on_bad_lines="skip")
    df = df.dropna(axis=1, how="all")
    df = df.dropna(subset=[c for c in ("HomeTeam", "AwayTeam") if c in df.columns])
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    return df


def load_results(fd_code: str, current: str, back: int) -> pd.DataFrame:
    frames = []
    for s in season_codes(current, back):
        max_age = 12 if s == current else None
        p = _get(f"{BASE}/mmz4281/{s}/{fd_code}.csv", CACHE / s / f"{fd_code}.csv", max_age)
        if p is None:
            continue
        df = _read(p)
        df["Season"] = s
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    return df.dropna(subset=["FTHG", "FTAG"]).sort_values("Date").reset_index(drop=True)


def load_fixtures() -> pd.DataFrame:
    """Upcoming fixtures for the main leagues, with average/max odds for 1X2 and O/U 2.5."""
    p = _get(f"{BASE}/fixtures.csv", CACHE / "fixtures.csv", max_age_h=6)
    return _read(p) if p else pd.DataFrame()
