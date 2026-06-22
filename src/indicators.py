"""12 camadas analíticas. Cada função retorna float em [-1, +1]."""
import math
import numpy as np
import pandas as pd

EPS = 1e-9


def _clip(x: float) -> float:
    if x is None or not np.isfinite(x):
        return 0.0
    return float(max(-1.0, min(1.0, x)))


def _tanh_norm(x: float, scale: float = 1.0) -> float:
    return _clip(math.tanh(x / scale)) if np.isfinite(x) else 0.0


# 1 — Tendência longa: preço vs SMA200 + slope SMA200
def layer_trend_long(df: pd.DataFrame) -> float:
    if len(df) < 220:
        return 0.0
    close = df["close"]
    sma200 = close.rolling(200).mean()
    if sma200.iloc[-1] is np.nan or sma200.iloc[-1] == 0:
        return 0.0
    distance = (close.iloc[-1] - sma200.iloc[-1]) / sma200.iloc[-1]
    slope_pct = (sma200.iloc[-1] - sma200.iloc[-60]) / sma200.iloc[-60] if sma200.iloc[-60] else 0.0
    score = 0.6 * _tanh_norm(distance, 0.15) + 0.4 * _tanh_norm(slope_pct, 0.08)
    return _clip(score)


# 2 — Tendência média: EMA20 vs EMA50 + MACD histogram
def layer_trend_mid(df: pd.DataFrame) -> float:
    if len(df) < 60:
        return 0.0
    close = df["close"]
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    cross = (ema20.iloc[-1] - ema50.iloc[-1]) / ema50.iloc[-1] if ema50.iloc[-1] else 0.0
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = (macd - signal).iloc[-1]
    hist_norm = hist / close.iloc[-1] if close.iloc[-1] else 0.0
    score = 0.6 * _tanh_norm(cross, 0.05) + 0.4 * _tanh_norm(hist_norm, 0.02)
    return _clip(score)


# 3 — Momentum: RSI(14) + ROC(20d)
def layer_momentum(df: pd.DataFrame) -> float:
    if len(df) < 30:
        return 0.0
    close = df["close"]
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + EPS)
    rsi = 100 - (100 / (1 + rs))
    rsi_v = rsi.iloc[-1]
    rsi_score = (rsi_v - 50) / 50.0 if np.isfinite(rsi_v) else 0.0
    roc20 = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 21 else 0.0
    score = 0.5 * _clip(rsi_score) + 0.5 * _tanh_norm(roc20, 0.10)
    return _clip(score)


# 4 — Volatilidade: ATR% + Bollinger bandwidth + regime
def layer_volatility(df: pd.DataFrame) -> float:
    """Volatilidade BAIXA + comprimindo = leve positivo (potencial breakout).
       Volatilidade ALTA + expandindo = negativo (instabilidade)."""
    if len(df) < 30:
        return 0.0
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        (high - low),
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    atr_pct = atr.iloc[-1] / close.iloc[-1] if close.iloc[-1] else 0.0
    atr_median = (atr / close).rolling(60).median().iloc[-1]
    atr_z = (atr_pct - atr_median) / (atr_median + EPS) if atr_median else 0.0
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_width = (4 * std20.iloc[-1]) / (sma20.iloc[-1] + EPS)
    bb_width_median = ((4 * std20) / (sma20 + EPS)).rolling(60).median().iloc[-1]
    bb_z = (bb_width - bb_width_median) / (bb_width_median + EPS) if bb_width_median else 0.0
    score = -0.5 * _tanh_norm(atr_z, 1.0) - 0.5 * _tanh_norm(bb_z, 1.0)
    return _clip(score)


# 5 — Volume: OBV trend + volume vs SMA20
def layer_volume(df: pd.DataFrame) -> float:
    if len(df) < 30 or "volume" not in df:
        return 0.0
    close = df["close"]
    vol = df["volume"]
    sign = np.sign(close.diff().fillna(0))
    obv = (sign * vol).cumsum()
    obv_slope = (obv.iloc[-1] - obv.iloc[-20]) / (abs(obv.iloc[-20]) + EPS) if len(obv) >= 21 else 0.0
    vol_sma20 = vol.rolling(20).mean()
    vol_ratio = vol.iloc[-1] / (vol_sma20.iloc[-1] + EPS) if vol_sma20.iloc[-1] else 1.0
    vol_ratio_norm = (vol_ratio - 1.0)
    score = 0.6 * _tanh_norm(obv_slope, 0.5) + 0.4 * _tanh_norm(vol_ratio_norm, 1.0)
    return _clip(score)


# 6 — Suporte/Resistência: distância de máximas/mínimas 52w
def layer_support_resist(df: pd.DataFrame) -> float:
    if len(df) < 60:
        return 0.0
    close = df["close"]
    window = min(252, len(df))
    hi = df["high"].rolling(window).max().iloc[-1]
    lo = df["low"].rolling(window).min().iloc[-1]
    if hi == lo:
        return 0.0
    pos = (close.iloc[-1] - lo) / (hi - lo)
    score = 2.0 * pos - 1.0
    return _clip(score)


