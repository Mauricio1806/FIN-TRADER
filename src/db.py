"""SQLite schema e helpers, com auto-migração de schema legado."""
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

EXPECTED_SIGNALS_COLS = {
    "id", "ts_utc", "window", "ticker", "region", "score", "classification",
    "layers_json", "price", "atr", "suggested_alloc_pct", "stop_pct",
    "target_pct", "data_hash", "model_version",
}


def _schema_compatible() -> bool:
    """Verifica se o DB existente tem schema compatível com v0.2."""
    if not DB_PATH.exists():
        return True
    try:
        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='signals'"
            )
            if not cur.fetchone():
                return True
            cur = c.execute("PRAGMA table_info(signals)")
            cols = {r[1] for r in cur.fetchall()}
        return EXPECTED_SIGNALS_COLS.issubset(cols)
    except Exception:
        return False


def init_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    if not _schema_compatible():
        backup = DB_PATH.with_suffix(".legacy.db")
        try:
            if backup.exists():
                backup.unlink()
            DB_PATH.rename(backup)
            print(f"[db] schema legado detectado; movido para {backup.name}")
        except Exception:
            try:
                DB_PATH.unlink()
                print("[db] schema legado removido")
            except Exception:
                pass
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
