#!/usr/bin/env python3
"""
Gerador automático — Dashboard de Lançamento Pago v2
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

SHEET_ID         = "1wxlEwwiIzPNfObxyjuhaB6uiR7PWj9VdDcQgKx_H8xk"
TEMPLATE_FILE    = "dashboard_lancamento_pago.html"
OUTPUT_FILE      = "index.html"

NOME_CLIENTE     = "Carol"
LOGO_LETRA       = "C"
COR_ACENTO       = "#e11d48"

LANCAMENTO_COD   = "VSE02"        # filtra campanhas; "" = ver tudo

PRODUTOS_HOTMART = ["Semana Pensar Estilo"]              # ex: ["Semana Pensar Estilo"]; [] = todos

CPA_BOM          = 50
CPA_MEDIO        = 80
ROAS_BOM         = 1.0
ROAS_MEDIO       = 0.6

# ══════════════════════════════════════════════════════════════════════════════
# NÃO PRECISA MEXER ABAIXO
# ══════════════════════════════════════════════════════════════════════════════

def sheet_url(tab):
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={tab}"

URL_META     = sheet_url("meta-ads")
URL_HOTMART  = sheet_url("hotmart+tratado")
URL_PESQUISA = sheet_url("Pesquisa")
URL_GA       = sheet_url("breakdown-gender-age")
URL_REGIAO   = sheet_url("breakdown-regiao")

def to_num(series):
    return pd.to_numeric(
        series.astype(str).str.replace("R$","",regex=False)
              .str.replace(".","",regex=False)
              .str.replace(",",".",regex=False).str.strip(),
        errors="coerce"
    ).fillna(0)

def safe(v):
    if v is None or (isinstance(v,float) and pd.isna(v)): return None
    f = float(v)
    return round(f,2) if f!=0 else None

def download_thumb(url, img_dir):
    if not url or str(url)=="nan": return ""
    try:
        ext = ".png" if ".png" in url.lower() else ".jpg"
        fname = hashlib.md5(url.encode()).hexdigest()[:16]+ext
        fpath = img_dir/fname
        if not fpath.exists():
            r = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code==200: fpath.write_bytes(r.content)
            else: return ""
        return "imgs/"+fname
    except: return ""

# ══ META ADS ══════════════════════════════════════════════════════════════════

def load_meta():
    print("  Lendo meta-ads...")
    df = pd.read_csv(URL_META)
    df = df.rename(columns={
        "Date":"date","Campaign Name":"campaign","Adset Name":"adset","Ad Name":"ad",
        "Thumbnail URL":"thumb",
        "Spend (Cost, Amount Spent)":"spend",
        "Impressions":"impressions",
        "Action Link Clicks":"link_clicks",
        "Action Landing Page View":"page_view",
        "Action Omni Initiated Checkout":"init_checkout",
        "Action Omni Purchase":"purchase",
        "Action Value Omni Purchase":"revenue",
    })
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ["spend","impressions","link_clicks","page_view","init_checkout","purchase","revenue"]:
        if c in df.columns: df[c] = to_num(df[c])
    df["ym"]  = df["date"].dt.to_period("M")
    df = df.dropna(subset=["date"])
    df["is_lct"] = df["campaign"].str.contains(LANCAMENTO_COD, na=False, case=False) if LANCAMENTO_COD else True
    print(f"     {len(df)} linhas | {df['date'].min().date()} → {df['date'].max().date()}")
    return df

def calc_funnel(p):
    sp = float(p["spend"].sum()); imp = float(p["impressions"].sum())
    lc = float(p["link_clicks"].sum()); pv = float(p["page_view"].sum())
    ic = float(p["init_checkout"].sum()); pur = float(p["purchase"].sum())
    rev = float(p["revenue"].sum())
    return {
        "spend":round(sp,2),"impressions":int(imp),"link_clicks":int(lc),
        "page_view":int(pv),"init_checkout":int(ic),"purchase":int(pur),"revenue":round(rev,2),
        "ctr":   round(lc/imp*100,2) if imp>0 else None,
        "connect_rate": round(pv/lc*100,2) if lc>0 else None,
        "tx_ic": round(ic/pv*100,2)  if pv>0 else None,
        "tx_checkout": round(pur/ic*100,2) if ic>0 else None,
        "tx_conv": round(pur/pv*100,2) if pv>0 else None,
        "cpa":   round(sp/pur,2)  if pur>0 else None,
        "roas_meta": round(rev/sp,2) if sp>0 else None,
        "cpm":   round(sp/imp*1000,2) if imp>0 else None,
    }

def meta_kpis(df):
    lct = df[df["is_lct"]]; all_ = df
    return {"lct": calc_funnel(lct), "all": calc_funnel(all_)}

def meta_daily(df):
    def build(p):
        agg = p.groupby("date").agg(
            spend=("spend","sum"), impressions=("impressions","sum"),
            link_clicks=("link_clicks","sum"), page_view=("page_view","sum"),
            init_checkout=("init_checkout","sum"), purchase=("purchase","sum"),
            revenue=("revenue","sum")
        ).reset_index().sort_values("date")
        out = {k:[] for k in ["days","spend","impressions","link_clicks","page_view",
                               "init_checkout","purchase","revenue",
                               "ctr","connect_rate","tx_ic","tx_checkout","tx_conv","cpa","roas_meta","cpm"]}
        for _,r in agg.iterrows():
            sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
            pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"]); rev=float(r["revenue"])
            out["days"].append(r["date"].strftime("%d/%m"))
            out["spend"].append(round(sp,2)); out["impressions"].append(int(imp))
            out["link_clicks"].append(int(lc)); out["page_view"].append(int(pv))
            out["init_checkout"].append(int(ic)); out["purchase"].append(int(pur))
            out["revenue"].append(round(rev,2))
            out["ctr"].append(round(lc/imp*100,2) if imp>0 else None)
            out["connect_rate"].append(round(pv/lc*100,2) if lc>0 else None)
            out["tx_ic"].append(round(ic/pv*100,2) if pv>0 else None)
            out["tx_checkout"].append(round(pur/ic*100,2) if ic>0 else None)
            out["tx_conv"].append(round(pur/pv*100,2) if pv>0 else None)
            out["cpa"].append(round(sp/pur,2) if pur>0 else None)
            out["roas_meta"].append(round(rev/sp,2) if sp>0 else None)
            out["cpm"].append(round(sp/imp*1000,2) if imp>0 else None)
        return out
    return {"lct": build(df[df["is_lct"]]), "all": build(df)}

def build_rows(agg, group_col):
    rows = []
    for _,r in agg.sort_values("purchase", ascending=False).iterrows():
        sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
        pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"]); rev=float(r["revenue"])
        rows.append({
            "n":str(r[group_col]),"spend":round(sp,2),"imp":int(imp),"lc":int(lc),
            "pv":int(pv),"ic":int(ic),"pur":int(pur),"rev":round(rev,2),
            "ctr":  round(lc/imp*100,2) if imp>0 else None,
            "cr":   round(pv/lc*100,2)  if lc>0 else None,
            "tx_ic":round(ic/pv*100,2)  if pv>0 else None,
            "tx_ck":round(pur/ic*100,2) if ic>0 else None,
            "tx_cv":round(pur/pv*100,2) if pv>0 else None,
            "cpa":  round(sp/pur,2)     if pur>0 else None,
            "roas": round(rev/sp,2)     if sp>0 else None,
            "cpm":  round(sp/imp*1000,2)if imp>0 else None,
        })
    return rows

def meta_tables(df, img_dir):
    def agg_by(p, col):
        return p.groupby(col).agg(
            spend=("spend","sum"), impressions=("impressions","sum"),
            link_clicks=("link_clicks","sum"), page_view=("page_view","sum"),
            init_checkout=("init_checkout","sum"), purchase=("purchase","sum"),
            revenue=("revenue","sum")
        ).reset_index()

    def make(p, col): return build_rows(agg_by(p, col), col)

    lct = df[df["is_lct"]]; all_ = df

    # Criativos
    def make_ads(p):
        agg = p.dropna(subset=["thumb"]).copy()
        agg = agg[agg["thumb"].astype(str)!="nan"]
        agg = agg.groupby(["ad","thumb"]).agg(
            spend=("spend","sum"), impressions=("impressions","sum"),
            link_clicks=("link_clicks","sum"), page_view=("page_view","sum"),
            init_checkout=("init_checkout","sum"), purchase=("purchase","sum"),
            revenue=("revenue","sum")
        ).reset_index().sort_values("purchase", ascending=False)
        ads = []
        for _,r in agg.iterrows():
            sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
            pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"]); rev=float(r["revenue"])
            ads.append({
                "n":str(r["ad"]), "thumb":download_thumb(str(r["thumb"]),img_dir),
                "spend":round(sp,2),"imp":int(imp),"lc":int(lc),"pv":int(pv),
                "ic":int(ic),"pur":int(pur),"rev":round(rev,2),
                "ctr":  round(lc/imp*100,2) if imp>0 else None,
                "cr":   round(pv/lc*100,2)  if lc>0 else None,
                "tx_cv":round(pur/pv*100,2) if pv>0 else None,
                "cpa":  round(sp/pur,2)     if pur>0 else None,
                "roas": round(rev/sp,2)     if sp>0 else None,
            })
        return ads

    return {
        "lct":{"camps":make(lct,"campaign"),"adsets":make(lct,"adset"),"ads":make_ads(lct)},
        "all":{"camps":make(all_,"campaign"),"adsets":make(all_,"adset"),"ads":make_ads(all_)},
    }

def meta_breakdowns(df):
    print("  Lendo breakdowns...")
    try:
        df_ga = pd.read_csv(sheet_url("breakdown-gender-age"))
        df_ga["date"] = pd.to_datetime(df_ga["Date"], errors="coerce")
        df_ga["spend"]   = to_num(df_ga["Spend (Cost, Amount Spent)"])
        df_ga["purchase"]= to_num(df_ga["Action Omni Purchase"])
        df_ga["revenue"] = to_num(df_ga["Action Value Omni Purchase"])
        df_ga["age"]     = df_ga["Age (Breakdown)"].astype(str)
        df_ga["gender"]  = df_ga["Gender (Breakdown)"].astype(str)

        # Filtrar datas do lançamento
        date_min = df[df["is_lct"]]["date"].min()
        date_max = df[df["is_lct"]]["date"].max()
        df_ga = df_ga[(df_ga["date"]>=date_min)&(df_ga["date"]<=date_max)]

        AGE_ORDER = ["18-24","25-34","35-44","45-54","55-64","65+"]

        def seg(grp, dim):
            agg = grp.groupby(dim).agg(spend=("spend","sum"),purchase=("purchase","sum"),revenue=("revenue","sum")).reset_index()
            agg = agg[agg["spend"]>0]
            agg["cpa"] = (agg["spend"]/agg["purchase"]).where(agg["purchase"]>0).round(2)
            agg["roas"] = (agg["revenue"]/agg["spend"]).where(agg["spend"]>0).round(2)
            if dim=="age":
                agg["_o"] = agg[dim].apply(lambda x: AGE_ORDER.index(x) if x in AGE_ORDER else 99)
                agg = agg.sort_values("_o")
            else:
                agg = agg.sort_values("purchase", ascending=False)
            return [{"n":str(r[dim]),"spend":round(float(r["spend"]),2),
                     "pur":int(r["purchase"]),"cpa":safe(r["cpa"]),"roas":safe(r["roas"])} for _,r in agg.iterrows()]

        age_data    = seg(df_ga[df_ga["age"].isin(AGE_ORDER)], "age")
        gender_data = seg(df_ga[df_ga["gender"].isin(["female","male"])], "gender")

        # Região
        df_reg = pd.read_csv(sheet_url("breakdown-regiao"))
        df_reg["date"]    = pd.to_datetime(df_reg["Date"], errors="coerce")
        df_reg["spend"]   = to_num(df_reg["Spend (Cost, Amount Spent)"])
        df_reg["purchase"]= to_num(df_reg["Action Omni Purchase"])
        df_reg["revenue"] = to_num(df_reg["Action Value Omni Purchase"])
        df_reg["region"]  = df_reg["Region (Breakdown)"].astype(str)
        df_reg = df_reg[(df_reg["date"]>=date_min)&(df_reg["date"]<=date_max)]
        region_data = seg(df_reg, "region")

        return {"age":age_data,"gender":gender_data,"region":region_data[:15]}
    except Exception as e:
        print(f"  Aviso breakdown: {e}")
        return {"age":[],"gender":[],"region":[]}

# ══ HOTMART ═══════════════════════════════════════════════════════════════════

def load_hotmart():
    print("  Lendo hotmart...")
    df = pd.read_csv(URL_HOTMART)
    df["date"]  = pd.to_datetime(df["Data"], errors="coerce")
    df["valor"] = pd.to_numeric(df["Valor bruto"], errors="coerce").fillna(0)
    df = df[df["Status"].isin(["COMPLETE","APPROVED","complete","approved"])]
    if PRODUTOS_HOTMART:
        mask = df["Produto"].str.contains("|".join(PRODUTOS_HOTMART), na=False, case=False)
        df = df[mask]
    print(f"     {len(df)} vendas | R$ {df['valor'].sum():,.2f}")
    return df

def hotmart_process(df):
    total = df["valor"].sum(); qtd = len(df)
    pago  = df[df["Organico ou Pago"]=="Tráfego Pago"]["valor"].sum()
    org   = df[df["Organico ou Pago"]=="Orgânico"]["valor"].sum()

    kpis = {
        "total":round(float(total),2), "qtd":int(qtd),
        "pago":round(float(pago),2),   "organico":round(float(org),2),
        "ticket_medio":round(float(total/qtd),2) if qtd>0 else None,
    }

    # Daily — fonte de verdade para faturamento
    agg = df.groupby("date").agg(qtd=("valor","count"),valor=("valor","sum")).reset_index().sort_values("date")
    daily = {
        "days":  [r["date"].strftime("%d/%m") for _,r in agg.iterrows()],
        "qtd":   [int(r["qtd"]) for _,r in agg.iterrows()],
        "valor": [round(float(r["valor"]),2) for _,r in agg.iterrows()],
    }

    # Por tipo
    by_tipo = df.groupby("Organico ou Pago").agg(qtd=("valor","count"),valor=("valor","sum")).reset_index()
    tipo = [{"n":str(r["Organico ou Pago"]),"qtd":int(r["qtd"]),"valor":round(float(r["valor"]),2)} for _,r in by_tipo.iterrows()]

    # Por source
    by_src = df.groupby("utm_source").agg(qtd=("valor","count"),valor=("valor","sum")).reset_index().sort_values("valor",ascending=False)
    source = [{"n":str(r["utm_source"]),"qtd":int(r["qtd"]),"valor":round(float(r["valor"]),2)} for _,r in by_src.iterrows()]

    # Por campaign
    by_camp = df.groupby("utm_campaign").agg(qtd=("valor","count"),valor=("valor","sum")).reset_index().sort_values("valor",ascending=False)
    campaign = [{"n":str(r["utm_campaign"]),"qtd":int(r["qtd"]),"valor":round(float(r["valor"]),2)} for _,r in by_camp.iterrows()]

    return kpis, daily, {"tipo":tipo,"source":source,"campaign":campaign}

# ══ PESQUISA ══════════════════════════════════════════════════════════════════

def load_pesquisa():
    print("  Lendo pesquisa...")
    df = pd.read_csv(URL_PESQUISA)
    return df

def pesquisa_process(df):
    PERGUNTAS = [
        "Você já trabalha como consultora de estilo?",
        "Hoje, a Consultoria de Estilo é sua principal fonte de renda?",
        "Qual é a sua faixa de renda mensal atualmente?",
        "Qual a sua opinião sobre os métodos tradicionais?",
        "Há quanto tempo você me conhece?",
        "Você já ouviu falar do método Styletelling e da semiótica visual?",
        "Qual é a sua maior dificuldade hoje na consultoria de estilo?",
        "Qual é a sua idade?",
    ]
    UTM_COLS = ["utm_source","utm_medium","utm_campaign","utm_content"]

    graficos = []
    for p in PERGUNTAS:
        if p not in df.columns: continue
        vc = df[p].value_counts()
        total = vc.sum()
        graficos.append({
            "pergunta":p,
            "opcoes":[{"label":str(k),"qtd":int(v),"pct":round(v/total*100,1)} for k,v in vc.items()]
        })

    # Valores únicos por utm para filtros
    filtros = {}
    for col in UTM_COLS:
        if col in df.columns:
            vals = sorted(df[col].dropna().unique().tolist())
            filtros[col] = [v for v in vals if v and v!="nan"]

    # Dados brutos para filtro dinâmico no front
    rows = []
    for _,r in df.iterrows():
        row = {}
        for p in PERGUNTAS:
            if p in df.columns: row[p] = str(r[p]) if pd.notna(r.get(p)) else None
        for col in UTM_COLS:
            if col in df.columns: row[col] = str(r[col]) if pd.notna(r.get(col)) else None
        rows.append(row)

    return {"total":len(df),"graficos":graficos,"filtros":filtros,"rows":rows,"perguntas":PERGUNTAS}

# ══ INJEÇÃO ════════════════════════════════════════════════════════════════════

def replace_js_const(html, name, value):
    pattern = rf"const {name}\s*=\s*(?:null|true|false|\d[\d\.]*|'[^']*'|\"[^\"]*\"|\{{[\s\S]*?\}}|\[[\s\S]*?\])\s*;"
    replacement = f"const {name} = {json.dumps(value, ensure_ascii=False)};"
    new_html, count = re.subn(pattern, replacement, html, count=1)
    if count==0: print(f"  AVISO: não encontrou const {name}")
    return new_html

def inject_all(template_path, meta_k, meta_d, meta_t, bd, hot_k, hot_d, hot_o, pes):
    html = Path(template_path).read_text(encoding="utf-8")
    html = replace_js_const(html,"META_KPIS",   meta_k)
    html = replace_js_const(html,"META_DAILY",  meta_d)
    html = replace_js_const(html,"META_TABLES", meta_t)
    html = replace_js_const(html,"META_BD",     bd)
    html = replace_js_const(html,"HOT_KPIS",    hot_k)
    html = replace_js_const(html,"HOT_DAILY",   hot_d)
    html = replace_js_const(html,"HOT_ORIGIN",  hot_o)
    html = replace_js_const(html,"PESQUISA",    pes)

    html = re.sub(r"const LANCAMENTO_COD\s*=\s*'[^']*'", f"const LANCAMENTO_COD='{LANCAMENTO_COD}'", html, count=1)
    html = re.sub(r"const NOME_CLIENTE\s*=\s*'[^']*'",   f"const NOME_CLIENTE='{NOME_CLIENTE}'",     html, count=1)
    html = re.sub(r"const LOGO_LETRA\s*=\s*'[^']*'",     f"const LOGO_LETRA='{LOGO_LETRA}'",         html, count=1)
    html = re.sub(r"const COR_ACENTO\s*=\s*'[^']*'",     f"const COR_ACENTO='{COR_ACENTO}'",         html, count=1)
    html = re.sub(r"const CPA_BOM\s*=\s*[\d\.]+",        f"const CPA_BOM={CPA_BOM}",                 html, count=1)
    html = re.sub(r"const CPA_MEDIO\s*=\s*[\d\.]+",      f"const CPA_MEDIO={CPA_MEDIO}",             html, count=1)
    html = re.sub(r"const ROAS_BOM\s*=\s*[\d\.]+",       f"const ROAS_BOM={ROAS_BOM}",               html, count=1)
    html = re.sub(r"const ROAS_MEDIO\s*=\s*[\d\.]+",     f"const ROAS_MEDIO={ROAS_MEDIO}",           html, count=1)

    today = date.today().strftime("%d/%m/%Y")
    html = re.sub(r"\d{2}/\d{2}/\d{4} · via planilha", f"{today} · via planilha", html)
    return html

# ══ MAIN ═══════════════════════════════════════════════════════════════════════

def main():
    print("="*60)
    print(f"Dashboard Lançamento — {NOME_CLIENTE} / {LANCAMENTO_COD or 'Todos'}")
    print("="*60)

    img_dir = Path("imgs"); img_dir.mkdir(exist_ok=True)

    print("\n[META ADS]")
    df_meta   = load_meta()
    meta_k    = meta_kpis(df_meta)
    meta_d    = meta_daily(df_meta)
    meta_t    = meta_tables(df_meta, img_dir)
    bd        = meta_breakdowns(df_meta)
    print(f"  ✓ {len(meta_t['lct']['camps'])} camps | {len(meta_t['lct']['adsets'])} adsets | {len(meta_t['lct']['ads'])} ads")

    print("\n[HOTMART]")
    df_hot    = load_hotmart()
    hot_k, hot_d, hot_o = hotmart_process(df_hot)
    print(f"  ✓ {hot_k['qtd']} vendas | R$ {hot_k['total']:,.2f}")

    print("\n[PESQUISA]")
    df_pes    = load_pesquisa()
    pes       = pesquisa_process(df_pes)
    print(f"  ✓ {pes['total']} respostas")

    print("\n[HTML]")
    if not Path(TEMPLATE_FILE).exists():
        print(f"  ERRO: {TEMPLATE_FILE} não encontrado"); return

    html = inject_all(TEMPLATE_FILE, meta_k, meta_d, meta_t, bd, hot_k, hot_d, hot_o, pes)
    Path(OUTPUT_FILE).write_text(html, encoding="utf-8")
    print(f"  ✓ {OUTPUT_FILE} ({len(html)//1024}KB)")

    # data.json para painel agência
    data_json = {
        "cliente":NOME_CLIENTE,"cor":COR_ACENTO,"letra":LOGO_LETRA,
        "lancamento":LANCAMENTO_COD,"atualizado":date.today().strftime("%d/%m/%Y"),
        "kpis":{
            "spend":   meta_k["lct"].get("spend"),
            "revenue": hot_k.get("total"),
            "roas":    round(hot_k["total"]/meta_k["lct"]["spend"],2) if meta_k["lct"].get("spend") else None,
            "vendas":  hot_k.get("qtd"),
            "cpa":     meta_k["lct"].get("cpa"),
        }
    }
    Path("data.json").write_text(json.dumps(data_json,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"  ✓ data.json")
    print("="*60)

if __name__=="__main__":
    main()
