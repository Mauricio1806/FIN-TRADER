from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

LOGGER = logging.getLogger(__name__)


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(db_path: str = "db/signals.db") -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                score REAL NOT NULL,
                classification TEXT NOT NULL,
                top_layers TEXT NOT NULL,
                data_hash TEXT NOT NULL UNIQUE
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);")
        conn.commit()


def _hash_signal(signal: Dict) -> str:
    payload = {
        "ticker": signal["ticker"],
        "timestamp": signal["timestamp"],
        "score": round(float(signal["score"]), 6),
        "classification": signal["classification"],
        "top_layers": signal.get("top_layers", []),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def save_signals(signals: List[Dict], db_path: str = "db/signals.db") -> int:
    if not signals:
        return 0

    init_db(db_path)
    inserted = 0

    with _connect(db_path) as conn:
        for s in signals:
            data_hash = _hash_signal(s)
            try:
                conn.execute(
                    """
                    INSERT INTO signals (ticker, timestamp, score, classification, top_layers, data_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        s["ticker"],
                        s["timestamp"],
                        float(s["score"]),
                        s["classification"],
                        json.dumps(s.get("top_layers", []), ensure_ascii=False),
                        data_hash,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                LOGGER.info("Registro já existente (idempotência): %s %s", s["ticker"], s["timestamp"])
        conn.commit()

    return inserted


def get_historical_avg(db_path: str = "db/signals.db", days: int = 90) -> Dict:
    init_db(db_path)
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT AVG(score) as avg_score,
                   COUNT(*) as count_score,
                   COALESCE(SQRT(AVG(score * score) - AVG(score) * AVG(score)), 0) as std_score
            FROM signals
            WHERE timestamp >= ?
            """,
            (cutoff,),
        ).fetchone()

    return {
        "avg": float(row[0]) if row and row[0] is not None else 0.0,
        "count": int(row[1]) if row and row[1] is not None else 0,
        "std": float(row[2]) if row and row[2] is not None else 0.0,
    }
