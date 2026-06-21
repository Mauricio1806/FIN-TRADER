from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import pandas as pd


CLASS_ORDER = {
    "BUY": 0,
    "WATCH_LONG": 1,
    "NEUTRAL": 2,
    "WATCH_SHORT": 3,
    "SELL_AVOID": 4,
}


def _fmt_float(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def _render_rank_table(signals: List[Dict]) -> str:
    lines = [
        "| Ticker | Score | Classificação | Top Camadas |",
        "|---|---:|---|---|",
    ]
    for item in signals:
        top = ", ".join([f"{x['layer']} ({x['contribution']:+.2f})" for x in item.get("top_layers", [])])
        lines.append(
            f"| {item['ticker']} | {item['score']:+.2f} | {item['classification']} | {top} |"
        )
    return "\n".join(lines)


def _next_agenda_lines(timestamp: datetime) -> List[str]:
    return [
        f"- Próximo pregão BR: {timestamp.strftime('%d/%m/%Y')} (acompanhar abertura e fluxo estrangeiro).",
        "- Monitorar fechamento de NY para confirmar direção de risco global.",
        "- Revisar variação de VIX e USD/BRL antes de novas entradas.",
    ]


def generate_brief(signals: List[Dict], macro_snapshot: Dict, timestamp: datetime) -> str:
    ordered = sorted(
        signals,
        key=lambda x: (CLASS_ORDER.get(x["classification"], 99), -x["score"]),
    )

    by_region: Dict[str, List[Dict]] = defaultdict(list)
    for s in ordered:
        by_region[s.get("region", "outros")].append(s)

    top_buys = [s for s in ordered if s["classification"] in {"BUY", "WATCH_LONG"}][:3]
    top_risks = [s for s in ordered if s["classification"] in {"SELL_AVOID", "WATCH_SHORT"}][:3]

    drift_msg = macro_snapshot.get("drift_alert")

    lines: List[str] = []
    lines.append(f"# FIN-TRADER Brief — {timestamp.strftime('%d/%m/%Y %H:%M')} BRT")
    lines.append("")
    lines.append("## TL;DR")
    if top_buys:
        buys_txt = ", ".join([f"{s['ticker']} ({s['score']:+.2f})" for s in top_buys])
        lines.append(f"- Viés comprador prioritário: {buys_txt}.")
    else:
        lines.append("- Sem ativos com viés comprador forte nesta janela.")

    if top_risks:
        risks_txt = ", ".join([f"{s['ticker']} ({s['score']:+.2f})" for s in top_risks])
        lines.append(f"- Principais pontos de atenção: {risks_txt}.")
    else:
        lines.append("- Sem sinais críticos de venda/evitar no conjunto monitorado.")

    lines.append(
        f"- Macro: VIX {_fmt_float(macro_snapshot.get('vix', float('nan')))}, "
        f"USD/BRL {_fmt_float(macro_snapshot.get('usdbrl', float('nan')))}, "
        f"Selic {_fmt_float(macro_snapshot.get('selic', float('nan')))}%."
    )
    if drift_msg:
        lines.append(f"- Alerta de drift: {drift_msg}")

    lines.append("")
    lines.append("## Brasil (foco)")
    br_signals = by_region.get("brasil", [])
    if br_signals:
        lines.append(_render_rank_table(br_signals))
    else:
        lines.append("Sem sinais para ativos brasileiros nesta execução.")

    lines.append("")
    lines.append("## US (secundário)")
    us_signals = by_region.get("usa", [])
    if us_signals:
        lines.append(_render_rank_table(us_signals))
    else:
        lines.append("Sem sinais para ativos dos EUA nesta execução.")

    lines.append("")
    lines.append("## Macro Snapshot")
    lines.append("| Indicador | Valor | Fonte |")
    lines.append("|---|---:|---|")
    lines.append(f"| VIX | {_fmt_float(macro_snapshot.get('vix', float('nan')))} | yfinance |")
    lines.append(f"| USD/BRL | {_fmt_float(macro_snapshot.get('usdbrl', float('nan')))} | yfinance/BCB |")
    lines.append(f"| Selic (%) | {_fmt_float(macro_snapshot.get('selic', float('nan')))} | BCB SGS 432 |")
    lines.append(f"| IPCA (índice) | {_fmt_float(macro_snapshot.get('ipca', float('nan')))} | BCB SGS 13522 |")
    lines.append("")

    lines.append("## Próxima Agenda")
    lines.extend(_next_agenda_lines(timestamp))
    lines.append("")
    lines.append("---")
    lines.append("Documento gerado automaticamente pelo FIN-TRADER.")

    return "\n".join(lines)
