"""Loader de configuração: watchlist, pesos, env vars."""
import os
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DB_DIR = ROOT / "db"
REPORTS_DIR = ROOT / "reports"


def load_watchlist() -> dict:
    with open(CONFIG_DIR / "watchlist.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_weights() -> dict:
    with open(CONFIG_DIR / "weights.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def active_tickers_by_region(wl: dict) -> dict[str, list[str]]:
    out = {}
    for region in ("br", "us", "eu", "asia"):
        out[region] = [t["symbol"] for t in wl[region]["tickers"] if t.get("active", True)]
    return out


def all_active_tickers(wl: dict) -> list[tuple[str, str]]:
    out = []
    for region in ("br", "us", "eu", "asia"):
        for t in wl[region]["tickers"]:
            if t.get("active", True):
                out.append((t["symbol"], region))
    return out


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


DB_PATH = DB_DIR / "signals.db"
