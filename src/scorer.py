"""Score composto a partir das 12 camadas."""
from .indicators import compute_all_layers, latest_atr


def composite_score(layers_scores: dict[str, float], weights_cfg: dict, region: str) -> float:
    layer_weights = weights_cfg["layers"]
    total_w = sum(layer_weights.get(k, 0) for k in layers_scores.keys())
    if total_w == 0:
        return 0.0
    weighted = sum(layers_scores[k] * layer_weights.get(k, 0) for k in layers_scores.keys())
    score = weighted / total_w
    boost = weights_cfg.get("regional_boost", {}).get(region, 1.0)
    score *= boost
    return max(-1.0, min(1.0, score))


def classify(score: float, weights_cfg: dict) -> str:
    th = weights_cfg["thresholds"]
    if score >= th["buy_strong"]:
        return "BUY"
    if score >= th["buy_watch"]:
        return "WATCH_LONG"
    if score > th["sell_watch"]:
        return "NEUTRAL"
    if score > th["sell_strong"]:
        return "WATCH_SHORT"
    return "SELL_AVOID"


def top_contributors(layers_scores: dict[str, float], weights_cfg: dict, k: int = 3):
    layer_weights = weights_cfg["layers"]
    contribs = [(name, val * layer_weights.get(name, 0)) for name, val in layers_scores.items()]
    contribs.sort(key=lambda x: abs(x[1]), reverse=True)
    return contribs[:k]


def suggested_alloc_pct(score: float, region: str) -> float:
    """Mapeia score em % de alocação sugerida. Min 1%, Max 8%, regional caps."""
    if score < 0.5:
        return 0.0
    base = 1.0 + (score - 0.5) * 14.0
    base = min(8.0, base)
    region_cap = {"br": 8.0, "us": 6.0, "eu": 4.0, "asia": 4.0}.get(region, 4.0)
    return min(base, region_cap)


def stop_target_pct(price: float, atr: float) -> tuple[float, float]:
    if price <= 0 or atr <= 0:
        return -3.0, 5.0
    stop_pct = -(1.5 * atr / price) * 100
    target_pct = (2.5 * atr / price) * 100
    return round(stop_pct, 2), round(target_pct, 2)


def score_ticker(df, region, bench_df, macro_context, weights_cfg):
    layers = compute_all_layers(df, region, bench_df, macro_context)
    score = composite_score(layers, weights_cfg, region)
    cls = classify(score, weights_cfg)
    atr = latest_atr(df)
    price = float(df["close"].iloc[-1])
    stop_pct, target_pct = stop_target_pct(price, atr)
    alloc = suggested_alloc_pct(score, region)
    contribs = top_contributors(layers, weights_cfg)
    return {
        "score": round(score, 3),
        "classification": cls,
        "layers": {k: round(v, 3) for k, v in layers.items()},
        "price": round(price, 4),
        "atr": round(atr, 4),
        "stop_pct": stop_pct,
        "target_pct": target_pct,
        "suggested_alloc_pct": round(alloc, 2),
        "top_contributors": [(n, round(v, 3)) for n, v in contribs],
    }
