# FIN-TRADER

Sistema autônomo de geração de sinais de trade quantitativos com foco no mercado brasileiro, secundários EUA e Europa, e contextual Ásia. Roda inteiramente em GitHub Actions, sem dependência de plataformas de IA em runtime — todo o "agente" é código Python determinístico.

Sistema irmão do [FIN-BOT](https://github.com/Mauricio1806/FIN-BOT), focado em geração de sinais (este) vs. monitoramento contínuo (FIN-BOT).

## O que faz

A cada execução agendada (5 janelas diárias), o FIN-TRADER:

1. Coleta cotações de ~48 ativos (B3, US, EU, Ásia) via yfinance
2. Coleta dados macroeconômicos do Banco Central (Selic, IPCA, USD/BRL, IBC-Br) e globais (VIX, Treasury 10Y, DXY)
3. Calcula 12 camadas analíticas por ticker
4. Combina em score composto ponderado, com boost regional (BR +10%)
5. Classifica cada ativo: BUY / WATCH_LONG / NEUTRAL / WATCH_SHORT / SELL_AVOID
6. Sugere alocação % de portfólio, stop e alvo baseados em ATR
7. Mantém portfólio paper-trading em % (sem capital fixo) para validar hit-rate
8. Gera Daily Brief em Markdown na pasta `reports/`
9. Publica via GitHub Pages no dashboard `https://mauricio1806.github.io/FIN-TRADER/`
10. Opcionalmente notifica via Telegram

## As 12 camadas analíticas

| # | Camada | Cálculo |
|---|---|---|
| 1 | Tendência longa | Preço vs SMA200 + slope 60d |
| 2 | Tendência média | EMA20/50 + MACD histogram |
| 3 | Momentum | RSI(14) + ROC(20) |
| 4 | Volatilidade | ATR% + Bollinger bandwidth |
| 5 | Volume | OBV + volume vs SMA20 |
| 6 | Suporte/Resistência | Posição vs máx/mín 52 semanas |
| 7 | Correlação | Beta rolling 60d vs benchmark regional |
| 8 | Macro | Sensibilidade a juros/câmbio |
| 9 | Sazonalidade | Retorno médio histórico do mês corrente |
| 10 | Estatística | Sharpe rolling 90d + skewness |
| 11 | Risco de cauda | Max drawdown + VaR 95% |
| 12 | Sentimento | VIX/breadth da região |

Pesos configuráveis em `config/weights.yaml`.

## Janelas de execução

Brasil não usa horário de verão; UTC = BRT + 3.

| Workflow | BRT | UTC Cron | Foco |
|---|---|---|---|
| `pre_market.yml` | 09:00 | `0 12 * * 1-5` | Pré-abertura B3, Ásia fechada, Europa abrindo |
| `mid_morning.yml` | 11:30 | `30 14 * * 1-5` | 1h30 pós-abertura B3 |
| `afternoon.yml` | 14:30 | `30 17 * * 1-5` | US recém-aberto, Europa fechando |
| `close_br.yml` | 18:00 | `0 21 * * 1-5` | Fechamento B3 — relatório principal |
| `close_us.yml` | 19:00 | `0 22 * * 1-5` | Pós-fechamento US — wrap-up global |

## Rodando localmente

Pré-requisitos: Python 3.12+, git.

```powershell
git clone https://github.com/Mauricio1806/FIN-TRADER.git
cd FIN-TRADER
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m src.main --window close_br
```

Após a execução, o brief estará em `reports/YYYY-MM-DD_HHMM_close_br.md`.

## Configuração

### Secrets do GitHub (opcionais)

Em `Settings → Secrets and variables → Actions`:

- `TELEGRAM_TOKEN`: token do bot do Telegram
- `TELEGRAM_CHAT_ID`: chat ID para receber notificações
- `WEBHOOK_URL`: URL HTTPS para POST do payload do brief

Sistema opera sem nenhum desses configurados.

### Personalizando a watchlist

Edite `config/watchlist.yaml`. Marque `active: false` para desativar um ticker sem removê-lo. Ajuste `weight` por região.

### Personalizando pesos das camadas

Edite `config/weights.yaml`. Os pesos não precisam somar 1 (são normalizados). Aumente pesos das camadas em que você confia mais para o seu estilo.

## Estrutura do brief

Cada brief inclui:

1. **TL;DR** — regime, top 3 sinais BR, evento principal
2. **Brasil (Foco Principal)** — macro BR, sinais por classificação, reversões
3. **EUA (Secundário)** — sinais compactos
4. **Europa (Secundário)** — sinais compactos
5. **Ásia (Contextual)** — sinais compactos
6. **Macro Global** — VIX, Treasury, DXY, índices, FX
7. **Portfólio Simulado** — hit-rate, retorno acumulado, exposição atual
8. **Agenda do Próximo Pregão**
9. **Anomalias / Data Quality**

## Dashboard

`https://mauricio1806.github.io/FIN-TRADER/`

HTML estático servido via GitHub Pages, lista todos os briefs em `reports/` e renderiza markdown com tabelas estilizadas. Sem build, sem backend, atualização automática quando workflow commita novo brief.

## Schema SQLite

Banco em `db/signals.db`:

- `signals` — todos os sinais com camadas e classificação
- `positions_simulated` — paper trading em %
- `macro_snapshots` — séries macro por região
- `daily_briefs` — índice de briefs gerados
- `data_quality_checks` — anomalias detectadas
- `errors_log` — exceções não-fatais

## Modelo

Versão: `0.2.0`

Todo sinal carrega `data_hash` (SHA256 dos preços usados) e `model_version` para auditoria.
