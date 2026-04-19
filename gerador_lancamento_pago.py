#!/usr/bin/env python3
"""Gerador Dashboard Lançamento Pago v4"""

import pandas as pd, json, re, hashlib, requests
from datetime import date
from pathlib import Path

# ══════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════

SHEET_ID         = "1wxlEwwiIzPNfObxyjuhaB6uiR7PWj9VdDcQgKx_H8xk"
TEMPLATE_FILE    = "dashboard_lancamento_pago.html"
OUTPUT_FILE      = "index.html"

NOME_CLIENTE     = "Carol"
LOGO_LETRA       = "C"
COR_ACENTO       = "#e11d48"

LANCAMENTO_COD   = "VSE02"        # filtra campanhas; "" = ver tudo

PRODUTOS_HOTMART = ["ALL"]              # ex: ["Semana Pensar Estilo"]; [] = todos

CPA_BOM          = 50
CPA_MEDIO        = 80
ROAS_BOM         = 1.0
ROAS_MEDIO       = 0.6

# ══════════════════════════════════════════════════════
def sheet_url(t): return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={t}"
URL_META = sheet_url("meta-ads")
URL_HOT  = sheet_url("hotmart+tratado")
URL_PES  = sheet_url("Pesquisa")
URL_GA   = sheet_url("breakdown-gender-age")
URL_PT   = sheet_url("breakdown-platform")

def to_num(s):
    # Se já é numérico, não converter (evita remover pontos decimais)
    if pd.api.types.is_numeric_dtype(s):
        return s.fillna(0)
    return pd.to_numeric(
        s.astype(str).str.replace("R$","",regex=False)
         .str.replace(".","",regex=False).str.replace(",",".",regex=False).str.strip(),
        errors="coerce").fillna(0)
def safe(v):
    if v is None or (isinstance(v,float) and pd.isna(v)): return None
    return round(float(v),2) if float(v)!=0 else None
