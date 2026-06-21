from __future__ import annotations

import logging
import time
from typing import Dict, List

import pandas as pd
import requests
import yfinance as yf

LOGGER = logging.getLogger(__name__)

BCB_SERIES = {
    "selic": 432,
    "ipca": 13522,
    "usdbrl_bcb": 1,
}


def _download_yf(tickers: List[str], period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    if not tickers:
        raise ValueError("Lista de tickers vazia para download.")

    data = yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )

    if data is None or data.empty:
        raise RuntimeError("yfinance retornou dataset vazio.")

    return data


def _clean_single_ticker(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    expected_cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    out = df.copy()

    for col in expected_cols:
        if col not in out.columns:
            if col == "Adj Close" and "Close" in out.columns:
                out[col] = out["Close"]
            else:
                out[col] = pd.NA

    out = out[expected_cols]
    out = out.dropna(how="all")

    numeric_cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    out[numeric_cols] = out[numeric_cols].apply(pd.to_numeric, errors="coerce")

    out[["Open", "High", "Low", "Close", "Adj Close"]] = out[
        ["Open", "High", "Low", "Close", "Adj Close"]
    ].ffill().bfill()

    out["Volume"] = out["Volume"].fillna(0)
    invalid_volume_mask = out["Volume"] <= 0
    if invalid_volume_mask.any():
        LOGGER.warning(
            "Ticker %s possui %s linhas com volume <= 0. Aplicando correção mínima.",
            ticker,
            int(invalid_volume_mask.sum()),
        )
        out.loc[invalid_volume_mask, "Volume"] = pd.NA
        out["Volume"] = out["Volume"].ffill().bfill().fillna(1.0)

    out = out.dropna(subset=["Close"])
    if out.empty:
        raise RuntimeError(f"Ticker {ticker} ficou sem dados após limpeza.")

    if float(out["Volume"].max()) <= 0:
        raise RuntimeError(f"Ticker {ticker} sem volume válido (>0).")

    out.index = pd.to_datetime(out.index)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def fetch_prices(tickers: List[str], retries: int = 3, base_backoff_seconds: float = 1.5) -> Dict[str, pd.DataFrame]:
    """Baixa preços diários via yfinance com retry e backoff exponencial."""
    if not tickers:
        return {}

    attempt = 0
    last_exception: Exception | None = None

    while attempt < retries:
        try:
            raw = _download_yf(tickers)
            result: Dict[str, pd.DataFrame] = {}

            if isinstance(raw.columns, pd.MultiIndex):
                for ticker in tickers:
                    if ticker not in raw.columns.get_level_values(0):
                        raise RuntimeError(f"Ticker {ticker} ausente no retorno do yfinance.")
                    result[ticker] = _clean_single_ticker(raw[ticker], ticker)
            else:
                if len(tickers) != 1:
                    raise RuntimeError("Formato inesperado do yfinance para múltiplos tickers.")
                result[tickers[0]] = _clean_single_ticker(raw, tickers[0])

            LOGGER.info("Coleta de preços concluída para %s tickers.", len(result))
            return result
        except Exception as exc:  # noqa: BLE001
            last_exception = exc
            attempt += 1
            if attempt >= retries:
                break
            sleep_s = base_backoff_seconds * (2 ** (attempt - 1))
            LOGGER.warning(
                "Erro ao coletar preços (tentativa %s/%s): %s. Retry em %.1fs",
                attempt,
                retries,
                exc,
                sleep_s,
            )
            time.sleep(sleep_s)

    raise RuntimeError(f"Falha ao coletar preços após {retries} tentativas: {last_exception}")


def _fetch_single_bcb_series(series_id: int, timeout: int = 20) -> pd.Series:
    base_url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados"
    headers = {"User-Agent": "FIN-TRADER/1.0", "Accept": "application/json"}

    end = pd.Timestamp.today().normalize()
    start = end - pd.DateOffset(years=10)

    params = {
        "formato": "json",
        "dataInicial": start.strftime("%d/%m/%Y"),
        "dataFinal": end.strftime("%d/%m/%Y"),
    }

    response = requests.get(base_url, params=params, timeout=timeout, headers=headers)

    if response.status_code >= 400:
        # fallback para séries com regras específicas da API
        fallback_url = f"{base_url}/ultimos/20"
        response = requests.get(fallback_url, params={"formato": "json"}, timeout=timeout, headers=headers)

    response.raise_for_status()

    payload = response.json()
    if not payload:
        raise RuntimeError(f"Série BCB {series_id} sem dados.")

    df = pd.DataFrame(payload)
    df["date"] = pd.to_datetime(df["data"], format="%d/%m/%Y", errors="coerce")
    df["value"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna(subset=["date", "value"]).sort_values("date")
    if df.empty:
        raise RuntimeError(f"Série BCB {series_id} inválida após parsing.")

    series = df.set_index("date")["value"]
    series.name = str(series_id)
    return series


def fetch_bcb_macro() -> pd.DataFrame:
    """Coleta séries SGS do BCB (Selic, IPCA e câmbio USD/BRL)."""
    frames = []
    for name, series_id in BCB_SERIES.items():
        s = _fetch_single_bcb_series(series_id)
        frames.append(s.rename(name))

    macro = pd.concat(frames, axis=1).sort_index()
    macro = macro.ffill().dropna(how="all")

    if macro.empty:
        raise RuntimeError("Macro BCB retornou vazio após limpeza.")

    LOGGER.info("Coleta macro BCB concluída com %s linhas.", len(macro))
    return macro
