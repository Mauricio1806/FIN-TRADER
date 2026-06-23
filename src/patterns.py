"""Detecção de padrões cross-asset e geração de insights narrativos.
Sem LLM — heurísticas determinísticas em cima dos scores e camadas.
"""
import statistics
from collections import defaultdict

REGION_NAMES = {"br": "Brasil", "us": "EUA", "eu": "Europa", "asia": "Ásia"}

SECTOR_LABELS = {
    "oil_gas": "Petróleo e Gás",
    "mining": "Mineração",
    "banks": "Bancos",
    "financials": "Financeiras",
    "industrials": "Industriais",
    "consumer": "Consumo",
    "transport": "Transportes",
    "paper_pulp": "Papel e Celulose",
    "utilities": "Utilities",
    "health": "Saúde",
    "retail": "Varejo",
    "food": "Alimentos",
    "tech": "Tecnologia",
    "semis": "Semicondutores",
    "auto": "Automotivo",
    "luxury": "Luxo",
    "ecommerce": "E-commerce",
    "etf": "ETFs",
    "index": "Índices",
    "volatility": "Volatilidade",
    "fx": "Câmbio",
}


def build_sector_map(watchlist: dict) -> dict[str, str]:
    """Ticker -> sector (string)."""
    out = {}
    for region in ("br", "us", "eu", "asia"):
        for t in watchlist[region]["tickers"]:
            out[t["symbol"]] = t.get("sector", "other")
    return out


def build_name_map(watchlist: dict) -> dict[str, str]:
    out = {}
    for region in ("br", "us", "eu", "asia"):
        for t in watchlist[region]["tickers"]:
            out[t["symbol"]] = t.get("name", t["symbol"])
    return out


def group_by_sector(signals: list, sector_map: dict) -> dict[str, list]:
    grouped = defaultdict(list)
    for s in signals:
        sec = sector_map.get(s["ticker"], "other")
        grouped[sec].append(s)
    return dict(grouped)


def sector_consensus(signals: list) -> dict | None:
    """Estatísticas de um conjunto de sinais (ex.: setor)."""
    if not signals:
        return None
    scores = [s["score"] for s in signals]
    n = len(scores)
    avg = statistics.mean(scores)
    std = statistics.stdev(scores) if n > 1 else 0.0
    outlier = max(signals, key=lambda s: abs(s["score"] - avg)) if n > 1 else signals[0]
    if avg > 0.25:
        consensus = "claramente positivo"
    elif avg > 0.10:
        consensus = "levemente positivo"
    elif avg < -0.25:
        consensus = "claramente negativo"
    elif avg < -0.10:
        consensus = "levemente negativo"
    else:
        consensus = "neutro"
    if std < 0.12:
        cohesion = "alta coesão"
    elif std < 0.25:
        cohesion = "coesão moderada"
    else:
        cohesion = "alta dispersão"
    return {
        "n": n,
        "avg": round(avg, 3),
        "std": round(std, 3),
        "min": round(min(scores), 3),
        "max": round(max(scores), 3),
        "outlier_ticker": outlier["ticker"],
        "outlier_score": outlier["score"],
        "outlier_distance": round(outlier["score"] - avg, 3),
        "consensus": consensus,
        "cohesion": cohesion,
    }


def sector_narrative(sector_key: str, stats: dict) -> str:
    label = SECTOR_LABELS.get(sector_key, sector_key.title())
    parts = [
        f"**{label}** ({stats['n']} ativo{'s' if stats['n'] > 1 else ''}): "
        f"viés {stats['consensus']} com média {stats['avg']:+.2f}, "
        f"{stats['cohesion']} (desvio {stats['std']:.2f})."
    ]
    if stats["n"] > 1 and abs(stats["outlier_distance"]) > 0.20:
        direction = "acima" if stats["outlier_distance"] > 0 else "abaixo"
        parts.append(
            f"Destaque: **{stats['outlier_ticker']}** ({stats['outlier_score']:+.2f}) "
            f"está {abs(stats['outlier_distance']):.2f} {direction} da média do setor."
        )
    return " ".join(parts)


