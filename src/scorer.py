from __future__ import annotations

from typing import Dict, List

import pandas as pd

from . import indicators

LAYER_WEIGHTS = {
    "trend_long": 1 / 6,
    "trend_mid": 1 / 6,
    "momentum": 1 / 6,
    "volatility": 1 / 6,
    "volume_strength": 1 / 6,
    "macro_sentiment": 1 / 6,
}


def classify_signal(score: float) -> str:
    if score >= 0.4:
        return "BUY"
    if 0.1 <= score < 0.4:
        return "WATCH_LONG"
    if -0.1 <= score < 0.1:
        return "NEUTRAL"
    if -0.4 < score < -0.1:
        return "WATCH_SHORT"
    return "SELL_AVOID"


def compute_score(ticker_df: pd.DataFrame, macro_data: Dict[str, float]) -> Dict:
    layer_scores = {
        "trend_long": indicators.trend_long(ticker_df),
        "trend_mid": indicators.trend_mid(ticker_df),
        "momentum": indicators.momentum(ticker_df),
        "volatility": indicators.volatility(ticker_df),
        "volume_strength": indicators.volume_strength(ticker_df),
        "macro_sentiment": indicators.macro_sentiment(
            macro_data.get("vix", float("nan")),
            macro_data.get("usdbrl", float("nan")),
        ),
    }

    weighted = {k: layer_scores[k] * LAYER_WEIGHTS[k] for k in layer_scores}
    total_score = float(sum(weighted.values()))
    total_score = max(-1.0, min(1.0, total_score))

    top_layers: List[Dict] = sorted(
        [
            {
                "layer": k,
                "raw": round(layer_scores[k], 4),
                "contribution": round(weighted[k], 4),
            }
            for k in layer_scores
        ],
        key=lambda x: abs(x["contribution"]),
        reverse=True,
    )[:3]

    return {
        "score": round(total_score, 4),
        "classification": classify_signal(total_score),
        "layers": {k: round(v, 4) for k, v in layer_scores.items()},
        "top_layers": top_layers,
    }
