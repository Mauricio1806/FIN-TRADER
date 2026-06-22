"""Coleta de dados: yfinance (prices) + BCB SGS (macro BR)."""
import logging
import time
import hashlib
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import requests

log = logging.getLogger(__name__)

BCB_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados?formato=json"
BCB_SERIES = {
    "selic":          432,
    "ipca_12m":       13522,
    "ipca15":         7478,
    "usdbrl":         1,
    "ibcbr":          24364,
    "prod_industrial": 21859,
}


def _retry(fn, *args, tries=3, base_delay=1.0, **kwargs):
    last = None
    for i in range(tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last = e
            time.sleep(base_delay * (4 ** i))
    raise last


def fetch_prices(tickers: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    """Baixa OHLCV de todos os tickers em batch. Retorna dict ticker -> DataFrame."""
    if not tickers:
        return {}
    try:
        data = yf.download(
            tickers=" ".join(tickers),
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        log.warning("yf.download falhou em batch (%s); tentando individual.", e)
        data = None

    out: dict[str, pd.DataFrame] = {}
    if data is not None and isinstance(data.columns, pd.MultiIndex):
        for t in tickers:
            try:
                df = data[t].dropna(how="all")
                if not df.empty:
                    df = df.rename(columns=str.lower)
                    out[t] = df
            except KeyError:
                pass
        missing = [t for t in tickers if t not in out]
    else:
        missing = list(tickers)

    for t in missing:
        try:
            df = _retry(yf.download, t, period=period, interval="1d",
                        auto_adjust=True, progress=False, threads=False)
            if df is not None and not df.empty:
                df = df.rename(columns=str.lower)
                out[t] = df
        except Exception as e:
            log.warning("Falha em %s: %s", t, e)
    return out


def fetch_bcb_series(code: int, last_n: int = 30) -> pd.DataFrame | None:
    url = BCB_BASE.format(code=code)
    try:
        r = _retry(requests.get, url, timeout=20)
        if r.status_code != 200:
            return None
        df = pd.DataFrame(r.json())
        df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
        df = df.sort_values("data").tail(last_n).reset_index(drop=True)
        return df
    except Exception as e:
        log.warning("BCB %s falhou: %s", code, e)
        return None


def fetch_all_bcb() -> dict[str, float | None]:
    out = {}
    for name, code in BCB_SERIES.items():
        df = fetch_bcb_series(code)
        out[name] = float(df["valor"].iloc[-1]) if df is not None and not df.empty else None
    return out


def data_hash(prices: dict[str, pd.DataFrame]) -> str:
    h = hashlib.sha256()
    for t in sorted(prices.keys()):
        df = prices[t]
        if df.empty:
            continue
        last = df.tail(1)
        h.update(f"{t}:{last.index[-1]}:{last['close'].iloc[-1]:.4f}".encode())
    return h.hexdigest()[:16]
