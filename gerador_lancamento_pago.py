#!/usr/bin/env python3
"""
Gerador automático — Dashboard de Lançamento Pago
Meta Ads + Hotmart + Pesquisa
"""

import pandas as pd
import json
import re
import hashlib
import requests
from datetime import date
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG DO LANÇAMENTO — edite apenas esta seção
# ══════════════════════════════════════════════════════════════════════════════

SHEET_ID        = "1wxlEwwiIzPNfObxyjuhaB6uiR7PWj9VdDcQgKx_H8xk"
TEMPLATE_FILE   = "dashboard_lancamento_pago.html"
OUTPUT_FILE     = "index.html"

NOME_CLIENTE    = "Carol"           # nome que aparece no dashboard
LOGO_LETRA      = "C"               # letra do ícone
COR_ACENTO      = "#e11d48"         # cor principal

# Código do lançamento — filtra campanhas que CONTENHAM esse texto
# Ex: "VSE02" filtra SOBE-VSE02-*, deixe "" para ver tudo
LANCAMENTO_COD  = "VSE02"

# Produtos Hotmart a considerar (lista de strings parciais)
# Ex: ["Semana Pensar Estilo"] — deixe [] para todos
PRODUTOS_HOTMART = ["Semana Pensar Estilo", "STYLETELLING", "YYY"]

# Metas de CPA (custo por venda)
CPA_BOM    = 50    # ≤ verde
CPA_MEDIO  = 80    # ≤ amarelo | acima → vermelho

# ROAS mínimo esperado
ROAS_BOM   = 1.0   # ≥ verde
ROAS_MEDIO = 0.6   # ≥ amarelo | abaixo → vermelho

# ══════════════════════════════════════════════════════════════════════════════
# NÃO PRECISA MEXER ABAIXO DESTA LINHA
# ══════════════════════════════════════════════════════════════════════════════

def sheet_url(tab):
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={tab}"

URL_META     = sheet_url("meta-ads")
URL_HOTMART  = sheet_url("hotmart+tratado")
URL_PESQUISA = sheet_url("Pesquisa")
URL_REGIAO   = sheet_url("breakdown-regiao")

def to_num(series):
    return pd.to_numeric(
        series.astype(str).str.replace("R$","",regex=False).str.replace(".","",regex=False).str.replace(",",".",regex=False).str.strip(),
        errors="coerce"
    ).fillna(0)

