#!/usr/bin/env python3
"""
FIN-TRADER Monitor — Painel de Monitoramento Pessoal
Roda todo dia às 08h BRT via GitHub Actions
Busca dados reais e gera monitor.html com análise personalizada
"""

import requests
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============ CARTEIRA REAL (atualizar quando mudar) ============
CARTEIRA = {
    "inter_brl":  {"saldo": 109991.56, "taxa": 14.00, "ir": 15.0},
    "inter_usd":  {"saldo": 101.31,    "taxa": 3.39},
    "wise_usd":   {"saldo": 103.23,    "taxa": 3.44},
    "wise_eur":   {"saldo": 3019.34,   "taxa": 2.02},
    "meta_renda_mensal": 1745.0,
    "meta_patrimonio":   198000.0,
    "data_emigracao":    "2027-02-01",
}

BRT = timezone(timedelta(hours=-3))

def get_brl_usd():
    """USD/BRL via BCB PTAX"""
    try:
        hoje = datetime.now(BRT).strftime("%m-%d-%Y")
        url = f"https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarDia(dataCotacao=@dataCotacao)?@dataCotacao='{hoje}'&$format=json"
        r = requests.get(url, timeout=10)
        data = r.json()
        valores = data.get("value", [])
        if valores:
            return float(valores[-1]["cotacaoVenda"])
    except:
        pass
    # Fallback: último dado via API de séries temporais BCB
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados/ultimos/1?formato=json"
        r = requests.get(url, timeout=10)
        return float(r.json()[0]["valor"])
    except:
        return 5.2233  # último valor conhecido

def get_brl_eur():
    """EUR/BRL via BCB (série 21619 = EUR)"""
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.21619/dados/ultimos/1?formato=json"
        r = requests.get(url, timeout=10)
        return float(r.json()[0]["valor"])
    except:
        return 5.9873

def get_selic():
    """Selic atual via BCB"""
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        r = requests.get(url, timeout=10)
        return float(r.json()[0]["valor"])
    except:
        return 14.00

def get_ipca():
    """IPCA acumulado 12m via BCB"""
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json"
        r = requests.get(url, timeout=10)
        return float(r.json()[0]["valor"])
    except:
        return 4.64