# 7 — Correlação: beta rolling 60d vs benchmark da região
def layer_correlation(df: pd.DataFrame, bench: pd.DataFrame | None) -> float:
    """Beta moderado positivo (0.5-1.2) é neutro; betas extremos são levemente negativos."""
    if bench is None or len(df) < 60 or len(bench) < 60:
        return 0.0
    rets = df["close"].pct_change().dropna()
    bench_rets = bench["close"].pct_change().dropna()
    common = rets.index.intersection(bench_rets.index)[-60:]
    if len(common) < 30:
        return 0.0
    r = rets.loc[common]
    b = bench_rets.loc[common]
    cov = np.cov(r, b)[0, 1]
    var_b = np.var(b)
    if var_b < EPS:
        return 0.0
    beta = cov / var_b
    if 0.5 <= beta <= 1.2:
        return 0.0
    if beta < 0:
        return -0.3
    if beta > 2.0:
        return -0.3
    return 0.0


# 8 — Macro: sensibilidade a juros/câmbio
def layer_macro(df: pd.DataFrame, region: str, macro_context: dict) -> float:
    """Aproximação simples: setores correlatos a juros sofrem em ciclo de alta.
       Aqui usamos um proxy genérico via diferencial USDBRL recente para BR."""
    if region == "br":
        usdbrl_delta = macro_context.get("usdbrl_delta_5d", 0.0)
        return _tanh_norm(-usdbrl_delta * 5, 1.0)
    if region == "us":
        vix = macro_context.get("vix", 16.0)
        return _tanh_norm((20.0 - vix) / 10.0, 1.0)
    return 0.0


# 9 — Sazonalidade: retorno médio do mês corrente nos últimos N anos
def layer_seasonality(df: pd.DataFrame) -> float:
    if len(df) < 252 * 3:
        return 0.0
    monthly = df["close"].resample("ME").last().pct_change().dropna()
    if monthly.empty:
        return 0.0
    current_month = monthly.index[-1].month if len(monthly) else None
    if current_month is None:
        return 0.0
    historical = monthly[monthly.index.month == current_month]
    if len(historical) < 3:
        return 0.0
    avg = historical.mean()
    return _tanh_norm(avg * 20, 1.0)


# 10 — Estatística: Sharpe rolling 90d + skewness
def layer_statistical(df: pd.DataFrame) -> float:
    if len(df) < 90:
        return 0.0
    rets = df["close"].pct_change().dropna().tail(90)
    if rets.std() < EPS:
        return 0.0
    sharpe = rets.mean() / rets.std() * math.sqrt(252)
    skew = rets.skew() if len(rets) > 10 else 0.0
    score = 0.7 * _tanh_norm(sharpe, 1.5) + 0.3 * _tanh_norm(skew, 1.0)
    return _clip(score)


# 11 — Risco de cauda: max drawdown 90d + VaR 95%
def layer_tail_risk(df: pd.DataFrame) -> float:
    """Drawdown grande e VaR ruim → negativo. Drawdown pequeno → leve positivo."""
    if len(df) < 90:
        return 0.0
    window = df["close"].tail(90)
    rolling_max = window.cummax()
    dd = (window / rolling_max - 1).min()
    rets = df["close"].pct_change().dropna().tail(90)
    if len(rets) < 30:
        return 0.0
    var95 = np.quantile(rets, 0.05)
    score = 0.6 * _tanh_norm(-dd * 5, 1.0) + 0.4 * _tanh_norm(var95 * 30, 1.0)
    return _clip(-score) if score > 0 else _clip(score)


# 12 — Sentimento: VIX (US), proxy IVOL (BR), breadth da região
def layer_sentiment(region: str, macro_context: dict) -> float:
    if region == "us":
        vix = macro_context.get("vix")
        if vix is None:
            return 0.0
        return _tanh_norm((20.0 - vix) / 8.0, 1.0)
    if region == "br":
        ivol = macro_context.get("br_breadth", 0.0)
        return _tanh_norm(ivol, 1.0)
    return 0.0


def compute_all_layers(
    df: pd.DataFrame,
    region: str,
    bench: pd.DataFrame | None,
    macro_context: dict,
) -> dict[str, float]:
    """Retorna dict com as 12 camadas. Falhas individuais não derrubam o conjunto."""
    layers = {}
    funcs = {
        "trend_long":     lambda: layer_trend_long(df),
        "trend_mid":      lambda: layer_trend_mid(df),
        "momentum":       lambda: layer_momentum(df),
        "volatility":     lambda: layer_volatility(df),
        "volume":         lambda: layer_volume(df),
        "support_resist": lambda: layer_support_resist(df),
        "correlation":    lambda: layer_correlation(df, bench),
        "macro":          lambda: layer_macro(df, region, macro_context),
        "seasonality":    lambda: layer_seasonality(df),
        "statistical":    lambda: layer_statistical(df),
        "tail_risk":      lambda: layer_tail_risk(df),
        "sentiment":      lambda: layer_sentiment(region, macro_context),
    }
    for name, fn in funcs.items():
        try:
            layers[name] = float(fn())
        except Exception:
            layers[name] = 0.0
    return layers


def latest_atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period + 1:
        return 0.0
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        (high - low),
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    return float(atr) if np.isfinite(atr) else 0.0
