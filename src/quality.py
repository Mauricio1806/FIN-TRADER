"""Health checks e drift detection."""
from datetime import datetime, timedelta
import pandas as pd
import numpy as np


def check_data_quality(prices: dict[str, pd.DataFrame], max_age_days: int = 5) -> list[dict]:
    """Retorna lista de anomalias. Vazio se tudo OK."""
    anomalies = []
    today = pd.Timestamp.now(tz="UTC").normalize()
    for ticker, df in prices.items():
        if df is None or df.empty:
            anomalies.append({"ticker": ticker, "detail": "Sem dados retornados"})
            continue
        last_ts = pd.Timestamp(df.index[-1])
        if last_ts.tz is None:
            last_ts = last_ts.tz_localize("UTC")
        age = (today - last_ts).days
        if age > max_age_days:
            anomalies.append({
                "ticker": ticker,
                "detail": f"Dado stale: última cotação há {age} dias"
            })
            continue
        last_close = df["close"].iloc[-1]
        if not np.isfinite(last_close) or last_close <= 0:
            anomalies.append({"ticker": ticker, "detail": "Preço inválido ou zero"})
            continue
        if "volume" in df and df["volume"].iloc[-1] == 0 and not ticker.startswith("^"):
            anomalies.append({"ticker": ticker, "detail": "Volume zero no último dia"})
    return anomalies


def detect_drift(current_scores: list[float], baseline_mean: float, baseline_std: float) -> str | None:
    if not current_scores or baseline_std <= 0:
        return None
    current_mean = np.mean(current_scores)
    z = abs((current_mean - baseline_mean) / baseline_std)
    if z > 2.0:
        direction = "alta" if current_mean > baseline_mean else "baixa"
        return f"Drift detectado: score médio da watchlist em {direction} (z={z:.2f})"
    return None