def get_ibovespa():
    """Ibovespa via Yahoo Finance"""
    try:
        import yfinance as yf
        ibov = yf.Ticker("^BVSP")
        hist = ibov.history(period="5d")
        if not hist.empty:
            return {
                "atual": float(hist["Close"].iloc[-1]),
                "anterior": float(hist["Close"].iloc[-2]) if len(hist) > 1 else None,
                "variacao_pct": float((hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100) if len(hist) > 1 else 0
            }
    except:
        pass
    return {"atual": 166934, "anterior": None, "variacao_pct": 0}

def get_etf_price(ticker):
    """Preço de ETF via Brapi"""
    try:
        url = f"https://brapi.dev/api/quote/{ticker}?range=5d&interval=1d"
        r = requests.get(url, timeout=10)
        result = r.json().get("results", [{}])[0]
        return {
            "preco": result.get("regularMarketPrice", 0),
            "variacao_pct": result.get("regularMarketChangePercent", 0),
            "nome": result.get("longName", ticker)
        }
    except:
        return {"preco": 0, "variacao_pct": 0, "nome": ticker}

def get_analise_claude(dados):
    """Gera análise personalizada via Claude API"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "API key não configurada — análise indisponível."

    carteira = CARTEIRA
    hoje = datetime.now(BRT)
    emigracao = datetime(2027, 2, 1, tzinfo=BRT)
    dias_restantes = (emigracao - hoje).days

    prompt = f"""Você é o analisador pessoal de carteira de Mauricio Behrens, que emigra para a Espanha em {dias_restantes} dias (fevereiro/2027).

DADOS DE HOJE ({hoje.strftime('%d/%m/%Y')}):
- USD/BRL: {dados['usd_brl']:.4f} (PTAX BCB)
- EUR/BRL: {dados['eur_brl']:.4f} (BCB)
- Selic: {dados['selic']:.2f}% a.a.
- IPCA 12m: {dados['ipca']:.2f}%
- Ibovespa: {dados['ibov']['atual']:,.0f} pts ({dados['ibov']['variacao_pct']:+.2f}%)
- VWRA11: R${dados['vwra11']['preco']:.2f} ({dados['vwra11']['variacao_pct']:+.2f}%)
- B5P211: R${dados['b5p211']['preco']:.2f} ({dados['b5p211']['variacao_pct']:+.2f}%)

CARTEIRA DE MAURICIO:
- Inter BRL: R${carteira['inter_brl']['saldo']:,.2f} @ {carteira['inter_brl']['taxa']}% CDI
- Wise EUR: €{carteira['wise_eur']['saldo']:,.2f} @ {carteira['wise_eur']['taxa']}% a.a.
- Wise USD: ${carteira['wise_usd']['saldo']:,.2f} @ {carteira['wise_usd']['taxa']}% a.a.
- ETFs: VWRA11 + B5P211 (posições registradas na carteira)
- Meta renda passiva: R${carteira['meta_renda_mensal']:,.0f}/mês em fev/2027
- Meta patrimônio: R${carteira['meta_patrimonio']:,.0f}

Total BRL estimado: R${carteira['inter_brl']['saldo'] + (carteira['wise_usd']['saldo'] + carteira['inter_usd']['saldo']) * dados['usd_brl'] + carteira['wise_eur']['saldo'] * dados['eur_brl']:,.2f}

Gere uma análise diária CONCISA e PERSONALIZADA com:
1. O que mudou hoje que impacta diretamente Mauricio (câmbio EUR, Selic, mercado)
2. Impacto quantificado no patrimônio dele (ex: "EUR subiu 1% → seus €3.017 valem mais R$X")
3. O que fazer ou não fazer hoje (1-2 ações concretas máximo)
4. Semáforo de risco: 🟢 tudo ok / 🟡 atenção / 🔴 agir

Seja direto, numérico e personalizado. Máximo 300 palavras. Responda em português."""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 400,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        return r.json()["content"][0]["text"]
    except Exception as e:
        return f"Erro na análise: {e}"

def calcular_patrimonio(usd_brl, eur_brl):
    c = CARTEIRA
    inter_brl = c["inter_brl"]["saldo"]
    usd_total = (c["inter_usd"]["saldo"] + c["wise_usd"]["saldo"]) * usd_brl
    eur_total = c["wise_eur"]["saldo"] * eur_brl
    total = inter_brl + usd_total + eur_total
    
    renda_inter = inter_brl * c["inter_brl"]["taxa"] / 100 / 12 * (1 - c["inter_brl"]["ir"]/100)
    renda_usd = c["wise_usd"]["saldo"] * c["wise_usd"]["taxa"] / 100 / 12 * usd_brl
    renda_eur = c["wise_eur"]["saldo"] * c["wise_eur"]["taxa"] / 100 / 12 * eur_brl
    renda_total = renda_inter + renda_usd + renda_eur
    
    return {"total": total, "renda": renda_total, "inter_brl": inter_brl, "usd_brl_val": usd_total, "eur_brl_val": eur_total}

def gerar_html(dados, analise, patrimonio):
    hoje = datetime.now(BRT)
    emigracao = datetime(2027, 2, 1, tzinfo=BRT)
    dias = (emigracao - hoje).days
    
    meta_p = CARTEIRA["meta_patrimonio"]
    meta_r = CARTEIRA["meta_renda_mensal"]
    pct_patrimonio = min(100, patrimonio["total"] / meta_p * 100)
    pct_renda = min(100, patrimonio["renda"] / meta_r * 100)
    
    ibov_color = "#86efac" if dados['ibov']['variacao_pct'] >= 0 else "#fca5a5"
    vwra_color = "#86efac" if dados['vwra11']['variacao_pct'] >= 0 else "#fca5a5"
    b5_color   = "#86efac" if dados['b5p211']['variacao_pct'] >= 0 else "#fca5a5"

    analise_html = analise.replace('\n', '<br>').replace('🟢', '<span style="color:#86efac">🟢</span>').replace('🟡', '<span style="color:#fbbf24">🟡</span>').replace('🔴', '<span style="color:#fca5a5">🔴</span>')

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FIN-TRADER Monitor — {hoje.strftime('%d/%m/%Y')}</title>
<style>
:root {{
  --bg: #0a0a0a; --surface: #111; --border: #1e1e1e;
  --text: #e5e5e5; --muted: #666; --accent: #22c55e;
  --font: 'SF Mono', ui-monospace, monospace;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font-family: var(--font); min-height: 100vh; }}
.header {{ padding: 1.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; }}
.header h1 {{ font-size: 1rem; color: var(--accent); letter-spacing: 0.08em; }}
.header .meta {{ font-size: 0.75rem; color: var(--muted); }}
.container {{ max-width: 1000px; margin: 0 auto; padding: 1.5rem; display: flex; flex-direction: column; gap: 1.5rem; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }}
.card-header {{ padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.65rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; }}
.card-body {{ padding: 1rem; }}
.grid-4 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; }}
.grid-3 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; }}
.metric {{ text-align: center; }}
.metric .val {{ font-size: 1.5rem; font-weight: 700; }}
.metric .lbl {{ font-size: 0.65rem; color: var(--muted); margin-top: 0.25rem; text-transform: uppercase; letter-spacing: 0.06em; }}
.metric .sub {{ font-size: 0.7rem; color: var(--muted); margin-top: 0.15rem; }}
.bar-wrap {{ background: #1a1a1a; border-radius: 4px; height: 8px; margin-top: 0.5rem; overflow: hidden; }}
.bar {{ height: 100%; border-radius: 4px; background: var(--accent); transition: width 0.3s; }}
.analise {{ font-size: 0.8rem; line-height: 1.8; color: #d4d4d4; }}
.badge {{ display: inline-block; font-size: 0.6rem; padding: 0.15rem 0.5rem; border-radius: 3px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; }}
.nav {{ display: flex; gap: 1rem; padding: 1rem 1.5rem; border-bottom: 1px solid var(--border); }}
.nav a {{ color: var(--muted); text-decoration: none; font-size: 0.75rem; }}
.nav a:hover {{ color: var(--text); }}
.nav a.active {{ color: var(--accent); }}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>● FIN-TRADER MONITOR</h1>
    <div class="meta">Atualizado: {hoje.strftime('%d/%m/%Y às %H:%M')} BRT · Auto-refresh 08h todo dia útil</div>
  </div>
  <div style="text-align:right">
    <div style="font-size:1.5rem;font-weight:700;color:var(--accent)">{dias} dias</div>
    <div style="font-size:0.7rem;color:var(--muted)">para Espanha (fev/2027)</div>
  </div>
</div>
<div class="nav">
  <a href="index.html">Briefs</a>
  <a href="carteira.html">Carteira</a>
  <a href="monitor.html" class="active">Monitor</a>
</div>
<div class="container">

  <!-- CÂMBIO -->
  <div class="card">
    <div class="card-header">Câmbio — fontes oficiais BCB/BCE</div>
    <div class="card-body grid-4">
      <div class="metric">
        <div class="val" style="color:#22c55e">€{dados['eur_brl']:.4f}</div>
        <div class="lbl">EUR/BRL</div>
        <div class="sub">BCE oficial · ⭐ mais importante</div>
      </div>
      <div class="metric">
        <div class="val" style="color:#3b82f6">${dados['usd_brl']:.4f}</div>
        <div class="lbl">USD/BRL</div>
        <div class="sub">PTAX BCB oficial</div>
      </div>
      <div class="metric">
        <div class="val" style="color:#fff">R${patrimonio['eur_brl_val']:,.0f}</div>
        <div class="lbl">Seus €{CARTEIRA['wise_eur']['saldo']:,.0f} em BRL</div>
        <div class="sub">Wise EUR convertido</div>
      </div>
      <div class="metric">
        <div class="val" style="color:#fff">R${patrimonio['usd_brl_val']:,.0f}</div>
        <div class="lbl">Seu USD em BRL</div>
        <div class="sub">Inter + Wise USD</div>
      </div>
    </div>
  </div>

  <!-- PATRIMÔNIO -->
  <div class="card">
    <div class="card-header">Patrimônio consolidado</div>
    <div class="card-body grid-3">
      <div class="metric">
        <div class="val" style="color:var(--accent)">R${patrimonio['total']:,.0f}</div>
        <div class="lbl">Total BRL hoje</div>
        <div class="bar-wrap"><div class="bar" style="width:{pct_patrimonio:.1f}%"></div></div>
        <div class="sub">{pct_patrimonio:.1f}% da meta R${meta_p:,.0f}</div>
      </div>
      <div class="metric">
        <div class="val" style="color:#86efac">R${patrimonio['renda']:,.0f}/mês</div>
        <div class="lbl">Renda passiva mensal</div>
        <div class="bar-wrap"><div class="bar" style="width:{pct_renda:.1f}%"></div></div>
        <div class="sub">{pct_renda:.1f}% da meta R${meta_r:,.0f}/mês</div>
      </div>
      <div class="metric">
        <div class="val" style="color:#fff">{dias}</div>
        <div class="lbl">Dias para emigração</div>
        <div class="sub">Fev/2027 · Espanha</div>
      </div>
    </div>
  </div>

  <!-- MERCADO -->
  <div class="card">
    <div class="card-header">Mercado — dados de hoje</div>
    <div class="card-body grid-4">
      <div class="metric">
        <div class="val" style="color:#fff">{dados['selic']:.2f}%</div>
        <div class="lbl">Selic a.a.</div>
        <div class="sub">BCB Copom</div>
      </div>
      <div class="metric">
        <div class="val" style="color:{ibov_color}">{dados['ibov']['atual']:,.0f}</div>
        <div class="lbl">Ibovespa</div>
        <div class="sub" style="color:{ibov_color}">{dados['ibov']['variacao_pct']:+.2f}% hoje</div>
      </div>
      <div class="metric">
        <div class="val" style="color:{vwra_color}">R${dados['vwra11']['preco']:.2f}</div>
        <div class="lbl">VWRA11</div>
        <div class="sub" style="color:{vwra_color}">{dados['vwra11']['variacao_pct']:+.2f}% hoje</div>
      </div>
      <div class="metric">
        <div class="val" style="color:{b5_color}">R${dados['b5p211']['preco']:.2f}</div>
        <div class="lbl">B5P211</div>
        <div class="sub" style="color:{b5_color}">{dados['b5p211']['variacao_pct']:+.2f}% hoje</div>
      </div>
    </div>
  </div>

  <!-- ANÁLISE CLAUDE -->
  <div class="card">
    <div class="card-header">Análise personalizada — gerada por IA com dados reais de hoje</div>
    <div class="card-body">
      <div class="analise">{analise_html}</div>
    </div>
  </div>

  <!-- RENDA FIXA -->
  <div class="card">
    <div class="card-header">Renda fixa — crescimento automático hoje</div>
    <div class="card-body grid-3">
      <div class="metric">
        <div class="val" style="color:#22c55e">R${CARTEIRA['inter_brl']['saldo'] * CARTEIRA['inter_brl']['taxa'] / 100 / 365 * 0.85:,.2f}</div>
        <div class="lbl">Inter BRL rendeu hoje</div>
        <div class="sub">Líquido 15% IR · {CARTEIRA['inter_brl']['taxa']}% CDI</div>
      </div>
      <div class="metric">
        <div class="val" style="color:#3b82f6">${CARTEIRA['wise_usd']['saldo'] * CARTEIRA['wise_usd']['taxa'] / 100 / 365:.4f}</div>
        <div class="lbl">Wise USD rendeu hoje</div>
        <div class="sub">{CARTEIRA['wise_usd']['taxa']}% a.a. Rende+</div>
      </div>
      <div class="metric">
        <div class="val" style="color:#a855f7">€{CARTEIRA['wise_eur']['saldo'] * CARTEIRA['wise_eur']['taxa'] / 100 / 365:.4f}</div>
        <div class="lbl">Wise EUR rendeu hoje</div>
        <div class="sub">{CARTEIRA['wise_eur']['taxa']}% a.a. Rende+</div>
      </div>
    </div>
  </div>

  <div style="text-align:center;font-size:0.65rem;color:var(--muted);padding:1rem">
    Dados: BCB · BCE · B3 · Brapi · Yahoo Finance · Anthropic Claude<br>
    Gerado automaticamente às {hoje.strftime('%H:%M')} BRT em {hoje.strftime('%d/%m/%Y')}
  </div>

</div>
</body>
</html>"""

def main():
    print("🚀 FIN-TRADER Monitor iniciando...")
    
    print("📡 Buscando dados...")
    usd_brl  = get_brl_usd()
    eur_brl  = get_brl_eur()
    selic    = get_selic()
    ipca     = get_ipca()
    ibov     = get_ibovespa()
    vwra11   = get_etf_price("VWRA11")
    b5p211   = get_etf_price("B5P211")
    
    dados = {
        "usd_brl": usd_brl, "eur_brl": eur_brl,
        "selic": selic, "ipca": ipca,
        "ibov": ibov, "vwra11": vwra11, "b5p211": b5p211
    }
    
    print(f"✓ EUR/BRL: {eur_brl:.4f} | USD/BRL: {usd_brl:.4f} | Selic: {selic:.2f}%")
    print(f"✓ Ibovespa: {ibov['atual']:,.0f} ({ibov['variacao_pct']:+.2f}%)")
    print(f"✓ VWRA11: R${vwra11['preco']:.2f} | B5P211: R${b5p211['preco']:.2f}")
    
    patrimonio = calcular_patrimonio(usd_brl, eur_brl)
    print(f"✓ Patrimônio: R${patrimonio['total']:,.2f} | Renda: R${patrimonio['renda']:,.2f}/mês")
    
    print("🤖 Gerando análise Claude...")
    analise = get_analise_claude(dados)
    print(f"✓ Análise: {len(analise)} chars")
    
    print("📝 Gerando monitor.html...")
    html = gerar_html(dados, analise, patrimonio)
    
    output = Path("monitor.html")
    output.write_text(html, encoding="utf-8")
    print(f"✓ monitor.html gerado: {len(html)} bytes")

if __name__ == "__main__":
    main()
