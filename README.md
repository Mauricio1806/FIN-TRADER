# FIN-TRADER

Sistema autônomo de geração de sinais de trading e brief diário em Markdown, executado por GitHub Actions, com persistência de histórico em SQLite.

## Objetivo

O FIN-TRADER roda diariamente no fechamento do mercado brasileiro (18:00 BRT), coleta dados de mercado e macro, calcula 6 camadas de análise técnica/sentimento, produz um score composto por ativo e gera um brief objetivo em português.

## Arquitetura

```text
src/main.py
  ├── src/collector.py   -> Coleta yfinance + BCB SGS
  ├── src/indicators.py  -> 6 camadas de score [-1, +1]
  ├── src/scorer.py      -> Agregação, classificação e top contribuições
  ├── src/brief.py       -> Geração de markdown
  └── src/db.py          -> Persistência SQLite + histórico 90d
```

### Fluxo de execução

1. Carrega `config/watchlist.yaml`.
2. Coleta preços (yfinance) com retry e backoff exponencial.
3. Coleta macro do BCB (SGS 432, 13522, 1).
4. Calcula camadas e score composto por ticker.
5. Detecta drift de score médio (> 2σ vs média 90d).
6. Gera brief em `reports/`.
7. Salva sinais em `db/signals.db` (idempotente por hash).
8. Tenta commit local de `reports/` e `db/`.

## Estrutura do brief

O markdown gerado segue as seções:

- `TL;DR`
- `Brasil (foco)`
- `US (secundário)`
- `Macro Snapshot`
- `Próxima Agenda`

Formato compacto, sem emojis, linguagem direta.

## Regras de classificação

- `BUY`: score >= 0.4
- `WATCH_LONG`: 0.1 <= score < 0.4
- `NEUTRAL`: -0.1 <= score < 0.1
- `WATCH_SHORT`: -0.4 < score < -0.1
- `SELL_AVOID`: score <= -0.4

## Camadas de análise

Todas retornam score no intervalo `[-1, +1]`:

1. `trend_long`: preço vs SMA200 + inclinação da SMA200.
2. `trend_mid`: EMA20 vs EMA50 + histograma MACD.
3. `momentum`: RSI(14) + ROC(20).
4. `volatility`: ATR(14) + largura de Bollinger.
5. `volume_strength`: tendência do OBV + volume atual vs SMA20.
6. `macro_sentiment`: normalização de VIX e USD/BRL.

## Pesos (score composto)

Por padrão, pesos iguais (1/6 cada camada) em `src/scorer.py`:

```python
LAYER_WEIGHTS = {
    "trend_long": 1/6,
    "trend_mid": 1/6,
    "momentum": 1/6,
    "volatility": 1/6,
    "volume_strength": 1/6,
    "macro_sentiment": 1/6,
}
```

### Como customizar pesos

1. Edite `LAYER_WEIGHTS` em `src/scorer.py`.
2. Garanta que a soma seja `1.0`.
3. Execute localmente para validar impacto no score/classificação.

## Rodando localmente

### 1) Pré-requisitos

- Python 3.12+
- Git
- Acesso à internet para yfinance e BCB API

### 2) Instalação

```bash
git clone https://github.com/Mauricio1806/FIN-TRADER.git
cd FIN-TRADER
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### 3) Execução

```bash
python -m src.main --window close_br
```

Saídas esperadas:
- Brief em `reports/brief_YYYYMMDD_HHMM.md`
- Banco SQLite em `db/signals.db`

## GitHub Actions

Workflow em `.github/workflows/close_br.yml`:
- Cron: `0 21 * * 1-5` (21:00 UTC = 18:00 BRT)
- Executa pipeline
- Commit/push automático de `reports/` e `db/`

## Banco de dados

Tabela `signals`:
- `id`
- `ticker`
- `timestamp`
- `score`
- `classification`
- `top_layers` (JSON)
- `data_hash` (UNIQUE para idempotência)

## Observações de operação

- O pipeline é resiliente a falhas pontuais de coleta via retries.
- Drift detection só dispara após base histórica mínima.
- Recomendado revisar periodicamente watchlist e pesos por regime de mercado.