def narrative_macro(macro: dict) -> list[str]:
    """Parágrafos narrativos do contexto macroeconômico."""
    paragraphs = []

    br = macro["br"]
    selic = br.get("selic")
    ipca = br.get("ipca_12m")
    usdbrl = br.get("usdbrl")

    br_parts = []
    if selic is not None:
        if selic > 13:
            br_parts.append(
                f"Selic em **{selic:.2f}%** mantém viés monetário restritivo, "
                f"penalizando crédito e ativos de risco doméstico"
            )
        elif selic < 8:
            br_parts.append(
                f"Selic em **{selic:.2f}%** indica política monetária expansionista, "
                f"favorável a ativos de risco e ações de crescimento"
            )
        else:
            br_parts.append(f"Selic em **{selic:.2f}%** em zona neutra")

    if ipca is not None:
        if ipca > 5:
            br_parts.append(
                f"IPCA 12m em **{ipca:.2f}%** acima do teto da meta — "
                f"reduz espaço para flexibilização monetária"
            )
        elif ipca < 3:
            br_parts.append(
                f"IPCA 12m em **{ipca:.2f}%** abaixo do centro da meta — "
                f"abre espaço para corte de juros"
            )
        else:
            br_parts.append(f"IPCA 12m em **{ipca:.2f}%** próximo à meta")

    if usdbrl is not None:
        br_parts.append(f"USD/BRL em **{usdbrl:.4f}**")

    if br_parts:
        paragraphs.append("**Brasil.** " + "; ".join(br_parts) + ".")

    us = macro["us"]
    vix = us.get("vix")
    t10 = us.get("treasury_10y")
    dxy = us.get("dxy")
    us_parts = []
    if vix is not None:
        if vix > 22:
            us_parts.append(
                f"VIX em **{vix:.1f}** sinaliza aversão a risco elevada — "
                f"esperado spillover de cautela para emergentes"
            )
        elif vix < 14:
            us_parts.append(
                f"VIX em **{vix:.1f}** indica complacência ou apetite robusto — "
                f"janela típica de busca por yield"
            )
        else:
            us_parts.append(f"VIX em **{vix:.1f}** em zona neutra")
    if t10 is not None:
        us_parts.append(f"Treasury 10Y em **{t10:.2f}%**")
    if dxy is not None:
        if dxy > 105:
            us_parts.append(
                f"DXY em **{dxy:.2f}** com dólar forte — pressão sobre EM e commodities"
            )
        elif dxy < 100:
            us_parts.append(
                f"DXY em **{dxy:.2f}** com dólar enfraquecido — alívio para EM"
            )
        else:
            us_parts.append(f"DXY em **{dxy:.2f}**")
    if us_parts:
        paragraphs.append("**EUA.** " + "; ".join(us_parts) + ".")

    asia = macro["asia"]
    asia_parts = []
    if asia.get("hsi"):
        asia_parts.append(f"Hang Seng em {asia['hsi']:,.0f}")
    if asia.get("nikkei"):
        asia_parts.append(f"Nikkei em {asia['nikkei']:,.0f}")
    if asia.get("usdcny"):
        asia_parts.append(f"USD/CNY em {asia['usdcny']:.4f}")
    if asia_parts:
        paragraphs.append("**Ásia (contextual).** " + "; ".join(asia_parts) + ".")

    return paragraphs


def cross_region_view(signals_by_region: dict) -> dict:
    avgs = {}
    for region, sigs in signals_by_region.items():
        if sigs:
            avgs[region] = round(statistics.mean(s["score"] for s in sigs), 3)
    ranked = sorted(avgs.items(), key=lambda x: x[1], reverse=True)
    return {"averages": avgs, "ranked": ranked}


def top_layers_today(all_signals: list) -> list[tuple[str, float]]:
    if not all_signals:
        return []
    layer_contrib = defaultdict(list)
    for s in all_signals:
        for layer_name, value in s.get("layers", {}).items():
            layer_contrib[layer_name].append(value)
    layer_avg = {l: statistics.mean(v) for l, v in layer_contrib.items() if v}
    return sorted(layer_avg.items(), key=lambda x: abs(x[1]), reverse=True)


def best_and_worst_global(all_signals: list, k: int = 5) -> tuple[list, list]:
    if not all_signals:
        return [], []
    ranked = sorted(all_signals, key=lambda s: s["score"], reverse=True)
    return ranked[:k], ranked[-k:][::-1]


def cross_region_sector_divergence(signals_by_region: dict, sector_map: dict) -> list[dict]:
    """Identifica setores onde BR e US divergem significativamente."""
    out = []
    br_by_sec = defaultdict(list)
    us_by_sec = defaultdict(list)
    for s in signals_by_region.get("br", []):
        br_by_sec[sector_map.get(s["ticker"], "other")].append(s["score"])
    for s in signals_by_region.get("us", []):
        us_by_sec[sector_map.get(s["ticker"], "other")].append(s["score"])
    for sec, br_scores in br_by_sec.items():
        us_scores = us_by_sec.get(sec)
        if not us_scores:
            continue
        br_avg = statistics.mean(br_scores)
        us_avg = statistics.mean(us_scores)
        diff = br_avg - us_avg
        if abs(diff) > 0.25:
            out.append({
                "sector": sec,
                "br_avg": round(br_avg, 3),
                "us_avg": round(us_avg, 3),
                "spread": round(diff, 3),
            })
    return sorted(out, key=lambda x: -abs(x["spread"]))


