"""Orquestrador FIN-TRADER. Entry-point dos workflows."""
import argparse
import json
import logging
from datetime import datetime
from .config import (
    load_watchlist, load_weights, all_active_tickers,
    active_tickers_by_region, DB_PATH,
)
from .db import init_db, conn
from .collector import fetch_prices, data_hash
from .scorer import score_ticker
from .macro import collect_macro
from .portfolio import (
    evaluate_open_positions, open_position, portfolio_metrics,
    open_positions_summary,
)
from .quality import check_data_quality
from .brief import generate_brief
from .notifier import notify_brief
from . import __version__

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fin-trader")


def build_agenda(window: str, macro: dict) -> list[str]:
    """Agenda do próximo pregão. Conservadora: combina padrões fixos + sinais macro."""
    items = []
    now = datetime.now()
    weekday = now.weekday()
    next_day_label = "amanhã" if weekday < 4 else "segunda"

    if macro["br"].get("selic") and macro["br"]["selic"] > 13:
        items.append(f"Selic em {macro['br']['selic']:.2f}% — monitorar cenário fiscal e Focus")
    if macro["us"].get("vix") and macro["us"]["vix"] > 22:
        items.append(f"VIX em {macro['us']['vix']:.1f} — volatilidade elevada nos EUA")
    if macro["br"].get("usdbrl"):
        items.append(f"USD/BRL em {macro['br']['usdbrl']:.4f} — atenção a fluxo cambial")
    if window == "asia_close":
        items.append("Próximo: abertura europeia (Frankfurt 04:00 BRT, Londres 05:00 BRT) "
                     "— observar reação ao fechamento asiático")
    elif window == "europe_open":
        items.append("Próximo: abertura B3 às 10:00 BRT — verificar futuros e fluxo estrangeiro")
    elif window == "pre_market":
        items.append("Acompanhar abertura B3 às 10:00 BRT e fluxo estrangeiro")
    elif window == "mid_morning":
        items.append("Próximo: abertura US às 10:30 BRT — atenção a futuros e earnings pré-mercado")
    elif window == "afternoon":
        items.append("Próximo: fechamento Europa em torno de 13:30 BRT, fechamento B3 às 18:00 BRT")
    elif window == "close_br":
        items.append(f"Próximo: fechamento US ({next_day_label} pré-mercado BR): "
                     "reavaliar viés de abertura")
    elif window == "close_us":
        items.append(f"Próximo: pré-abertura B3 ({next_day_label}) — observar futuros do Ibovespa")
    elif window == "daily_wrap":
        items.append("Consolidado do dia completo. Próxima janela: abertura asiática "
                     f"({next_day_label} ~05:00 BRT)")
    if not items:
        items.append("Sem eventos macro de destaque programados.")
    return items


def persist_signals(window: str, results: dict, dhash: str):
    rows = []
    ts = datetime.utcnow().isoformat()
    for region, sigs in results.items():
        for s in sigs:
            rows.append((
                ts, window, s["ticker"], region, s["score"], s["classification"],
                json.dumps(s["layers"]), s["price"], s["atr"],
                s["suggested_alloc_pct"], s["stop_pct"], s["target_pct"],
                dhash, __version__,
            ))
    if rows:
        with conn() as c:
            c.executemany(
                "INSERT INTO signals (ts_utc, window, ticker, region, score, "
                "classification, layers_json, price, atr, suggested_alloc_pct, "
                "stop_pct, target_pct, data_hash, model_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )


def persist_macro(macro: dict):
    ts = datetime.utcnow().isoformat()
    rows = []
    for region in ("br", "us", "eu", "asia"):
        for ind, val in macro[region].items():
            if val is not None:
                rows.append((ts, region, ind, float(val), "live"))
    if rows:
        with conn() as c:
            try:
                c.executemany(
                    "INSERT OR REPLACE INTO macro_snapshots (ts_utc, region, indicator, value, source) "
                    "VALUES (?,?,?,?,?)",
                    rows,
                )
            except Exception as e:
                log.warning("Falha persist macro: %s", e)


def run(window: str, dry_run: bool = False):
    log.info("FIN-TRADER v%s starting | window=%s", __version__, window)
    init_db()

    wl = load_watchlist()
    weights = load_weights()
    by_region = active_tickers_by_region(wl)
    all_tickers = [t for ts in by_region.values() for t in ts]
    benchmarks = {r: wl[r]["benchmark"] for r in by_region}

    log.info("Coletando preços para %d tickers...", len(all_tickers))
    prices = fetch_prices(all_tickers, period="2y")
    log.info("Preços recebidos: %d/%d", len(prices), len(all_tickers))

    anomalies = check_data_quality(prices)
    log.info("Anomalias: %d", len(anomalies))

    log.info("Coletando macro...")
    macro = collect_macro()
    persist_macro(macro)

    log.info("Calculando scores...")
    results_by_region: dict[str, list] = {"br": [], "us": [], "eu": [], "asia": []}
    latest_prices = {}
    latest_scores = {}
    for region, tickers in by_region.items():
        bench_symbol = benchmarks[region]
        bench_df = prices.get(bench_symbol)
        for ticker in tickers:
            df = prices.get(ticker)
            if df is None or len(df) < 30:
                continue
            try:
                res = score_ticker(df, region, bench_df, macro["context"], weights)
                res["ticker"] = ticker
                results_by_region[region].append(res)
                latest_prices[ticker] = res["price"]
                latest_scores[ticker] = res["score"]
            except Exception as e:
                log.warning("Falha scoring %s: %s", ticker, e)

    dhash = data_hash(prices)

    if not dry_run:
        persist_signals(window, results_by_region, dhash)

        log.info("Avaliando posições abertas...")
        closures = evaluate_open_positions(latest_prices, latest_scores)

        for region, sigs in results_by_region.items():
            for s in sigs:
                if s["score"] >= 0.5 and s["suggested_alloc_pct"] >= 1.0:
                    open_position(
                        s["ticker"], region, s["price"], s["score"],
                        s["suggested_alloc_pct"], s["stop_pct"], s["target_pct"],
                    )
    else:
        closures = []

    metrics = portfolio_metrics()
    exposure = open_positions_summary()
    agenda = build_agenda(window, macro)

    path = generate_brief(
        window=window,
        signals_by_region=results_by_region,
        macro=macro,
        closures=closures,
        metrics=metrics,
        exposure_summary=exposure,
        anomalies=anomalies,
        agenda=agenda,
    )
    log.info("Brief gerado: %s", path)

    if not dry_run:
        summary_lines = [f"*FIN-TRADER {window}*", ""]
        for s in sorted(results_by_region["br"], key=lambda x: -x["score"])[:5]:
            summary_lines.append(f"`{s['ticker']}` {s['score']:+.2f} {s['classification']}")
        summary_lines.append("")
        summary_lines.append(f"Brief: `reports/{path.name}`")
        notify_brief("\n".join(summary_lines), str(path),
                     "https://github.com/Mauricio1806/FIN-TRADER")

    print(f"OK brief={path.name} signals_total={sum(len(v) for v in results_by_region.values())}")
    return path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--window", required=True,
                   choices=["asia_close", "europe_open", "pre_market", "mid_morning", "afternoon", "close_br", "close_us", "daily_wrap"])
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    run(args.window, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
