"""Paper trading em % de portfólio. Sem capital fixo."""
import json
from datetime import datetime
from .db import conn

REGION_CAPS = {"br": 40.0, "us": 20.0, "eu": 10.0, "asia": 10.0}
MAX_TOTAL_EXPOSURE = 70.0
MIN_POS = 1.0
MAX_POS = 8.0


def open_positions_summary() -> dict:
    with conn() as c:
        rows = c.execute(
            "SELECT region, SUM(entry_alloc_pct) as alloc FROM positions_simulated "
            "WHERE status='open' GROUP BY region"
        ).fetchall()
    by_region = {r["region"]: r["alloc"] or 0 for r in rows}
    total = sum(by_region.values())
    return {"by_region": by_region, "total": total, "cash": max(0, 100 - total)}


def can_open(region: str, alloc_pct: float) -> bool:
    summary = open_positions_summary()
    region_cap = REGION_CAPS.get(region, 5.0)
    if summary["by_region"].get(region, 0) + alloc_pct > region_cap:
        return False
    if summary["total"] + alloc_pct > MAX_TOTAL_EXPOSURE:
        return False
    return True


def open_position(ticker, region, price, score, alloc_pct, stop_pct, target_pct):
    if alloc_pct < MIN_POS or alloc_pct > MAX_POS:
        return None
    if not can_open(region, alloc_pct):
        return None
    with conn() as c:
        c.execute(
            "INSERT INTO positions_simulated (ticker, region, entry_ts, entry_price, "
            "entry_score, entry_alloc_pct, stop_pct, target_pct, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')",
            (ticker, region, datetime.utcnow().isoformat(), price, score,
             alloc_pct, stop_pct, target_pct),
        )
    return True


def evaluate_open_positions(latest_prices: dict[str, float], latest_scores: dict[str, float]):
    """Verifica stop/target/score-flip. Retorna lista de fechamentos."""
    closures = []
    with conn() as c:
        rows = c.execute("SELECT * FROM positions_simulated WHERE status='open'").fetchall()
    for r in rows:
        t = r["ticker"]
        price = latest_prices.get(t)
        score = latest_scores.get(t, 0)
        if price is None:
            continue
        pnl_pct = (price / r["entry_price"] - 1) * 100
        reason = None
        if pnl_pct <= r["stop_pct"]:
            reason = "stop"
        elif pnl_pct >= r["target_pct"]:
            reason = "target"
        elif score < 0:
            reason = "score_flip"
        if reason:
            contrib = pnl_pct * (r["entry_alloc_pct"] / 100)
            with conn() as c:
                c.execute(
                    "UPDATE positions_simulated SET exit_ts=?, exit_price=?, exit_reason=?, "
                    "pnl_pct=?, pnl_contrib_pct=?, status='closed' WHERE id=?",
                    (datetime.utcnow().isoformat(), price, reason, pnl_pct, contrib, r["id"]),
                )
            closures.append({
                "ticker": t, "reason": reason, "pnl_pct": round(pnl_pct, 2),
                "alloc": r["entry_alloc_pct"], "contrib": round(contrib, 3),
            })
    return closures


def portfolio_metrics() -> dict:
    """Hit-rate, retorno acumulado, exposição atual."""
    with conn() as c:
        closed = c.execute(
            "SELECT pnl_pct, pnl_contrib_pct FROM positions_simulated WHERE status='closed'"
        ).fetchall()
    n = len(closed)
    if n == 0:
        return {"n_trades": 0, "hit_rate": 0, "cum_return_pct": 0, "best": 0, "worst": 0}
    wins = sum(1 for r in closed if (r["pnl_pct"] or 0) > 0)
    cum = sum((r["pnl_contrib_pct"] or 0) for r in closed)
    return {
        "n_trades": n,
        "hit_rate": round(wins / n * 100, 1),
        "cum_return_pct": round(cum, 2),
        "best": round(max((r["pnl_pct"] or 0) for r in closed), 2),
        "worst": round(min((r["pnl_pct"] or 0) for r in closed), 2),
    }
