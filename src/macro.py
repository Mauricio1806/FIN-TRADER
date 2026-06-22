"""Snapshot macro das 4 regiões com classificação de regime."""
import logging
import pandas as pd
import yfinance as yf
from .collector import fetch_all_bcb, fetch_prices

log = logging.getLogger(__name__)

GLOBAL_TICKERS = ["^VIX", "^TNX", "DX-Y.NYB", "^STOXX50E", "^HSI", "^N225",
                  "USDCNY=X", "USDJPY=X", "EURUSD=X"]


def collect_macro() -> dict:
    """Retorna dicionário aninhado: {region: {indicator: value}} + context flags."""
    out = {"br": {}, "us": {}, "eu": {}, "asia": {}, "context": {}}

    bcb = fetch_all_bcb()
    out["br"]["selic"] = bcb.get("selic")
    out["br"]["ipca_12m"] = bcb.get("ipca_12m")
    out["br"]["ipca15"] = bcb.get("ipca15")
    out["br"]["usdbrl"] = bcb.get("usdbrl")
    out["br"]["ibcbr"] = bcb.get("ibcbr")

    prices = fetch_prices(GLOBAL_TICKERS, period="3mo")
    def last(t):
        df = prices.get(t)
        return float(df["close"].iloc[-1]) if df is not None and not df.empty else None
    def delta_5d(t):
        df = prices.get(t)
        if df is None or len(df) < 6:
            return 0.0
        return float(df["close"].iloc[-1] / df["close"].iloc[-6] - 1)

    out["us"]["vix"] = last("^VIX")
    out["us"]["treasury_10y"] = last("^TNX")
    out["us"]["dxy"] = last("DX-Y.NYB")
    out["eu"]["stoxx50"] = last("^STOXX50E")
    out["eu"]["eurusd"] = last("EURUSD=X")
    out["asia"]["hsi"] = last("^HSI")
    out["asia"]["nikkei"] = last("^N225")
    out["asia"]["usdcny"] = last("USDCNY=X")
    out["asia"]["usdjpy"] = last("USDJPY=X")

    out["context"]["vix"] = out["us"]["vix"] or 16.0
    out["context"]["usdbrl_delta_5d"] = -delta_5d("USDBRL=X") if "USDBRL=X" in prices else 0.0
    out["context"]["br_breadth"] = 0.0

    out["regime"] = _classify_regime(out)
    return out


def _classify_regime(macro: dict) -> dict:
    """Classifica regime global e por região."""
    vix = macro["us"].get("vix") or 16
    selic = macro["br"].get("selic") or 10
    out = {}
    if vix > 25:
        out["global"] = "risk_off"
    elif vix < 14:
        out["global"] = "risk_on"
    else:
        out["global"] = "transition"
    if selic and selic > 13:
        out["br"] = "tight_monetary"
    elif selic and selic < 8:
        out["br"] = "loose_monetary"
    else:
        out["br"] = "neutral_monetary"
    out["us"] = out["global"]
    out["eu"] = out["global"]
    out["asia"] = out["global"]
    return out
