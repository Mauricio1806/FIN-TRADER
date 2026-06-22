"""Gera o Daily Brief em markdown com seções acionáveis."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from .config import REPORTS_DIR
from . import __version__

BRT = ZoneInfo("America/Bahia")

REGIME_LABELS_GLOBAL = {
    "risk_on": "Risk-On (apetite ao risco elevado)",
    "risk_off": "Risk-Off (aversão ao risco)",
    "transition": "Transição (VIX em zona neutra)",
    "divergent": "Divergente entre regiões",
}
REGIME_LABELS_BR = {
    "tight_monetary": "Política monetária restritiva (Selic alta)",
    "loose_monetary": "Política monetária expansionista (Selic baixa)",
    "neutral_monetary": "Política monetária neutra",
}

WINDOW_LABELS = {
    "pre_market": "Pré-Abertura B3",
    "mid_morning": "Meio da Manhã",
    "afternoon": "Tarde",
    "close_br": "Fechamento B3",
    "close_us": "Pós Fechamento US",
}


def _fmt(v, decimals=2, suffix=""):
    if v is None:
        return "n/d"
    try:
        return f"{float(v):.{decimals}f}{suffix}"
    except Exception:
        return str(v)


def _tl_dr(signals_by_region, macro, agenda):
    br = signals_by_region.get("br", [])
    top_br = sorted([s for s in br if s["score"] > 0.1], key=lambda x: -x["score"])[:3]
    regime_br = REGIME_LABELS_BR.get(macro["regime"]["br"], macro["regime"]["br"])
    regime_global = REGIME_LABELS_GLOBAL.get(macro["regime"]["global"], macro["regime"]["global"])
    lines = []
    lines.append(f"Regime: {regime_br} | Global: {regime_global}.")
    if top_br:
        names = ", ".join(f"{s['ticker']} (+{s['score']:.2f})" for s in top_br)
        lines.append(f"Top sinais BR: {names}.")
    else:
        lines.append("Sem sinais BR de alta convicção no momento.")
    if agenda:
        lines.append(f"Próximo pregão: {agenda[0]}")
    return "\n".join(lines)


def _signal_table_br(signals):
    if not signals:
        return "_Nenhum sinal nesta faixa._\n"
    header = "| Ticker | Score | Alocação % | Stop % | Alvo % | Top 3 Camadas |\n"
    header += "|---|---|---|---|---|---|\n"
    rows = []
    for s in signals:
        top = ", ".join(f"{n} ({v:+.2f})" for n, v in s["top_contributors"])
        alloc = f"{s['suggested_alloc_pct']:.1f}%" if s["suggested_alloc_pct"] > 0 else "—"
        rows.append(
            f"| {s['ticker']} | {s['score']:+.3f} | {alloc} | "
            f"{s['stop_pct']:+.1f}% | {s['target_pct']:+.1f}% | {top} |"
        )
    return header + "\n".join(rows) + "\n"


def _signal_table_compact(signals):
    if not signals:
        return "_Nenhum sinal._\n"
    header = "| Ticker | Score | Classificação |\n|---|---|---|\n"
    rows = [f"| {s['ticker']} | {s['score']:+.3f} | {s['classification']} |" for s in signals]
    return header + "\n".join(rows) + "\n"


def _macro_table_br(macro):
    br = macro["br"]
    lines = ["| Indicador | Valor | Fonte |", "|---|---|---|"]
    lines.append(f"| Selic (%) | {_fmt(br.get('selic'))} | BCB SGS 432 |")
    lines.append(f"| IPCA 12m (%) | {_fmt(br.get('ipca_12m'))} | BCB SGS 13522 |")
    lines.append(f"| IPCA-15 (%) | {_fmt(br.get('ipca15'))} | BCB SGS 7478 |")
    lines.append(f"| USD/BRL | {_fmt(br.get('usdbrl'), 4)} | BCB SGS 1 |")
    lines.append(f"| IBC-Br | {_fmt(br.get('ibcbr'))} | BCB SGS 24364 |")
    return "\n".join(lines) + "\n"


def _macro_table_global(macro):
    lines = ["| Região | Indicador | Valor |", "|---|---|---|"]
    us = macro["us"]
    lines.append(f"| US | VIX | {_fmt(us.get('vix'))} |")
    lines.append(f"| US | Treasury 10Y | {_fmt(us.get('treasury_10y'))} |")
    lines.append(f"| US | DXY | {_fmt(us.get('dxy'))} |")
    eu = macro["eu"]
    lines.append(f"| EU | EuroStoxx 50 | {_fmt(eu.get('stoxx50'))} |")
    lines.append(f"| EU | EUR/USD | {_fmt(eu.get('eurusd'), 4)} |")
    asia = macro["asia"]
    lines.append(f"| Asia | Hang Seng | {_fmt(asia.get('hsi'))} |")
    lines.append(f"| Asia | Nikkei | {_fmt(asia.get('nikkei'))} |")
    lines.append(f"| Asia | USD/CNY | {_fmt(asia.get('usdcny'), 4)} |")
    lines.append(f"| Asia | USD/JPY | {_fmt(asia.get('usdjpy'), 2)} |")
    return "\n".join(lines) + "\n"


def _portfolio_table(metrics, summary):
    lines = ["| Métrica | Valor |", "|---|---|"]
    lines.append(f"| Trades fechados | {metrics['n_trades']} |")
    lines.append(f"| Hit-rate | {_fmt(metrics['hit_rate'])}% |")
    lines.append(f"| Retorno acumulado | {_fmt(metrics['cum_return_pct'])}% |")
    lines.append(f"| Melhor trade | {_fmt(metrics['best'])}% |")
    lines.append(f"| Pior trade | {_fmt(metrics['worst'])}% |")
    lines.append(f"| Exposição atual | {_fmt(summary['total'])}% |")
    lines.append(f"| Cash | {_fmt(summary['cash'])}% |")
    return "\n".join(lines) + "\n"


def _closures_section(closures):
    if not closures:
        return "_Sem reversões hoje._\n"
    lines = ["| Ticker | Motivo | P&L % | Contribuição |", "|---|---|---|---|"]
    for c in closures:
        lines.append(
            f"| {c['ticker']} | {c['reason']} | {c['pnl_pct']:+.2f}% | {c['contrib']:+.3f}% |"
        )
    return "\n".join(lines) + "\n"


def _anomalies_section(anomalies):
    if not anomalies:
        return "_Sem anomalias detectadas. Todos os tickers retornaram dados frescos._\n"
    lines = ["| Ticker | Problema |", "|---|---|"]
    for a in anomalies:
        lines.append(f"| {a['ticker']} | {a['detail']} |")
    return "\n".join(lines) + "\n"


def _agenda_section(agenda):
    if not agenda:
        return "_Sem eventos programados destacados._\n"
    return "\n".join(f"- {item}" for item in agenda) + "\n"


def generate_brief(
    window: str,
    signals_by_region: dict,
    macro: dict,
    closures: list,
    metrics: dict,
    exposure_summary: dict,
    anomalies: list,
    agenda: list,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now_brt = datetime.now(BRT)
    stamp = now_brt.strftime("%Y-%m-%d_%H%M")
    path = REPORTS_DIR / f"{stamp}_{window}.md"
    window_label = WINDOW_LABELS.get(window, window)

    def filter_signals(region, score_min, score_max):
        return sorted(
            [s for s in signals_by_region.get(region, [])
             if score_min <= s["score"] < score_max],
            key=lambda x: -x["score"]
        )

    br_strong = filter_signals("br", 0.5, 999)
    br_watch = filter_signals("br", 0.1, 0.5)
    br_neg_watch = filter_signals("br", -0.5, -0.1)
    br_avoid = filter_signals("br", -999, -0.5)
    us_strong = filter_signals("us", 0.5, 999)
    us_watch = filter_signals("us", 0.1, 0.5)
    us_avoid = filter_signals("us", -999, -0.1)
    eu_signals = sorted(signals_by_region.get("eu", []), key=lambda x: -x["score"])
    asia_signals = sorted(signals_by_region.get("asia", []), key=lambda x: -x["score"])

    md = []
    md.append(f"# Brief — {now_brt.strftime('%d/%m/%Y %H:%M BRT')} — {window_label}\n")
    md.append("## TL;DR\n")
    md.append(_tl_dr(signals_by_region, macro, agenda) + "\n")

    md.append("\n## Brasil — Foco Principal\n")
    md.append("### Regime Macro BR\n")
    md.append(_macro_table_br(macro))
    md.append(f"\n_Regime detectado: **{REGIME_LABELS_BR.get(macro['regime']['br'], macro['regime']['br'])}**_\n")

    md.append("\n### Sinais Alta Convicção BR (score >= 0.5)\n")
    md.append(_signal_table_br(br_strong))
    md.append("\n### Watchlist BR Longa (0.1 <= score < 0.5)\n")
    md.append(_signal_table_br(br_watch))
    md.append("\n### Watchlist BR Curta (-0.5 < score <= -0.1)\n")
    md.append(_signal_table_br(br_neg_watch))
    md.append("\n### Evitar / Possível Short BR (score <= -0.5)\n")
    md.append(_signal_table_br(br_avoid))
    md.append("\n### Reversões / Saídas BR de Hoje\n")
    md.append(_closures_section([c for c in closures if c.get("region") == "br"]))

    md.append("\n## EUA — Secundário\n")
    md.append("### Sinais Alta Convicção US\n")
    md.append(_signal_table_compact(us_strong))
    md.append("\n### Watchlist US\n")
    md.append(_signal_table_compact(us_watch))
    md.append("\n### Evitar US\n")
    md.append(_signal_table_compact(us_avoid))

    md.append("\n## Europa — Secundário\n")
    md.append(_signal_table_compact(eu_signals))

    md.append("\n## Ásia — Contextual\n")
    md.append(_signal_table_compact(asia_signals))

    md.append("\n## Macro Global\n")
    md.append(_macro_table_global(macro))

    md.append("\n## Performance do Portfólio Simulado\n")
    md.append(_portfolio_table(metrics, exposure_summary))

    md.append("\n## Agenda do Próximo Pregão\n")
    md.append(_agenda_section(agenda))

    md.append("\n## Anomalias / Data Quality\n")
    md.append(_anomalies_section(anomalies))

    md.append("\n---\n")
    md.append(f"Model version: {__version__} | Janela: {window} | "
              f"Gerado em: {now_brt.isoformat()}\n")

    path.write_text("\n".join(md), encoding="utf-8")
    return path
