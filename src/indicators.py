from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _clip_score(value: float) -> float:
    if pd.isna(value):
        return 0.0
    return float(np.clip(value, -1.0, 1.0))


def _safe_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        raise ValueError(f"Coluna obrigatória ausente: {column}")
    s = pd.to_numeric(df[column], errors="coerce")
    return s.ffill().bfill()


def trend_long(df: pd.DataFrame) -> float:
    close = _safe_series(df, "Close")
    if len(close) < 210:
        return 0.0

    sma200 = close.rolling(200).mean()
    last_close = close.iloc[-1]
    last_sma = sma200.iloc[-1]

    ratio = (last_close / last_sma) - 1 if last_sma and not pd.isna(last_sma) else 0.0
    ratio_score = np.tanh(ratio / 0.08)

    slope = (sma200.iloc[-1] - sma200.iloc[-20]) / abs(sma200.iloc[-20]) if not pd.isna(sma200.iloc[-20]) and sma200.iloc[-20] != 0 else 0.0
    slope_score = np.tanh(slope / 0.03)

    return _clip_score(0.7 * ratio_score + 0.3 * slope_score)


def trend_mid(df: pd.DataFrame) -> float:
    close = _safe_series(df, "Close")
    if len(close) < 60:
        return 0.0

    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    ema_spread = ((ema20.iloc[-1] / ema50.iloc[-1]) - 1) if ema50.iloc[-1] != 0 else 0.0
    ema_score = np.tanh(ema_spread / 0.03)

    macd_line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line
    hist_norm = macd_hist.iloc[-1] / close.iloc[-1] if close.iloc[-1] != 0 else 0.0
    macd_score = np.tanh(hist_norm / 0.01)

    return _clip_score(0.6 * ema_score + 0.4 * macd_score)


def momentum(df: pd.DataFrame) -> float:
    close = _safe_series(df, "Close")
    if len(close) < 30:
        return 0.0

    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.rolling(14).mean()
    avg_loss = losses.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi_last = rsi.iloc[-1]

    if pd.isna(rsi_last):
        rsi_score = 0.0
    else:
        # 50 neutro; acima disso momentum positivo
        rsi_score = np.tanh((rsi_last - 50) / 18)

    roc20 = close.pct_change(20).iloc[-1]
    roc_score = np.tanh((0.0 if pd.isna(roc20) else roc20) / 0.12)

    return _clip_score(0.5 * rsi_score + 0.5 * roc_score)


def volatility(df: pd.DataFrame) -> float:
    close = _safe_series(df, "Close")
    high = _safe_series(df, "High")
    low = _safe_series(df, "Low")

    if len(close) < 30:
        return 0.0

    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr14 = tr.rolling(14).mean()
    atr_pct = (atr14.iloc[-1] / close.iloc[-1]) if close.iloc[-1] != 0 else math.nan

    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    upper = ma20 + 2 * std20
    lower = ma20 - 2 * std20
    bb_width = ((upper - lower) / ma20).iloc[-1] if ma20.iloc[-1] != 0 else math.nan

    atr_score = -np.tanh((0.0 if pd.isna(atr_pct) else atr_pct) / 0.05)
    bb_score = -np.tanh((0.0 if pd.isna(bb_width) else bb_width) / 0.25)

    return _clip_score(0.5 * atr_score + 0.5 * bb_score)


def volume_strength(df: pd.DataFrame) -> float:
    close = _safe_series(df, "Close")
    volume = _safe_series(df, "Volume")

    if len(close) < 30:
        return 0.0

    direction = np.sign(close.diff().fillna(0))
    obv = (direction * volume).cumsum()

    n = min(30, len(obv))
    y = obv.tail(n).to_numpy(dtype=float)
    x = np.arange(n, dtype=float)
    slope = np.polyfit(x, y, 1)[0] if n > 2 else 0.0
    denom = np.mean(np.abs(y)) + 1e-9
    obv_score = np.tanh((slope / denom) * 60)

    vol_sma20 = volume.rolling(20).mean().iloc[-1]
    vol_ratio = (volume.iloc[-1] / vol_sma20) if vol_sma20 and not pd.isna(vol_sma20) else 1.0
    vol_score = np.tanh((vol_ratio - 1.0) / 0.5)

    return _clip_score(0.6 * obv_score + 0.4 * vol_score)


def macro_sentiment(vix: float, usdbrl: float) -> float:
    if pd.isna(vix) or pd.isna(usdbrl):
        return 0.0

    # Menor VIX e menor USD/BRL favorecem risk-on
    vix_norm = np.clip((vix - 20.0) / 15.0, -1.0, 1.0)
    usd_norm = np.clip((usdbrl - 5.2) / 0.9, -1.0, 1.0)

    score = -0.6 * vix_norm - 0.4 * usd_norm
    return _clip_score(score)