def generate_insights(signals_by_region: dict, sector_map: dict,
                      name_map: dict, macro: dict) -> list[str]:
    """Bullets narrativos de insights cross-asset."""
    insights = []

    cross = cross_region_view(signals_by_region)
    if len(cross["ranked"]) >= 2:
        top_region, top_avg = cross["ranked"][0]
        bot_region, bot_avg = cross["ranked"][-1]
        spread = top_avg - bot_avg
        if spread > 0.25:
            insights.append(
                f"**Descorrelação regional:** {REGION_NAMES[top_region]} ({top_avg:+.2f}) "
                f"vs {REGION_NAMES[bot_region]} ({bot_avg:+.2f}) com spread de {spread:.2f}. "
                f"Sugere oportunidade de alpha relativo em {REGION_NAMES[top_region]} "
                f"e/ou hedge em {REGION_NAMES[bot_region]}."
            )

    all_sigs = [s for sigs in signals_by_region.values() for s in sigs]
    drivers = top_layers_today(all_sigs)
    if drivers:
        top_layer, top_val = drivers[0]
        direction = "positivo" if top_val > 0 else "negativo"
        layer_labels = {
            "trend_long": "tendência longa", "trend_mid": "tendência média",
            "momentum": "momentum", "volatility": "volatilidade",
            "volume": "volume", "support_resist": "suporte/resistência",
            "correlation": "correlação", "macro": "sensibilidade macro",
            "seasonality": "sazonalidade", "statistical": "estatística",
            "tail_risk": "risco de cauda", "sentiment": "sentimento",
        }
        label = layer_labels.get(top_layer, top_layer)
        insights.append(
            f"**Camada dominante:** {label} com viés agregado {direction} de "
            f"{top_val:+.2f}. Indica que o mercado está sendo movido principalmente "
            f"por esse fator hoje."
        )

    sector_divs = cross_region_sector_divergence(signals_by_region, sector_map)[:3]
    for d in sector_divs:
        sec_label = SECTOR_LABELS.get(d["sector"], d["sector"])
        direction = "alta" if d["spread"] > 0 else "baixa"
        insights.append(
            f"**Setor {sec_label}:** BR ({d['br_avg']:+.2f}) e US ({d['us_avg']:+.2f}) "
            f"divergindo {d['spread']:+.2f}. Brasil relativamente em viés de {direction}."
        )

    vix = macro["us"].get("vix")
    us_sigs = signals_by_region.get("us", [])
    if vix is not None and us_sigs:
        us_avg = statistics.mean(s["score"] for s in us_sigs)
        if vix > 22 and us_avg > 0.15:
            insights.append(
                f"**Contradição:** VIX em {vix:.1f} sinaliza estresse, mas score "
                f"agregado US em {us_avg:+.2f}. Possível resiliência específica ou "
                f"leitura adiantada de fim do evento."
            )
        elif vix < 14 and us_avg < -0.15:
            insights.append(
                f"**Contradição:** VIX baixo em {vix:.1f} sugere complacência, mas score "
                f"agregado US em {us_avg:+.2f}. Atenção a possível reversão."
            )

    selic = macro["br"].get("selic")
    br_sigs = signals_by_region.get("br", [])
    if selic and selic > 13 and br_sigs:
        banks = [s for s in br_sigs if sector_map.get(s["ticker"]) == "banks"]
        if banks:
            banks_avg = statistics.mean(s["score"] for s in banks)
            if banks_avg > 0.20:
                insights.append(
                    f"**Bancos BR x juros altos:** Selic em {selic:.2f}% com bancos "
                    f"em score médio {banks_avg:+.2f}. Consistente — spread bancário "
                    f"se beneficia de juros altos."
                )
            elif banks_avg < -0.20:
                insights.append(
                    f"**Bancos BR x juros altos:** Selic em {selic:.2f}% mas bancos "
                    f"em score médio {banks_avg:+.2f}. Possível preocupação com "
                    f"qualidade de crédito ou compressão de margem."
                )

    return insights
