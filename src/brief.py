"""Daily Brief com narrativa interpretativa e cobertura completa dos 48 ativos."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import statistics
from .config import REPORTS_DIR, load_watchlist
from .patterns import (
    build_sector_map, build_name_map, group_by_sector, sector_consensus,
    sector_narrative, narrative_macro, cross_region_view, top_layers_today,
    best_and_worst_global, generate_insights, REGION_NAMES, SECTOR_LABELS,
)
from . import __version__

BRT = ZoneInfo("America/Bahia")

WINDOW_LABELS = {
    "asia_close": "Fechamento Ásia + Pré-Europa",
    "europe_open": "Abertura Europa + Pré-BR",
    "pre_market": "Pré-Abertura B3",
    "mid_morning": "Meio da Manhã",
    "afternoon": "Tarde Cross-Asset",
    "close_br": "Fechamento B3",
    "close_us": "Pós-Fechamento US",
    "daily_wrap": "Consolidado do Dia",
}


def _fmt(v, decimals=2, suffix=""):
    if v is None:
        return "n/d"
    try:
        return f"{float(v):.{decimals}f}{suffix}"
    except Exception:
        return str(v)


def _signal_row(s: dict, name_map: dict, sector_map: dict) -> str:
    name = name_map.get(s["ticker"], s["ticker"])
    sec = SECTOR_LABELS.get(sector_map.get(s["ticker"], ""), "—")
    contribs = ", ".join(f"{n} ({v:+.2f})" for n, v in s.get("top_contributors", []))
    alloc = f"{s['suggested_alloc_pct']:.1f}%" if s.get("suggested_alloc_pct", 0) > 0 else "—"
    return (
        f"| {s['ticker']} | {name} | {sec} | {s['score']:+.3f} | "
        f"{s['classification']} | {alloc} | {s['stop_pct']:+.1f}% | "
        f"{s['target_pct']:+.1f}% | {contribs} |"
    )


def _full_table(signals: list, name_map: dict, sector_map: dict) -> str:
    if not signals:
        return "_Sem sinais._\n"
    header = (
        "| Ticker | Nome | Setor | Score | Classificação | Aloc % | Stop | Alvo | Top Camadas |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
    )
    rows = sorted(signals, key=lambda s: -s["score"])
    return header + "\n".join(_signal_row(s, name_map, sector_map) for s in rows) + "\n"


def _compact_table(signals: list, name_map: dict) -> str:
    if not signals:
        return "_Sem sinais._\n"
    header = "| Ticker | Nome | Score | Classificação |\n|---|---|---|---|\n"
    rows = sorted(signals, key=lambda s: -s["score"])
    body = "\n".join(
        f"| {s['ticker']} | {name_map.get(s['ticker'], s['ticker'])} | "
        f"{s['score']:+.3f} | {s['classification']} |"
        for s in rows
    )
    return header + body + "\n"


def _sector_summary_table(sector_stats: dict[str, dict]) -> str:
    if not sector_stats:
        return ""
    header = (
        "| Setor | N | Score Médio | Mín | Máx | Dispersão | Leitura |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for sec_key, stats in sorted(sector_stats.items(), key=lambda x: -x[1]["avg"]):
        label = SECTOR_LABELS.get(sec_key, sec_key)
        rows.append(
            f"| {label} | {stats['n']} | {stats['avg']:+.3f} | "
            f"{stats['min']:+.3f} | {stats['max']:+.3f} | "
            f"{stats['std']:.3f} | {stats['consensus']}, {stats['cohesion']} |"
        )
    return header + "\n".join(rows) + "\n"


def _macro_table_br(macro: dict) -> str:
    br = macro["br"]
    lines = ["| Indicador | Valor | Fonte |", "|---|---|---|"]
    lines.append(f"| Selic (%) | {_fmt(br.get('selic'))} | BCB SGS 432 |")
    lines.append(f"| IPCA 12m (%) | {_fmt(br.get('ipca_12m'))} | BCB SGS 13522 |")
    lines.append(f"| IPCA-15 (%) | {_fmt(br.get('ipca15'))} | BCB SGS 7478 |")
    lines.append(f"| USD/BRL | {_fmt(br.get('usdbrl'), 4)} | BCB SGS 1 |")
    lines.append(f"| IBC-Br | {_fmt(br.get('ibcbr'))} | BCB SGS 24364 |")
    return "\n".join(lines) + "\n"


def _macro_table_global(macro: dict) -> str:
    lines = ["| Região | Indicador | Valor |", "|---|---|---|"]
    us = macro["us"]
    lines.append(f"| US | VIX | {_fmt(us.get('vix'))} |")
    lines.append(f"| US | Treasury 10Y (%) | {_fmt(us.get('treasury_10y'))} |")
    lines.append(f"| US | DXY | {_fmt(us.get('dxy'))} |")
    eu = macro["eu"]
    lines.append(f"| EU | EuroStoxx 50 | {_fmt(eu.get('stoxx50'))} |")
    lines.append(f"| EU | EUR/USD | {_fmt(eu.get('eurusd'), 4)} |")
    asia = macro["asia"]
    lines.append(f"| Ásia | Hang Seng | {_fmt(asia.get('hsi'), 0)} |")
    lines.append(f"| Ásia | Nikkei | {_fmt(asia.get('nikkei'), 0)} |")
    lines.append(f"| Ásia | USD/CNY | {_fmt(asia.get('usdcny'), 4)} |")
    lines.append(f"| Ásia | USD/JPY | {_fmt(asia.get('usdjpy'), 2)} |")
    return "\n".join(lines) + "\n"


def _portfolio_table(metrics: dict, summary: dict) -> str:
    lines = ["| Métrica | Valor |", "|---|---|"]
    lines.append(f"| Trades fechados | {metrics['n_trades']} |")
    lines.append(f"| Hit-rate | {_fmt(metrics['hit_rate'])}% |")
    lines.append(f"| Retorno acumulado | {_fmt(metrics['cum_return_pct'])}% |")
    lines.append(f"| Melhor trade | {_fmt(metrics['best'])}% |")
    lines.append(f"| Pior trade | {_fmt(metrics['worst'])}% |")
    lines.append(f"| Exposição atual | {_fmt(summary['total'])}% |")
    lines.append(f"| Cash | {_fmt(summary['cash'])}% |")
    return "\n".join(lines) + "\n"


def _ranking_table(signals: list, name_map: dict) -> str:
    if not signals:
        return "_Sem dados._\n"
    header = "| # | Ticker | Nome | Score | Classificação |\n|---|---|---|---|---|\n"
    rows = []
    for i, s in enumerate(signals, 1):
        name = name_map.get(s["ticker"], s["ticker"])
        rows.append(
            f"| {i} | {s['ticker']} | {name} | {s['score']:+.3f} | {s['classification']} |"
        )
    return header + "\n".join(rows) + "\n"


def _closures_section(closures: list) -> str:
    if not closures:
        return "_Sem reversões nesta janela._\n"
    lines = ["| Ticker | Motivo | P&L % | Contribuição % |", "|---|---|---|---|"]
    for c in closures:
        lines.append(
            f"| {c['ticker']} | {c['reason']} | {c['pnl_pct']:+.2f}% | "
            f"{c['contrib']:+.3f}% |"
        )
    return "\n".join(lines) + "\n"


def _anomalies_section(anomalies: list) -> str:
    if not anomalies:
        return "_Todos os tickers retornaram dados frescos. Nenhuma anomalia detectada._\n"
    lines = ["| Ticker | Problema |", "|---|---|"]
    for a in anomalies:
        lines.append(f"| {a['ticker']} | {a['detail']} |")
    return "\n".join(lines) + "\n"


def _agenda_section(agenda: list) -> str:
    if not agenda:
        return "_Sem eventos macro de destaque programados._\n"
    return "\n".join(f"- {item}" for item in agenda) + "\n"


def _leitura_geral(signals_by_region: dict, macro: dict, name_map: dict) -> str:
    """Parágrafos de abertura: regime, viés geral, destaques."""
    paragraphs = []
    paragraphs.extend(narrative_macro(macro))

    cross = cross_region_view(signals_by_region)
    if cross["averages"]:
        avgs_str = ", ".join(
            f"{REGION_NAMES[r]} ({v:+.2f})"
            for r, v in sorted(cross["averages"].items(), key=lambda x: -x[1])
        )
        paragraphs.append(f"**Viés agregado por região:** {avgs_str}.")

    all_sigs = [s for sigs in signals_by_region.values() for s in sigs]
    best, worst = best_and_worst_global(all_sigs, k=5)
    if best:
        best_str = ", ".join(
            f"{s['ticker']} ({s['score']:+.2f})" for s in best
        )
        paragraphs.append(f"**Top 5 globais (compra):** {best_str}.")
    if worst:
        worst_str = ", ".join(
            f"{s['ticker']} ({s['score']:+.2f})" for s in worst
        )
        paragraphs.append(f"**Top 5 globais (cautela/short):** {worst_str}.")

    return "\n\n".join(paragraphs) + "\n"


def _daily_wrap_section(signals_by_region: dict, sector_map: dict) -> str:
    """Seção exclusiva do daily_wrap: consolida e narra o dia inteiro."""
    from .db import conn as db_conn
    from datetime import datetime, timedelta

    today = datetime.utcnow().date()
    today_start = datetime(today.year, today.month, today.day).isoformat()

    lines = []
    try:
        with db_conn() as c:
            rows = c.execute(
                "SELECT window, COUNT(*) as n, AVG(score) as avg_score "
                "FROM signals WHERE ts_utc >= ? GROUP BY window ORDER BY MIN(ts_utc)",
                (today_start,)
            ).fetchall()

        if rows:
            lines.append("### Janelas Executadas Hoje\n")
            lines.append("| Janela | Sinais Gerados | Score Médio |")
            lines.append("|---|---|---|")
            for r in rows:
                w_label = WINDOW_LABELS.get(r["window"], r["window"])
                lines.append(f"| {w_label} | {r['n']} | {r['avg_score']:+.3f} |")
            lines.append("")

        with db_conn() as c:
            class_rows = c.execute(
                "SELECT ticker, region, classification, score "
                "FROM signals WHERE ts_utc >= ? "
                "ORDER BY ticker, ts_utc",
                (today_start,)
            ).fetchall()

        ticker_history = {}
        for r in class_rows:
            ticker_history.setdefault(r["ticker"], []).append({
                "class": r["classification"], "score": r["score"], "region": r["region"]
            })

        flipped = []
        for ticker, hist in ticker_history.items():
            if len(hist) < 2:
                continue
            first_class = hist[0]["class"]
            last_class = hist[-1]["class"]
            if first_class != last_class:
                flipped.append({
                    "ticker": ticker, "region": hist[0]["region"],
                    "from": first_class, "to": last_class,
                    "first_score": hist[0]["score"], "last_score": hist[-1]["score"],
                })

        if flipped:
            lines.append("### Mudanças de Classificação ao Longo do Dia\n")
            lines.append("| Ticker | Região | De | Para | Δ Score |")
            lines.append("|---|---|---|---|---|")
            for f in sorted(flipped, key=lambda x: abs(x["last_score"] - x["first_score"]),
                            reverse=True)[:15]:
                delta = f["last_score"] - f["first_score"]
                lines.append(
                    f"| {f['ticker']} | {f['region'].upper()} | {f['from']} | "
                    f"{f['to']} | {delta:+.3f} |"
                )
            lines.append("")
        else:
            lines.append("_Nenhuma mudança de classificação relevante no dia._\n")

    except Exception as e:
        lines.append(f"_Histórico do dia indisponível: {e}_\n")

    return "\n".join(lines) + "\n"


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

    wl = load_watchlist()
    sector_map = build_sector_map(wl)
    name_map = build_name_map(wl)

    md = []
    md.append(f"# FIN-TRADER Brief — {now_brt.strftime('%d/%m/%Y %H:%M BRT')} — {window_label}\n")

    if window == "daily_wrap":
        md.append("## Consolidado do Dia\n")
        md.append("_Resumo das janelas executadas hoje, com análise de mudanças de classificação ao longo do dia._\n\n")
        md.append(_daily_wrap_section(signals_by_region, sector_map))

    # Seção 1: Leitura Geral
    md.append("## Leitura Geral\n")
    md.append(_leitura_geral(signals_by_region, macro, name_map))

    # Seção 2: Insights Cross-Asset
    insights = generate_insights(signals_by_region, sector_map, name_map, macro)
    md.append("\n## Insights Cross-Asset\n")
    if insights:
        md.append("\n".join(f"- {ins}" for ins in insights) + "\n")
    else:
        md.append("_Sem padrões cross-asset relevantes detectados nesta janela._\n")

    # Seção 3: Camada Dominante / Drivers
    all_sigs = [s for sigs in signals_by_region.values() for s in sigs]
    drivers = top_layers_today(all_sigs)
    md.append("\n## Camadas Dominantes Hoje (Top 5)\n")
    if drivers:
        layer_labels = {
            "trend_long": "Tendência Longa", "trend_mid": "Tendência Média",
            "momentum": "Momentum", "volatility": "Volatilidade",
            "volume": "Volume", "support_resist": "Suporte/Resistência",
            "correlation": "Correlação", "macro": "Macro",
            "seasonality": "Sazonalidade", "statistical": "Estatística",
            "tail_risk": "Risco de Cauda", "sentiment": "Sentimento",
        }
        rows = ["| # | Camada | Viés Agregado |", "|---|---|---|"]
        for i, (layer, val) in enumerate(drivers[:5], 1):
            label = layer_labels.get(layer, layer)
            rows.append(f"| {i} | {label} | {val:+.3f} |")
        md.append("\n".join(rows) + "\n")
    else:
        md.append("_n/d_\n")

    # Seção 4: Brasil — Foco Principal
    md.append("\n## Brasil — Foco Principal\n")
    md.append("### Macro BR\n")
    md.append(_macro_table_br(macro))

    br_signals = signals_by_region.get("br", [])
    br_by_sector = group_by_sector(br_signals, sector_map)
    br_sector_stats = {
        sec: sector_consensus(sigs)
        for sec, sigs in br_by_sector.items()
        if sigs
    }

    md.append("\n### Visão Setorial BR\n")
    md.append(_sector_summary_table(br_sector_stats))

    md.append("\n### Análise Setorial Detalhada\n")
    for sec_key in sorted(br_by_sector.keys(), key=lambda k: -br_sector_stats[k]["avg"]):
        stats = br_sector_stats[sec_key]
        md.append(sector_narrative(sec_key, stats) + "\n")
        md.append(_full_table(br_by_sector[sec_key], name_map, sector_map))
        md.append("\n")

    md.append("\n### Reversões/Saídas BR\n")
    md.append(_closures_section([c for c in closures if c.get("region") == "br"]))

    # Seção 5: EUA
    md.append("\n## EUA — Secundário\n")
    us_signals = signals_by_region.get("us", [])
    if us_signals:
        us_avg = round(statistics.mean(s["score"] for s in us_signals), 3)
        md.append(f"_Score agregado: **{us_avg:+.3f}** ({len(us_signals)} ativos)._\n\n")
    md.append(_full_table(us_signals, name_map, sector_map))

    # Seção 6: Europa
    md.append("\n## Europa — Secundário\n")
    eu_signals = signals_by_region.get("eu", [])
    if eu_signals:
        eu_avg = round(statistics.mean(s["score"] for s in eu_signals), 3)
        md.append(f"_Score agregado: **{eu_avg:+.3f}** ({len(eu_signals)} ativos)._\n\n")
    md.append(_full_table(eu_signals, name_map, sector_map))

    # Seção 7: Ásia
    md.append("\n## Ásia — Contextual\n")
    asia_signals = signals_by_region.get("asia", [])
    if asia_signals:
        asia_avg = round(statistics.mean(s["score"] for s in asia_signals), 3)
        md.append(f"_Score agregado: **{asia_avg:+.3f}** ({len(asia_signals)} ativos)._\n\n")
    md.append(_full_table(asia_signals, name_map, sector_map))

    # Seção 8: Macro Global
    md.append("\n## Macro Global\n")
    md.append(_macro_table_global(macro))

    # Seção 9: Ranking Global
    md.append("\n## Ranking Global Completo (todos os ativos)\n")
    all_ranked = sorted(all_sigs, key=lambda s: -s["score"])
    md.append(_ranking_table(all_ranked, name_map))

    # Seção 10: Portfólio
    md.append("\n## Portfólio Simulado\n")
    md.append(_portfolio_table(metrics, exposure_summary))

    # Seção 11: Agenda
    md.append("\n## Agenda do Próximo Pregão\n")
    md.append(_agenda_section(agenda))

    # Seção 12: Anomalias
    md.append("\n## Anomalias / Data Quality\n")
    md.append(_anomalies_section(anomalies))

    md.append("\n---\n")
    md.append(
        f"FIN-TRADER v{__version__} | Janela: {window} | "
        f"Gerado em: {now_brt.isoformat()} | "
        f"Total de ativos analisados: {len(all_sigs)}\n"
    )

    path.write_text("\n".join(md), encoding="utf-8")
    return path