def safe(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return None
    f = float(v)
    return round(f, 2) if f != 0 else None

def download_thumb(url, img_dir):
    if not url or str(url) == "nan": return ""
    try:
        ext = ".png" if ".png" in url.lower() else ".jpg"
        fname = hashlib.md5(url.encode()).hexdigest()[:16] + ext
        fpath = img_dir / fname
        if not fpath.exists():
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                fpath.write_bytes(r.content)
            else: return ""
        return "imgs/" + fname
    except: return ""

# ══════════════════════════════════════════════════════════════════════════════
# META ADS
# ══════════════════════════════════════════════════════════════════════════════

def load_meta():
    print("  Lendo meta-ads...")
    df = pd.read_csv(URL_META)
    df = df.rename(columns={
        "Date": "date", "Campaign Name": "campaign",
        "Adset Name": "adset", "Ad Name": "ad",
        "Thumbnail URL": "thumb",
        "Spend (Cost, Amount Spent)": "spend",
        "Impressions": "impressions",
        "Action Link Clicks": "link_clicks",
        "Action Landing Page View": "page_view",
        "Action Omni Initiated Checkout": "init_checkout",
        "Action Omni Purchase": "purchase",
        "Action Value Omni Purchase": "revenue",
    })
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ["spend","impressions","link_clicks","page_view","init_checkout","purchase","revenue"]:
        if c in df.columns:
            df[c] = to_num(df[c])
    df["ym"] = df["date"].dt.to_period("M")
    df = df.dropna(subset=["date"])

    # Filtrar por lançamento se definido
    if LANCAMENTO_COD:
        df_lct = df[df["campaign"].str.contains(LANCAMENTO_COD, na=False, case=False)]
        print(f"     Filtro '{LANCAMENTO_COD}': {len(df_lct)} linhas de {len(df)}")
        df["is_lancamento"] = df["campaign"].str.contains(LANCAMENTO_COD, na=False, case=False)
    else:
        df["is_lancamento"] = True

    print(f"     {len(df)} linhas | {df['date'].min().date()} → {df['date'].max().date()}")
    return df

def meta_funil_total(df):
    """KPIs do funil para o período completo"""
    p = df[df["is_lancamento"]] if "is_lancamento" in df.columns else df
    spend = p["spend"].sum()
    imp   = p["impressions"].sum()
    lc    = p["link_clicks"].sum()
    pv    = p["page_view"].sum()
    ic    = p["init_checkout"].sum()
    pur   = p["purchase"].sum()
    rev   = p["revenue"].sum()

    return {
        "spend":        round(float(spend), 2),
        "impressions":  int(imp),
        "link_clicks":  int(lc),
        "page_view":    int(pv),
        "init_checkout":int(ic),
        "purchase":     int(pur),
        "revenue":      round(float(rev), 2),
        "ctr":          round(lc/imp*100, 2)   if imp  > 0 else None,
        "connect_rate": round(pv/lc*100, 2)    if lc   > 0 else None,
        "tx_ic":        round(ic/pv*100, 2)    if pv   > 0 else None,
        "tx_checkout":  round(pur/ic*100, 2)   if ic   > 0 else None,
        "tx_conv":      round(pur/pv*100, 2)   if pv   > 0 else None,
        "cpa":          round(spend/pur, 2)    if pur  > 0 else None,
        "roas":         round(rev/spend, 2)    if spend > 0 else None,
        "cpm":          round(spend/imp*1000,2) if imp  > 0 else None,
    }

def meta_daily(df):
    """Dados diários do funil"""
    p = df[df["is_lancamento"]] if "is_lancamento" in df.columns else df
    agg = p.groupby("date").agg(
        spend=("spend","sum"), impressions=("impressions","sum"),
        link_clicks=("link_clicks","sum"), page_view=("page_view","sum"),
        init_checkout=("init_checkout","sum"), purchase=("purchase","sum"),
        revenue=("revenue","sum")
    ).reset_index().sort_values("date")

    out = {k:[] for k in ["days","spend","impressions","link_clicks","page_view",
                           "init_checkout","purchase","revenue",
                           "ctr","connect_rate","tx_ic","tx_checkout","tx_conv","cpa","roas","cpm"]}
    for _, r in agg.iterrows():
        sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
        pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"]); rev=float(r["revenue"])
        out["days"].append(r["date"].strftime("%d/%m"))
        out["spend"].append(round(sp,2))
        out["impressions"].append(int(imp))
        out["link_clicks"].append(int(lc))
        out["page_view"].append(int(pv))
        out["init_checkout"].append(int(ic))
        out["purchase"].append(int(pur))
        out["revenue"].append(round(rev,2))
        out["ctr"].append(round(lc/imp*100,2) if imp>0 else None)
        out["connect_rate"].append(round(pv/lc*100,2) if lc>0 else None)
        out["tx_ic"].append(round(ic/pv*100,2) if pv>0 else None)
        out["tx_checkout"].append(round(pur/ic*100,2) if ic>0 else None)
        out["tx_conv"].append(round(pur/pv*100,2) if pv>0 else None)
        out["cpa"].append(round(sp/pur,2) if pur>0 else None)
        out["roas"].append(round(rev/sp,2) if sp>0 else None)
        out["cpm"].append(round(sp/imp*1000,2) if imp>0 else None)
    return out

def meta_camps(df, img_dir):
    """Tabelas por campanha, conjunto e criativo"""
    p = df[df["is_lancamento"]] if "is_lancamento" in df.columns else df

    def build_table(group_col, df_in):
        agg = df_in.groupby(group_col).agg(
            spend=("spend","sum"), impressions=("impressions","sum"),
            link_clicks=("link_clicks","sum"), page_view=("page_view","sum"),
            init_checkout=("init_checkout","sum"), purchase=("purchase","sum"),
            revenue=("revenue","sum")
        ).reset_index()
        result = []
        for _, r in agg.sort_values("purchase", ascending=False).iterrows():
            sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
            pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"]); rev=float(r["revenue"])
            result.append({
                "n":    str(r[group_col]),
                "spend":round(sp,2),
                "imp":  int(imp),
                "lc":   int(lc),
                "pv":   int(pv),
                "ic":   int(ic),
                "pur":  int(pur),
                "rev":  round(rev,2),
                "ctr":  round(lc/imp*100,2) if imp>0 else None,
                "cr":   round(pv/lc*100,2)  if lc>0 else None,
                "tx_ic":round(ic/pv*100,2)  if pv>0 else None,
                "tx_ck":round(pur/ic*100,2) if ic>0 else None,
                "tx_cv":round(pur/pv*100,2) if pv>0 else None,
                "cpa":  round(sp/pur,2)     if pur>0 else None,
                "roas": round(rev/sp,2)     if sp>0 else None,
                "cpm":  round(sp/imp*1000,2)if imp>0 else None,
            })
        return result

    camps = build_table("campaign", p)
    adsets = build_table("adset", p)

    # Criativos com thumb
    agg_ad = p.groupby(["ad","thumb"]).agg(
        spend=("spend","sum"), impressions=("impressions","sum"),
        link_clicks=("link_clicks","sum"), page_view=("page_view","sum"),
        init_checkout=("init_checkout","sum"), purchase=("purchase","sum"),
        revenue=("revenue","sum")
    ).reset_index().sort_values("purchase", ascending=False)

    ads = []
    for _, r in agg_ad.iterrows():
        sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
        pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"]); rev=float(r["revenue"])
        local_thumb = download_thumb(str(r["thumb"]), img_dir)
        ads.append({
            "n":    str(r["ad"]),
            "thumb":local_thumb,
            "spend":round(sp,2), "imp":int(imp), "lc":int(lc), "pv":int(pv),
            "ic":int(ic), "pur":int(pur), "rev":round(rev,2),
            "ctr":  round(lc/imp*100,2) if imp>0 else None,
            "cr":   round(pv/lc*100,2)  if lc>0 else None,
            "tx_cv":round(pur/pv*100,2) if pv>0 else None,
            "cpa":  round(sp/pur,2)     if pur>0 else None,
            "roas": round(rev/sp,2)     if sp>0 else None,
        })

    return camps, adsets, ads

# ══════════════════════════════════════════════════════════════════════════════
# HOTMART
# ══════════════════════════════════════════════════════════════════════════════

def load_hotmart():
    print("  Lendo hotmart tratado...")
    df = pd.read_csv(URL_HOTMART)
    df["date"] = pd.to_datetime(df["Data"], errors="coerce")
    df["valor"] = to_num(df["Valor bruto"])

    # Filtrar apenas status válidos
    df = df[df["Status"].isin(["COMPLETE","APPROVED","complete","approved"])]

    # Filtrar produtos se definido
    if PRODUTOS_HOTMART:
        mask = df["Produto"].str.contains("|".join(PRODUTOS_HOTMART), na=False, case=False)
        df = df[mask]

    print(f"     {len(df)} vendas | R$ {df['valor'].sum():,.2f}")
    return df

def hotmart_kpis(df):
    total = df["valor"].sum()
    qtd = len(df)
    pago = df[df["Organico ou Pago"]=="Tráfego Pago"]["valor"].sum()
    org  = df[df["Organico ou Pago"]=="Orgânico"]["valor"].sum()

    return {
        "total":   round(float(total),2),
        "qtd":     int(qtd),
        "pago":    round(float(pago),2),
        "organico":round(float(org),2),
        "ticket_medio": round(float(total/qtd),2) if qtd>0 else None,
    }

def hotmart_by_origin(df):
    """Vendas por SCK / origem"""
    result = []
    for _, g in df.groupby("Organico ou Pago"):
        pass

    # Por utm_source
    by_src = df.groupby("utm_source").agg(
        qtd=("valor","count"), valor=("valor","sum")
    ).reset_index().sort_values("valor", ascending=False)
    src_list = [{"n":str(r["utm_source"]),"qtd":int(r["qtd"]),"valor":round(float(r["valor"]),2)} for _,r in by_src.iterrows()]

    # Por utm_campaign
    by_camp = df.groupby("utm_campaign").agg(
        qtd=("valor","count"), valor=("valor","sum")
    ).reset_index().sort_values("valor", ascending=False)
    camp_list = [{"n":str(r["utm_campaign"]),"qtd":int(r["qtd"]),"valor":round(float(r["valor"]),2)} for _,r in by_camp.iterrows()]

    # Por Organico/Pago
    by_tipo = df.groupby("Organico ou Pago").agg(
        qtd=("valor","count"), valor=("valor","sum")
    ).reset_index()
    tipo_list = [{"n":str(r["Organico ou Pago"]),"qtd":int(r["qtd"]),"valor":round(float(r["valor"]),2)} for _,r in by_tipo.iterrows()]

    return {"por_source": src_list, "por_campaign": camp_list, "por_tipo": tipo_list}

def hotmart_daily(df):
    agg = df.groupby("date").agg(qtd=("valor","count"), valor=("valor","sum")).reset_index().sort_values("date")
    return {
        "days":  [r["date"].strftime("%d/%m") for _,r in agg.iterrows()],
        "qtd":   [int(r["qtd"]) for _,r in agg.iterrows()],
        "valor": [round(float(r["valor"]),2) for _,r in agg.iterrows()],
    }

# ══════════════════════════════════════════════════════════════════════════════
# PESQUISA
# ══════════════════════════════════════════════════════════════════════════════

def load_pesquisa():
    print("  Lendo pesquisa...")
    df = pd.read_csv(URL_PESQUISA)
    return df

def pesquisa_data(df):
    PERGUNTAS_FECHADAS = [
        "Você já trabalha como consultora de estilo?",
        "Hoje, a Consultoria de Estilo é sua principal fonte de renda?",
        "Qual é a sua faixa de renda mensal atualmente?",
        "Qual a sua opinião sobre os métodos tradicionais?",
        "Há quanto tempo você me conhece?",
        "Você já ouviu falar do método Styletelling e da semiótica visual?",
        "Qual é a sua maior dificuldade hoje na consultoria de estilo?",
        "Qual é a sua idade?",
    ]

    graficos = []
    for p in PERGUNTAS_FECHADAS:
        if p not in df.columns: continue
        vc = df[p].value_counts()
        total = vc.sum()
        graficos.append({
            "pergunta": p,
            "opcoes": [{"label": str(k), "qtd": int(v), "pct": round(v/total*100,1)} for k,v in vc.items()]
        })

    # Origens únicas
    sources = sorted(df["utm_source"].dropna().unique().tolist())

    # Por origem - distribuição por perguntas chave
    por_origem = {}
    for src in sources:
        sub = df[df["utm_source"]==src]
        por_origem[src] = {}
        for p in PERGUNTAS_FECHADAS[:3]:  # 3 perguntas mais relevantes
            if p not in sub.columns: continue
            vc2 = sub[p].value_counts()
            total2 = vc2.sum()
            por_origem[src][p] = [{"label":str(k),"pct":round(v/total2*100,1)} for k,v in vc2.items()]

    return {
        "total":      len(df),
        "graficos":   graficos,
        "sources":    sources,
        "por_origem": por_origem,
    }

# ══════════════════════════════════════════════════════════════════════════════
# INJETAR NO HTML
# ══════════════════════════════════════════════════════════════════════════════

def replace_js_const(html, const_name, value):
    pattern = rf"const {const_name}\s*=\s*(?:\{{[\s\S]*?\}}|\[[\s\S]*?\]|\"[^\"]*?\"|'[^']*?'|null|true|false|\d[\d\.]*)\s*;"
    replacement = f"const {const_name} = {json.dumps(value, ensure_ascii=False)};"
    new_html, count = re.subn(pattern, replacement, html, count=1)
    if count == 0:
        print(f"  AVISO: não encontrou const {const_name}")
    return new_html

def inject_all(template_path, meta_kpis, meta_daily_d, meta_camps_d, meta_adsets_d, meta_ads_d,
               meta_kpis_all, meta_daily_all, meta_camps_all, meta_adsets_all, meta_ads_all,
               hot_kpis, hot_daily_d, hot_origin_d, pesquisa_d):

    html = Path(template_path).read_text(encoding="utf-8")

    html = replace_js_const(html, "META_KPIS",    meta_kpis)
    html = replace_js_const(html, "META_DAILY",   meta_daily_d)
    html = replace_js_const(html, "META_CAMPS",   meta_camps_d)
    html = replace_js_const(html, "META_ADSETS",  meta_adsets_d)
    html = replace_js_const(html, "META_ADS",     meta_ads_d)
    html = replace_js_const(html, "META_KPIS_ALL",   meta_kpis_all)
    html = replace_js_const(html, "META_DAILY_ALL",  meta_daily_all)
    html = replace_js_const(html, "META_CAMPS_ALL",  meta_camps_all)
    html = replace_js_const(html, "META_ADSETS_ALL", meta_adsets_all)
    html = replace_js_const(html, "META_ADS_ALL",    meta_ads_all)
    html = replace_js_const(html, "HOT_KPIS",     hot_kpis)
    html = replace_js_const(html, "HOT_DAILY",    hot_daily_d)
    html = replace_js_const(html, "HOT_ORIGIN",   hot_origin_d)
    html = replace_js_const(html, "PESQUISA",     pesquisa_d)

    # Config do lançamento
    html = re.sub(r"const LANCAMENTO_COD\s*=\s*'[^']*'", f"const LANCAMENTO_COD='{LANCAMENTO_COD}'", html, count=1)
    html = re.sub(r"const NOME_CLIENTE\s*=\s*'[^']*'",   f"const NOME_CLIENTE='{NOME_CLIENTE}'",     html, count=1)
    html = re.sub(r"const LOGO_LETRA\s*=\s*'[^']*'",     f"const LOGO_LETRA='{LOGO_LETRA}'",         html, count=1)
    html = re.sub(r"const COR_ACENTO\s*=\s*'[^']*'",     f"const COR_ACENTO='{COR_ACENTO}'",         html, count=1)
    html = re.sub(r"const CPA_BOM\s*=\s*\d+",            f"const CPA_BOM={CPA_BOM}",                 html, count=1)
    html = re.sub(r"const CPA_MEDIO\s*=\s*\d+",          f"const CPA_MEDIO={CPA_MEDIO}",             html, count=1)
    html = re.sub(r"const ROAS_BOM\s*=\s*[\d\.]+",       f"const ROAS_BOM={ROAS_BOM}",               html, count=1)
    html = re.sub(r"const ROAS_MEDIO\s*=\s*[\d\.]+",     f"const ROAS_MEDIO={ROAS_MEDIO}",           html, count=1)

    today = date.today().strftime("%d/%m/%Y")
    html = re.sub(r"\d{2}/\d{2}/\d{4} · via planilha", f"{today} · via planilha", html)

    return html

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print(f"Dashboard Lançamento — {NOME_CLIENTE} / {LANCAMENTO_COD}")
    print("=" * 60)

    img_dir = Path("imgs")
    img_dir.mkdir(exist_ok=True)

    # META
    print("\n[META ADS]")
    df_meta = load_meta()

    # Dados filtrados pelo lançamento
    m_kpis   = meta_funil_total(df_meta)
    m_daily  = meta_daily(df_meta)
    m_camps, m_adsets, m_ads = meta_camps(df_meta, img_dir)
    print(f"  ✓ {len(m_camps)} campanhas | {len(m_adsets)} conjuntos | {len(m_ads)} criativos")

    # Dados totais (todas as campanhas)
    df_meta_all = df_meta.copy()
    df_meta_all["is_lancamento"] = True  # forçar sem filtro
    m_kpis_all   = meta_funil_total(df_meta_all)
    m_daily_all  = meta_daily(df_meta_all)
    m_camps_all, m_adsets_all, m_ads_all = meta_camps(df_meta_all, img_dir)
    print(f"  ✓ Total (sem filtro): {len(m_camps_all)} campanhas")

    # HOTMART
    print("\n[HOTMART]")
    df_hot   = load_hotmart()
    h_kpis   = hotmart_kpis(df_hot)
    h_daily  = hotmart_daily(df_hot)
    h_origin = hotmart_by_origin(df_hot)
    print(f"  ✓ {h_kpis['qtd']} vendas | R$ {h_kpis['total']:,.2f}")

    # PESQUISA
    print("\n[PESQUISA]")
    df_pes   = load_pesquisa()
    pes_data = pesquisa_data(df_pes)
    print(f"  ✓ {pes_data['total']} respostas | {len(pes_data['graficos'])} gráficos")

    # HTML
    print("\n[HTML]")
    if not Path(TEMPLATE_FILE).exists():
        print(f"  ERRO: {TEMPLATE_FILE} não encontrado")
        return

    html = inject_all(
        TEMPLATE_FILE,
        m_kpis, m_daily, m_camps, m_adsets, m_ads,
        m_kpis_all, m_daily_all, m_camps_all, m_adsets_all, m_ads_all,
        h_kpis, h_daily, h_origin, pes_data,
    )

    Path(OUTPUT_FILE).write_text(html, encoding="utf-8")
    print(f"  ✓ {OUTPUT_FILE} gerado ({len(html)//1024}KB)")

    # data.json para painel de agência
    data_json = {
        "cliente":    NOME_CLIENTE,
        "cor":        COR_ACENTO,
        "letra":      LOGO_LETRA,
        "lancamento": LANCAMENTO_COD,
        "atualizado": date.today().strftime("%d/%m/%Y"),
        "kpis": {
            "spend":   m_kpis.get("spend"),
            "revenue": h_kpis.get("total"),
            "roas":    m_kpis.get("roas"),
            "vendas":  h_kpis.get("qtd"),
            "cpa":     m_kpis.get("cpa"),
        }
    }
    Path("data.json").write_text(json.dumps(data_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ data.json gerado")
    print("=" * 60)

if __name__ == "__main__":
    main()