def download_thumb(url, d):
    if not url or str(url)=="nan": return ""
    try:
        ext=".png" if ".png" in url.lower() else ".jpg"
        fname=hashlib.md5(url.encode()).hexdigest()[:16]+ext
        fp=d/fname
        if not fp.exists():
            r=requests.get(url,timeout=10,headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code==200: fp.write_bytes(r.content)
            else: return ""
        return "imgs/"+fname
    except: return ""

# ══ HOTMART (carrega primeiro para ter ticket_medio) ══
def load_hotmart():
    print("  Lendo hotmart...")
    df=pd.read_csv(URL_HOT)
    df["date"]=pd.to_datetime(df["Data"],errors="coerce")
    df["valor"]=pd.to_numeric(df["Valor bruto"],errors="coerce").fillna(0)
    df=df[df["Status"].isin(["COMPLETE","APPROVED","complete","approved"])]
    if PRODUTOS_HOTMART and PRODUTOS_HOTMART != ["ALL"]:
        df=df[df["Produto"].str.contains("|".join(PRODUTOS_HOTMART),na=False,case=False)]
    print(f"     {len(df)} vendas | R$ {df['valor'].sum():,.2f}")
    return df

def hotmart_process(df):
    total=df["valor"].sum(); qtd=len(df)
    ticket=round(float(total/qtd),2) if qtd>0 else 0
    pago=df[df["Organico ou Pago"]=="Tráfego Pago"]
    org =df[df["Organico ou Pago"]=="Orgânico"]
    # Vendas por produto (pago vs orgânico)
    por_produto=[]
    for prod, gdf in df.groupby("Produto"):
        p_pago=gdf[gdf["Organico ou Pago"]=="Tráfego Pago"]
        p_org =gdf[gdf["Organico ou Pago"]=="Orgânico"]
        por_produto.append({
            "produto": str(prod),
            "total_qtd": int(len(gdf)),
            "total_val": round(float(gdf["valor"].sum()),2),
            "pago_qtd":  int(len(p_pago)),
            "pago_val":  round(float(p_pago["valor"].sum()),2),
            "org_qtd":   int(len(p_org)),
            "org_val":   round(float(p_org["valor"].sum()),2),
        })
    por_produto.sort(key=lambda x: x["total_val"], reverse=True)

    kpis={"total":round(float(total),2),"qtd":int(qtd),"ticket_medio":ticket,
          "pago_qtd":int(len(pago)),"pago_val":round(float(pago["valor"].sum()),2),
          "org_qtd": int(len(org)), "org_val": round(float(org["valor"].sum()),2),
          "por_produto": por_produto}
    agg=df.groupby("date").agg(qtd=("valor","count"),valor=("valor","sum")).reset_index().sort_values("date")
    daily={"days":[r["date"].strftime("%d/%m") for _,r in agg.iterrows()],
           "qtd": [int(r["qtd"]) for _,r in agg.iterrows()],
           "valor":[round(float(r["valor"]),2) for _,r in agg.iterrows()]}
    return kpis, daily

# ══ META ADS ══════════════════════════════════════════
def load_meta():
    print("  Lendo meta-ads...")
    df=pd.read_csv(URL_META)
    df=df.rename(columns={"Date":"date","Campaign Name":"campaign","Adset Name":"adset",
        "Ad Name":"ad","Thumbnail URL":"thumb","Spend (Cost, Amount Spent)":"spend",
        "Impressions":"impressions","Action Link Clicks":"link_clicks",
        "Action Landing Page View":"page_view","Action Omni Initiated Checkout":"init_checkout",
        "Action Omni Purchase":"purchase","Action Value Omni Purchase":"revenue_meta"})
    df["date"]=pd.to_datetime(df["date"],errors="coerce")
    for c in ["spend","impressions","link_clicks","page_view","init_checkout","purchase","revenue_meta"]:
        if c in df.columns: df[c]=to_num(df[c])
    df["is_lct"]=df["campaign"].str.contains(LANCAMENTO_COD,na=False,case=False) if LANCAMENTO_COD else True
    df=df.dropna(subset=["date"])
    print(f"     {len(df)} linhas | {df['date'].min().date()} → {df['date'].max().date()}")
    return df

def calc_kpis(p, ticket):
    sp=float(p["spend"].sum()); imp=float(p["impressions"].sum())
    lc=float(p["link_clicks"].sum()); pv=float(p["page_view"].sum())
    ic=float(p["init_checkout"].sum()); pur=float(p["purchase"].sum())
    rev=pur*ticket  # receita correta = purchase × ticket_medio
    return {"spend":round(sp,2),"impressions":int(imp),"link_clicks":int(lc),
            "page_view":int(pv),"init_checkout":int(ic),"purchase":int(pur),
            "revenue":round(rev,2),
            "ctr":   round(lc/imp*100,2) if imp>0 else None,
            "connect_rate":round(pv/lc*100,2) if lc>0 else None,
            "tx_ic": round(ic/pv*100,2) if pv>0 else None,
            "tx_checkout":round(pur/ic*100,2) if ic>0 else None,
            "tx_conv":round(pur/pv*100,2) if pv>0 else None,
            "cpa":   round(sp/pur,2) if pur>0 else None,
            "roas":  round(rev/sp,2) if sp>0 else None,
            "cpm":   round(sp/imp*1000,2) if imp>0 else None}

def meta_kpis(df, ticket):
    return {"lct":calc_kpis(df[df["is_lct"]],ticket),"all":calc_kpis(df,ticket)}

def build_daily(p, ticket):
    agg=p.groupby("date").agg(spend=("spend","sum"),impressions=("impressions","sum"),
        link_clicks=("link_clicks","sum"),page_view=("page_view","sum"),
        init_checkout=("init_checkout","sum"),purchase=("purchase","sum")
    ).reset_index().sort_values("date")
    out={k:[] for k in ["days","spend","impressions","link_clicks","page_view",
                         "init_checkout","purchase","revenue","ctr","connect_rate",
                         "tx_ic","tx_checkout","tx_conv","cpa","roas","cpm"]}
    for _,r in agg.iterrows():
        sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
        pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"])
        rev=pur*ticket
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
        out["roas"].append(round(rev/sp,2) if sp>0 else None)
        out["cpm"].append(round(sp/imp*1000,2) if imp>0 else None)
    return out

def meta_daily(df, ticket):
    return {"lct":build_daily(df[df["is_lct"]],ticket),"all":build_daily(df,ticket)}

def meta_daily_camps(df, ticket):
    """Daily por campanha para filtro nas métricas diárias"""
    result={"lct":{},"all":{}}
    for key,subset in [("lct",df[df["is_lct"]]),("all",df)]:
        for camp in subset["campaign"].unique():
            p=subset[subset["campaign"]==camp]
            result[key][camp]=build_daily(p,ticket)
    return result

def build_rows(agg, col, ticket):
    rows=[]
    for _,r in agg.sort_values("purchase",ascending=False).iterrows():
        sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
        pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"])
        rev=float(r.get("revenue_meta",0) or pur*ticket)  # usa Action Value se disponível
        rows.append({"n":str(r[col]),"spend":round(sp,2),"imp":int(imp),"lc":int(lc),
            "pv":int(pv),"ic":int(ic),"pur":int(pur),"rev":round(rev,2),
            "ctr":round(lc/imp*100,2) if imp>0 else None,
            "cr": round(pv/lc*100,2)  if lc>0 else None,
            "tx_ic":round(ic/pv*100,2) if pv>0 else None,
            "tx_ck":round(pur/ic*100,2) if ic>0 else None,
            "tx_cv":round(pur/pv*100,2) if pv>0 else None,
            "cpa":round(sp/pur,2) if pur>0 else None,
            "roas":round(rev/sp,2) if sp>0 else None,
            "cpm":round(sp/imp*1000,2) if imp>0 else None})
    return rows

def meta_tables_period(df, p, img_dir, ticket):
    """Calcula tabelas para um subset p do df"""
    def ag(sub,col):
        return sub.groupby(col).agg(spend=("spend","sum"),impressions=("impressions","sum"),
            link_clicks=("link_clicks","sum"),page_view=("page_view","sum"),
            init_checkout=("init_checkout","sum"),purchase=("purchase","sum"),
            revenue_meta=("revenue_meta","sum")).reset_index()
    def make(sub,col): return build_rows(ag(sub,col),col,ticket)
    def make_adsets(sub):
        agg2=sub.groupby(["campaign","adset"]).agg(spend=("spend","sum"),impressions=("impressions","sum"),
            link_clicks=("link_clicks","sum"),page_view=("page_view","sum"),
            init_checkout=("init_checkout","sum"),purchase=("purchase","sum"),
            revenue_meta=("revenue_meta","sum")).reset_index()
        rows=[]
        for _,r in agg2.sort_values("purchase",ascending=False).iterrows():
            sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"])
            pv=float(r["page_view"]); ic=float(r["init_checkout"]); pur=float(r["purchase"])
            rev=float(r.get("revenue_meta",0) or pur*ticket)
            rows.append({"n":str(r["adset"]),"camp":str(r["campaign"]),"spend":round(sp,2),
                "imp":int(imp),"lc":int(lc),"pv":int(pv),"ic":int(ic),"pur":int(pur),"rev":round(rev,2),
                "ctr":round(lc/imp*100,2) if imp>0 else None,
                "cr": round(pv/lc*100,2)  if lc>0 else None,
                "tx_ic":round(ic/pv*100,2) if pv>0 else None,
                "tx_ck":round(pur/ic*100,2) if ic>0 else None,
                "tx_cv":round(pur/pv*100,2) if pv>0 else None,
                "cpa":round(sp/pur,2) if pur>0 else None,
                "roas":round(rev/sp,2) if sp>0 else None,
                "cpm":round(sp/imp*1000,2) if imp>0 else None})
        return rows
    def make_ads(sub):
        df_t=sub[sub["thumb"].notna()&(sub["thumb"].astype(str)!="nan")].copy()
        if df_t.empty: return []
        agg=df_t.groupby(["ad","adset","campaign","thumb"]).agg(spend=("spend","sum"),impressions=("impressions","sum"),
            link_clicks=("link_clicks","sum"),purchase=("purchase","sum")).reset_index().sort_values("purchase",ascending=False)
        ads=[]
        for _,r in agg.iterrows():
            sp=float(r["spend"]); imp=float(r["impressions"]); lc=float(r["link_clicks"]); pur=float(r["purchase"])
            ads.append({"n":str(r["ad"]),"adset":str(r["adset"]),"camp":str(r["campaign"]),
                "thumb":download_thumb(str(r["thumb"]),img_dir),
                "spend":round(sp,2),"pur":int(pur),"imp":int(imp),"lc":int(lc),
                "ctr":round(lc/imp*100,2) if imp>0 else None,
                "cpa":round(sp/pur,2) if pur>0 else None})
        return ads
    return {"camps":make(p,"campaign"),"adsets":make_adsets(p),"ads":make_ads(p)}

def meta_tables(df, img_dir, ticket):
    """Exporta tabelas por período: 1d,7d,14d,30d,all"""
    last=df["date"].max()
    result={"lct":{},"all":{}}
    periods={"1":1,"7":7,"14":14,"30":30,"all":0}
    for key,subset in [("lct",df[df["is_lct"]]),("all",df)]:
        for pname,n in periods.items():
            p=subset[subset["date"]>=last-pd.Timedelta(days=n-1)] if n>0 else subset
            result[key][pname]=meta_tables_period(df,p,img_dir,ticket)
            print(f"     [{key}][{pname}]: {len(result[key][pname]['camps'])} camps")
    return result

def meta_breakdowns(df):
    print("  Lendo breakdowns...")
    last=df[df["is_lct"]]["date"].max()
    AGE_ORDER=["18-24","25-34","35-44","45-54","55-64","65+"]
    def seg(agg,dim):
        agg=agg[agg["spend"]>0].copy()
        agg["cpa"]=(agg["spend"]/agg["purchase"]).where(agg["purchase"]>0).round(2)
        return [{"n":str(r[dim]),"spend":round(float(r["spend"]),2),"pur":int(r["purchase"]),"cpa":safe(r["cpa"])} for _,r in agg.iterrows()]
    try:
        df_ga=pd.read_csv(URL_GA)
        df_ga["date"]=pd.to_datetime(df_ga["Date"],errors="coerce")
        df_ga["spend"]=to_num(df_ga["Spend (Cost, Amount Spent)"])
        df_ga["purchase"]=to_num(df_ga["Action Omni Purchase"])
        df_ga["age"]=df_ga["Age (Breakdown)"].astype(str)
        df_ga["gender"]=df_ga["Gender (Breakdown)"].astype(str)
        df_ga=df_ga.dropna(subset=["date"])
    except Exception as e: print(f"  Aviso GA: {e}"); df_ga=pd.DataFrame()
    try:
        df_pt=pd.read_csv(URL_PT)
        df_pt["date"]=pd.to_datetime(df_pt["Date"],errors="coerce")
        df_pt["spend"]=to_num(df_pt["Spend (Cost, Amount Spent)"])
        df_pt["purchase"]=to_num(df_pt["Action Omni Purchase"])
        df_pt["platform"]=df_pt["Platform Position (Breakdown)"].astype(str)
        df_pt=df_pt.dropna(subset=["date"])
    except Exception as e: print(f"  Aviso PT: {e}"); df_pt=pd.DataFrame()

    result={}
    for pname,n in [("1",1),("7",7),("14",14),("30",30),("all",0)]:
        if n>0:
            start=last-pd.Timedelta(days=n-1)
            pga=df_ga[df_ga["date"]>=start] if len(df_ga)>0 else df_ga
            ppt=df_pt[df_pt["date"]>=start] if len(df_pt)>0 else df_pt
        else:
            pga=df_ga; ppt=df_pt
        if len(pga)>0:
            ag_age=pga[pga["age"].isin(AGE_ORDER)].groupby("age").agg(spend=("spend","sum"),purchase=("purchase","sum")).reset_index()
            ag_age["_o"]=ag_age["age"].apply(lambda x:AGE_ORDER.index(x) if x in AGE_ORDER else 99)
            age_d=seg(ag_age.sort_values("_o"),"age")
            ag_gen=pga[pga["gender"].isin(["female","male"])].groupby("gender").agg(spend=("spend","sum"),purchase=("purchase","sum")).reset_index().sort_values("purchase",ascending=False)
            gen_d=seg(ag_gen,"gender")
        else: age_d=[]; gen_d=[]
        if len(ppt)>0:
            ag_pt=ppt.groupby("platform").agg(spend=("spend","sum"),purchase=("purchase","sum")).reset_index().sort_values("purchase",ascending=False).head(8)
            plat_d=seg(ag_pt,"platform")
        else: plat_d=[]
        result[pname]={"age":age_d,"gender":gen_d,"platform":plat_d}
    return result

# ══ PESQUISA ══════════════════════════════════════════
def load_pesquisa():
    print("  Lendo pesquisa..."); return pd.read_csv(URL_PES)

def pesquisa_process(df, hot_qtd):
    PERGUNTAS=["Você já trabalha como consultora de estilo?",
               "Hoje, a Consultoria de Estilo é sua principal fonte de renda?",
               "Qual é a sua faixa de renda mensal atualmente?",
               "Qual a sua opinião sobre os métodos tradicionais?",
               "Há quanto tempo você me conhece?",
               "Você já ouviu falar do método Styletelling e da semiótica visual?",
               "Qual é a sua maior dificuldade hoje na consultoria de estilo?",
               "Qual é a sua idade?"]
    UTM_COLS=["utm_source","utm_medium","utm_campaign","utm_content"]
    graficos=[]
    for p in PERGUNTAS:
        if p not in df.columns: continue
        vc=df[p].value_counts(); total=vc.sum()
        graficos.append({"pergunta":p,"opcoes":[{"label":str(k),"qtd":int(v),"pct":round(v/total*100,1)} for k,v in vc.items()]})
    filtros={}
    for col in UTM_COLS:
        if col in df.columns:
            filtros[col]=sorted([v for v in df[col].dropna().unique().tolist() if v and str(v)!="nan"])
    rows=[]
    for _,r in df.iterrows():
        row={}
        for p in PERGUNTAS: row[p]=str(r[p]) if p in df.columns and pd.notna(r.get(p)) else None
        for col in UTM_COLS: row[col]=str(r[col]) if col in df.columns and pd.notna(r.get(col)) else None
        rows.append(row)
    return {"total":len(df),"hot_qtd":int(hot_qtd),"graficos":graficos,"filtros":filtros,"rows":rows,"perguntas":PERGUNTAS}

# ══ INJEÇÃO ════════════════════════════════════════════
def replace_js_const(html, name, value):
    pattern=rf"const {name}\s*=\s*(?:null|true|false|-?\d[\d\.]*|'[^']*'|\"[^\"]*\"|\{{[\s\S]*?\}}|\[[\s\S]*?\])\s*;"
    repl=f"const {name} = {json.dumps(value,ensure_ascii=False)};"
    new_html,count=re.subn(pattern,repl,html,count=1)
    if count==0: print(f"  AVISO: não encontrou const {name}")
    return new_html

def inject_all(tpl, meta_k, meta_d, meta_dc, meta_t, meta_bd, hot_k, hot_d, pes, ticket):
    html=Path(tpl).read_text(encoding="utf-8")
    html=replace_js_const(html,"META_KPIS",    meta_k)
    html=replace_js_const(html,"META_DAILY",       meta_d)
    html=replace_js_const(html,"META_DAILY_CAMPS", meta_dc)
    html=replace_js_const(html,"META_TABLES",      meta_t)
    html=replace_js_const(html,"META_BD",      meta_bd)
    html=replace_js_const(html,"HOT_KPIS",     hot_k)
    html=replace_js_const(html,"HOT_DAILY",    hot_d)
    html=replace_js_const(html,"PESQUISA",     pes)
    html=replace_js_const(html,"TICKET_MEDIO", ticket)
    # Data de geração em Brasília (UTC-3) para o filtro de período correto
    from datetime import timezone, timedelta
    brt = timezone(timedelta(hours=-3))
    hoje_brt = date.today()  # data local do servidor (GitHub Actions = UTC, mas usamos a data atual)
    html=replace_js_const(html,"DATA_GERACAO", hoje_brt.strftime("%Y-%m-%d"))
    for k,v in [("LANCAMENTO_COD",f"'{LANCAMENTO_COD}'"),("NOME_CLIENTE",f"'{NOME_CLIENTE}'"),
                ("LOGO_LETRA",f"'{LOGO_LETRA}'"),("COR_ACENTO",f"'{COR_ACENTO}'"),
                ("CPA_BOM",str(CPA_BOM)),("CPA_MEDIO",str(CPA_MEDIO)),
                ("ROAS_BOM",str(ROAS_BOM)),("ROAS_MEDIO",str(ROAS_MEDIO))]:
        html=re.sub(rf"const {k}\s*=\s*[^;]+;",f"const {k}={v};",html,count=1)
    html=re.sub(r"\d{2}/\d{2}/\d{4} · via planilha",date.today().strftime("%d/%m/%Y")+" · via planilha",html)
    return html

# ══ MAIN ═══════════════════════════════════════════════
def main():
    print("="*60)
    print(f"Dashboard Lançamento — {NOME_CLIENTE} / {LANCAMENTO_COD or 'Todos'}")
    print("="*60)
    img_dir=Path("imgs"); img_dir.mkdir(exist_ok=True)

    print("\n[HOTMART]")
    df_hot=load_hotmart()
    hot_k,hot_d=hotmart_process(df_hot)
    ticket=hot_k["ticket_medio"]
    print(f"  ✓ {hot_k['qtd']} vendas | R$ {hot_k['total']:,.2f} | ticket R$ {ticket:.2f}")

    print("\n[META ADS]")
    df_meta=load_meta()
    m_k=meta_kpis(df_meta,ticket)
    m_d=meta_daily(df_meta,ticket)
    m_dc=meta_daily_camps(df_meta,ticket)
    m_t=meta_tables(df_meta,img_dir,ticket)
    m_bd=meta_breakdowns(df_meta)
    print(f"  ✓ {len(m_t['lct']['all']['camps'])} camps | {len(m_t['lct']['all']['adsets'])} adsets | {len(m_t['lct']['all']['ads'])} ads")

    print("\n[PESQUISA]")
    df_pes=load_pesquisa()
    pes=pesquisa_process(df_pes, hot_k["qtd"])
    print(f"  ✓ {pes['total']} respostas")

    print("\n[HTML]")
    if not Path(TEMPLATE_FILE).exists():
        print(f"  ERRO: {TEMPLATE_FILE} não encontrado"); return
    html=inject_all(TEMPLATE_FILE,m_k,m_d,m_dc,m_t,m_bd,hot_k,hot_d,pes,ticket)
    Path(OUTPUT_FILE).write_text(html,encoding="utf-8")
    print(f"  ✓ {OUTPUT_FILE} ({len(html)//1024}KB)")

    data_json={"cliente":NOME_CLIENTE,"cor":COR_ACENTO,"letra":LOGO_LETRA,
               "lancamento":LANCAMENTO_COD,"atualizado":date.today().strftime("%d/%m/%Y"),
               "kpis":{"spend":m_k["lct"].get("spend"),"vendas":hot_k.get("qtd"),
                       "faturamento":hot_k.get("total"),"cpa":m_k["lct"].get("cpa")}}
    Path("data.json").write_text(json.dumps(data_json,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"  ✓ data.json\n{'='*60}")

if __name__=="__main__":
    main()
