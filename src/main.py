from __future__ import annotations

import argparse
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo

import yaml

from .brief import generate_brief
from .collector import fetch_bcb_macro, fetch_prices
from .db import get_historical_avg, save_signals
from .scorer import compute_score

LOGGER = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FIN-TRADER pipeline")
    parser.add_argument("--window", default="close_br", choices=["close_br"])
    parser.add_argument("--watchlist", default="config/watchlist.yaml")
    parser.add_argument("--db-path", default="db/signals.db")
    return parser.parse_args()


def load_watchlist(path: str) -> Dict[str, List[str]]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    required = {"brasil", "usa", "macro"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Watchlist inválida. Chaves ausentes: {sorted(missing)}")

    return data


def detect_drift(current_avg: float, historical: Dict) -> str | None:
    if historical["count"] < 20 or historical["std"] <= 0:
        return None

    diff = abs(current_avg - historical["avg"])
    threshold = 2 * historical["std"]
    if diff > threshold:
        return (
            f"score médio atual ({current_avg:+.3f}) distante da média 90d "
            f"({historical['avg']:+.3f}) em {diff:.3f} (> 2σ={threshold:.3f})."
        )
    return None


def commit_artifacts() -> None:
    try:
        subprocess.run(["git", "add", "reports/", "db/"], check=False)
        commit_msg = f"chore: daily brief {datetime.utcnow().isoformat()}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=False)
        LOGGER.info("Tentativa de commit local executada.")
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Falha ao executar git commit automático: %s", exc)


def run() -> None:
    args = parse_args()
    setup_logging()

    LOGGER.info("Iniciando FIN-TRADER com janela: %s", args.window)
    tz = ZoneInfo("America/Sao_Paulo")
    now = datetime.now(tz)

    watchlist = load_watchlist(args.watchlist)
    ticker_regions = {
        **{t: "brasil" for t in watchlist["brasil"]},
        **{t: "usa" for t in watchlist["usa"]},
    }

    price_tickers = list(dict.fromkeys(watchlist["brasil"] + watchlist["usa"] + watchlist["macro"]))
    price_data = fetch_prices(price_tickers)
    macro_bcb = fetch_bcb_macro()

    vix = float(price_data["^VIX"]["Close"].iloc[-1])
    usdbrl_yf = float(price_data["USDBRL=X"]["Close"].iloc[-1])
    selic = float(macro_bcb["selic"].iloc[-1])
    ipca = float(macro_bcb["ipca"].iloc[-1])
    usdbrl_bcb = float(macro_bcb["usdbrl_bcb"].iloc[-1])

    macro_snapshot = {
        "vix": vix,
        "usdbrl": usdbrl_yf,
        "selic": selic,
        "ipca": ipca,
        "usdbrl_bcb": usdbrl_bcb,
    }

    historical = get_historical_avg(db_path=args.db_path)

    signals = []
    for ticker, region in ticker_regions.items():
        try:
            score_output = compute_score(
                ticker_df=price_data[ticker],
                macro_data={"vix": vix, "usdbrl": usdbrl_yf},
            )
            signals.append(
                {
                    "ticker": ticker,
                    "region": region,
                    "timestamp": now.isoformat(),
                    **score_output,
                }
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Falha no cálculo para %s: %s", ticker, exc)

    if not signals:
        raise RuntimeError("Nenhum sinal foi gerado.")

    current_avg = sum(s["score"] for s in signals) / len(signals)
    drift_alert = detect_drift(current_avg, historical)
    if drift_alert:
        LOGGER.warning("DRIFT DETECTED: %s", drift_alert)
        macro_snapshot["drift_alert"] = drift_alert

    report_md = generate_brief(signals=signals, macro_snapshot=macro_snapshot, timestamp=now)
    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"brief_{now.strftime('%Y%m%d_%H%M')}.md"
    report_path.write_text(report_md, encoding="utf-8")

    inserted = save_signals(signals=signals, db_path=args.db_path)
    LOGGER.info("Brief salvo em %s | sinais inseridos: %s", report_path, inserted)

    commit_artifacts()


def main() -> None:
    try:
        run()
    except Exception as exc:  # noqa: BLE001
        logging.exception("Erro fatal no pipeline: %s", exc)
        raise


if __name__ == "__main__":
    main()
