"""SQLite schema e helpers."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .config import DB_PATH, DB_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    window TEXT NOT NULL,
    ticker TEXT NOT NULL,
    region TEXT NOT NULL,
    score REAL NOT NULL,
    classification TEXT NOT NULL,
    layers_json TEXT NOT NULL,
    price REAL,
    atr REAL,
    suggested_alloc_pct REAL,
    stop_pct REAL,
    target_pct REAL,
    data_hash TEXT NOT NULL,
    model_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts_utc);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);

CREATE TABLE IF NOT EXISTS positions_simulated (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    region TEXT NOT NULL,
    entry_ts TEXT NOT NULL,
    entry_price REAL NOT NULL,
    entry_score REAL NOT NULL,
    entry_alloc_pct REAL NOT NULL,
    stop_pct REAL NOT NULL,
    target_pct REAL NOT NULL,
    exit_ts TEXT,
    exit_price REAL,
    exit_reason TEXT,
    pnl_pct REAL,
    pnl_contrib_pct REAL,
    status TEXT NOT NULL DEFAULT 'open'
);
CREATE INDEX IF NOT EXISTS idx_pos_status ON positions_simulated(status);

CREATE TABLE IF NOT EXISTS macro_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    region TEXT NOT NULL,
    indicator TEXT NOT NULL,
    value REAL,
    source TEXT,
    UNIQUE(ts_utc, region, indicator)
);

CREATE TABLE IF NOT EXISTS data_quality_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    ticker TEXT NOT NULL,
    check_type TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS daily_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    window TEXT NOT NULL,
    path TEXT NOT NULL,
    model_version TEXT NOT NULL,
    UNIQUE(ts_utc, window)
);

CREATE TABLE IF NOT EXISTS errors_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc TEXT NOT NULL,
    module TEXT NOT NULL,
    message TEXT NOT NULL
);
"""


def init_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def conn():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()
