from __future__ import annotations

from io import BytesIO
from datetime import date
import unicodedata

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ============================================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================================
st.set_page_config(
    page_title="Dashboard Performance AWB",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# ESTILO VISUAL
# ============================================================
st.markdown(
    """
<style>
    .stApp { background-color: #F5F7FB; }
    .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }

    .hero {
        background: linear-gradient(135deg, #003B71 0%, #005DAA 70%, #FF8A00 140%);
        color: white;
        padding: 24px 28px;
        border-radius: 22px;
        box-shadow: 0 10px 28px rgba(0,0,0,0.12);
        margin-bottom: 18px;
    }
    .hero h1 { margin: 0; font-size: 31px; line-height: 1.15; }
    .hero p { margin-top: 8px; margin-bottom: 0; opacity: 0.92; font-size: 15px; }

    .section-title {
        color: #003B71;
        font-size: 21px;
        font-weight: 800;
        margin-top: 26px;
        margin-bottom: 12px;
    }

    .kpi-card {
        background: #FFFFFF;
        border-radius: 18px;
        padding: 18px 18px;
        min-height: 112px;
        border: 1px solid #E7ECF3;
        box-shadow: 0 5px 18px rgba(18,38,63,0.07);
    }
    .kpi-title { color: #627084; font-size: 13px; font-weight: 700; margin-bottom: 8px; }
    .kpi-value { color: #003B71; font-size: 27px; font-weight: 900; line-height: 1.1; }
    .kpi-note { color: #7A869A; font-size: 12px; margin-top: 7px; }

    .insight-box {
        background: #FFFFFF;
        border-left: 6px solid #FF8A00;
        padding: 15px 18px;
        border-radius: 16px;
        border-top: 1px solid #E7ECF3;
        border-right: 1px solid #E7ECF3;
        border-bottom: 1px solid #E7ECF3;
        box-shadow: 0 5px 18px rgba(18,38,63,0.06);
        color: #233142;
        margin-bottom: 12px;
    }

    div[data-testid="stMetricValue"] { color: #003B71; }
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# FUNÇÕES DE APOIO
# ============================================================
def remover_acentos(texto: str) -> str:
    texto = str(texto)
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(ch for ch in texto if not unicodedata.combining(ch))


def norm_txt(texto: object) -> str:
    return remover_acentos(str(texto).strip().lower())


def format_int(valor: float | int) -> str:
    try:
        return f"{int(valor):,}".replace(",", ".")
    except Exception:
        return "0"


def format_pct(valor: float | int | None) -> str:
    if valor is None or pd.isna(valor):
        return "-"
    return f"{float(valor):.1f}%".replace(".", ",")


def format_float(valor: float | int | None, casas: int = 1) -> str:
    if valor is None or pd.isna(valor):
        return "-"
    return f"{float(valor):.{casas}f}".replace(".", ",")


def render_kpi(titulo: str, valor: str, nota: str = "") -> None:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-title">{titulo}</div>
            <div class="kpi-value">{valor}</div>
            <div class="kpi-note">{nota}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def encontrar_coluna(df: pd.DataFrame, opcoes: list[str]) -> str | None:
    mapa = {norm_txt(c): c for c in df.columns}
    for opcao in opcoes:
        if norm_txt(opcao) in mapa:
            return mapa[norm_txt(opcao)]
    return None


def classificar_status(valor: object) -> str:
    txt = norm_txt(valor)

    if any(x in txt for x in ["entregue", "delivered"]):
        return "Entregue"
    if any(x in txt for x in ["pendente entrega", "out for delivery", "saiu para entrega"]):
        return "Pendente entrega"
    if any(x in txt for x in ["pendente embarque", "accepted", "aguardando embarque"]):
        return "Pendente embarque"
    if any(x in txt for x in ["transito", "transferencia", "transferido", "manifestado", "voo", "rota"]):
        return "Em trânsito"
    if any(x in txt for x in ["insucesso", "ocorr", "devol", "extravio", "retido", "avaria", "cancel"]):
        return "Ocorrência / Insucesso"
    if any(x in txt for x in ["pendente", "aguardando", "parado"]):
        return "Pendente"
    return "Outros"


def status_nao_finalizado(status_grupo: object) -> bool:
    return str(status_grupo) != "Entregue"


def faixa_aging(dias: float | int | None) -> str:
    if dias is None or pd.isna(dias):
        return "Sem data"
    if dias <= 1:
        return "0-24h"
    if dias <= 2:
        return "24-48h"
    if dias <= 3:
        return "48-72h"
    return ">72h"


def definir_risco(row: pd.Series) -> str:
    if row.get("Status Grupo") == "Entregue":
        return "Finalizado"
    if pd.isna(row.get("ApproxSLA_dt")):
        return "Sem SLA"
    agora = pd.Timestamp.now()
    sla = row.get("ApproxSLA_dt")
    horas = (sla - agora).total_seconds() / 3600
    if horas < 0:
        return "Fora SLA"
    if horas <= 24:
        return "Risco 24h"
    return "Dentro do prazo"


def gerar_excel(df_export: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_export.to_excel(writer, sheet_name="Base Filtrada", index=False)

        workbook = writer.book
        worksheet = writer.sheets["Base Filtrada"]
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#003B71", "font_color": "white", "border": 1})
        for col_num, value in enumerate(df_export.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            worksheet.set_column(col_num, col_num, min(max(len(str(value)) + 2, 12), 35))
    return output.getvalue()


@st.cache_data(show_spinner=False)
def carregar_arquivo(uploaded_file) -> pd.DataFrame:
    nome = uploaded_file.name.lower()
    if nome.endswith(".csv"):
        df0 = pd.read_csv(uploaded_file, sep=None, engine="python")
    else:
        df0 = pd.read_excel(uploaded_file)
    df0.columns = [str(c).strip() for c in df0.columns]
    return df0


# ============================================================
# CABEÇALHO
# ============================================================
st.markdown(
    """
    <div class="hero">
        <h1>📦 Dashboard de Performance AWB</h1>
        <p>Torre de controle operacional para acompanhar emissões, SLA, carga parada, ofensores, destino final e fluxo entre unidades.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# UPLOAD
# ============================================================
with st.sidebar:
    st.header("📁 Arquivo")
    arquivo = st.file_uploader("Carregue a planilha AWBStatusAtPieceLevel", type=["xlsx", "xls", "csv"])

if arquivo is None:
    st.info("Carregue o Excel para iniciar a análise.")
    st.stop()

try:
    df = carregar_arquivo(arquivo)
except Exception as exc:
    st.error(f"Erro ao ler o arquivo: {exc}")
    st.stop()

if df.empty:
    st.warning("A planilha está vazia.")
    st.stop()


# ============================================================
# MAPEAMENTO DE COLUNAS REAIS
# ============================================================
col_awb_prefix = encontrar_coluna(df, ["AWBPrefix"])
col_awb_number = encontrar_coluna(df, ["AWBNumber"])
col_origin = encontrar_coluna(df, ["OriginCode"])
col_destination = encontrar_coluna(df, ["DestinationCode"])
col_execution = encontrar_coluna(df, ["ExecutionDateTime"])
col_pieces = encontrar_coluna(df, ["PiecesCount", "No of Pieces"])
col_ops = encontrar_coluna(df, ["OPSStation"])
col_flt_no = encontrar_coluna(df, ["FltNo"])
col_flt_dt = encontrar_coluna(df, ["FltDt"])
col_flt_origin = encontrar_coluna(df, ["FltOrigin"])
col_flt_destination = encontrar_coluna(df, ["FltDestination"])
col_status = encontrar_coluna(df, ["StatusDescription"])
col_status_en = encontrar_coluna(df, ["StatusDescriptionEN"])
col_approx_sla = encontrar_coluna(df, ["ApproxSLA"])
col_billto = encontrar_coluna(df, ["BillTo"])
col_product = encontrar_coluna(df, ["ProductType"])
col_shipper = encontrar_coluna(df, ["Shipper"])
col_consignee = encontrar_coluna(df, ["Consignee"])
col_delivery_request = encontrar_coluna(df, ["DeliveryRequest"])
col_gross_wt = encontrar_coluna(df, ["GrossWt"])

obrigatorias = {
    "DestinationCode": col_destination,
    "ExecutionDateTime": col_execution,
    "OPSStation": col_ops,
    "StatusDescription": col_status,
    "ApproxSLA": col_approx_sla,
    "BillTo": col_billto,
}

faltantes = [nome for nome, col in obrigatorias.items() if col is None]
if faltantes:
    st.error("Não encontrei estas colunas obrigatórias: " + ", ".join(faltantes))
    st.write("Colunas encontradas na planilha:", list(df.columns))
    st.stop()


# ============================================================
# TRATAMENTO DA BASE
# ============================================================
df_work = df.copy()

# AWB completo
if col_awb_prefix and col_awb_number:
    df_work["AWB"] = df_work[col_awb_prefix].astype(str).str.zfill(3) + df_work[col_awb_number].astype(str).str.zfill(8)
elif col_awb_number:
    df_work["AWB"] = df_work[col_awb_number].astype(str)
else:
    df_work["AWB"] = df_work.index.astype(str)

# Datas
df_work["ExecutionDateTime_dt"] = pd.to_datetime(df_work[col_execution], errors="coerce")
df_work["ApproxSLA_dt"] = pd.to_datetime(df_work[col_approx_sla], errors="coerce")
if col_flt_dt:
    df_work["FltDt_dt"] = pd.to_datetime(df_work[col_flt_dt], errors="coerce")
else:
    df_work["FltDt_dt"] = pd.NaT

df_work = df_work.dropna(subset=["ExecutionDateTime_dt"])
if df_work.empty:
    st.warning("Nenhuma linha possui ExecutionDateTime válido.")
    st.stop()

# Campos calculados
df_work["Data Emissão"] = df_work["ExecutionDateTime_dt"].dt.date
df_work["Mês"] = df_work["ExecutionDateTime_dt"].dt.to_period("M").astype(str)
df_work["Dia Semana"] = df_work["ExecutionDateTime_dt"].dt.day_name(locale=None)
df_work["Status Grupo"] = df_work[col_status].apply(classificar_status)
df_work["Não finalizada"] = df_work["Status Grupo"].apply(status_nao_finalizado)
df_work["Carga no destino final"] = (
    df_work[col_destination].astype(str).str.strip().str.upper()
    == df_work[col_ops].astype(str).str.strip().str.upper()
)
df_work["Fora do destino"] = ~df_work["Carga no destino final"]
df_work["Aging Dias"] = (pd.Timestamp.now().normalize() - df_work["ExecutionDateTime_dt"].dt.normalize()).dt.days
df_work["Faixa Aging"] = df_work["Aging Dias"].apply(faixa_aging)
df_work["Risco SLA"] = df_work.apply(definir_risco, axis=1)

if col_gross_wt:
    df_work["Peso"] = pd.to_numeric(df_work[col_gross_wt], errors="coerce").fillna(0)
else:
    df_work["Peso"] = 0


# ============================================================
# FILTROS
# ============================================================
with st.sidebar:
    st.header("🔎 Filtros")

    clientes = sorted(df_work[col_billto].dropna().astype(str).unique())
    default_cliente_idx = 0
    for i, c in enumerate(clientes):
        if "TRES CORACOES" in c.upper():
            default_cliente_idx = i
            break

    cliente = st.selectbox("Cliente / BillTo", clientes, index=default_cliente_idx if clientes else 0)
    df_f = df_work[df_work[col_billto].astype(str) == str(cliente)].copy()

    min_data = df_f["Data Emissão"].min()
    max_data = df_f["Data Emissão"].max()
    periodo = st.date_input("Período de emissão", value=(min_data, max_data), min_value=min_data, max_value=max_data)
    if isinstance(periodo, tuple) and len(periodo) == 2:
        data_ini, data_fim = periodo
        df_f = df_f[(df_f["Data Emissão"] >= data_ini) & (df_f["Data Emissão"] <= data_fim)]

    destinos = ["Todos"] + sorted(df_f[col_destination].dropna().astype(str).unique())
    destino_sel = st.multiselect("DestinationCode", destinos, default=["Todos"])
    if destino_sel and "Todos" not in destino_sel:
        df_f = df_f[df_f[col_destination].astype(str).isin(destino_sel)]

    ops_options = ["Todos"] + sorted(df_f[col_ops].dropna().astype(str).unique())
    ops_sel = st.multiselect("OPSStation", ops_options, default=["Todos"])
    if ops_sel and "Todos" not in ops_sel:
        df_f = df_f[df_f[col_ops].astype(str).isin(ops_sel)]

    status_options = ["Todos"] + sorted(df_f["Status Grupo"].dropna().astype(str).unique())
    status_sel = st.multiselect("Status operacional", status_options, default=["Todos"])
    if status_sel and "Todos" not in status_sel:
        df_f = df_f[df_f["Status Grupo"].astype(str).isin(status_sel)]

    risco_options = ["Todos"] + sorted(df_f["Risco SLA"].dropna().astype(str).unique())
    risco_sel = st.multiselect("Risco SLA", risco_options, default=["Todos"])
    if risco_sel and "Todos" not in risco_sel:
        df_f = df_f[df_f["Risco SLA"].astype(str).isin(risco_sel)]

    if col_product:
        prod_options = ["Todos"] + sorted(df_f[col_product].dropna().astype(str).unique())
        prod_sel = st.multiselect("Produto", prod_options, default=["Todos"])
        if prod_sel and "Todos" not in prod_sel:
            df_f = df_f[df_f[col_product].astype(str).isin(prod_sel)]

if df_f.empty:
    st.warning("Nenhum dado encontrado para os filtros selecionados.")
    st.stop()


# ============================================================
# KPIs EXECUTIVOS
# ============================================================
st.markdown('<div class="section-title">1. Visão Executiva</div>', unsafe_allow_html=True)

total = len(df_f)
entregues = int((df_f["Status Grupo"] == "Entregue").sum())
nao_finalizadas = int(df_f["Não finalizada"].sum())
em_transito = int((df_f["Status Grupo"] == "Em trânsito").sum())
pendentes = int(df_f["Status Grupo"].str.contains("Pendente", na=False).sum())
fora_sla = int((df_f["Risco SLA"] == "Fora SLA").sum())
risco_24h = int((df_f["Risco SLA"] == "Risco 24h").sum())
fora_destino = int((df_f["Não finalizada"] & df_f["Fora do destino"]).sum())
aging_medio = df_f.loc[df_f["Não finalizada"], "Aging Dias"].mean()
peso_total = df_f["Peso"].sum()
sla_operacional = (1 - (fora_sla / nao_finalizadas)) * 100 if nao_finalizadas > 0 else 100.0

principal_ofensor = "-"
if nao_finalizadas > 0:
    ranking_tmp = df_f[df_f["Não finalizada"]].groupby(col_ops).size().sort_values(ascending=False)
    if not ranking_tmp.empty:
        principal_ofensor = str(ranking_tmp.index[0])

destino_critico = "-"
ranking_dest_tmp = df_f[df_f["Não finalizada"]].groupby(col_destination).size().sort_values(ascending=False)
if not ranking_dest_tmp.empty:
    destino_critico = str(ranking_dest_tmp.index[0])

c1, c2, c3, c4 = st.columns(4)
with c1:
    render_kpi("Total de emissões", format_int(total), "Quantidade de AWBs/peças no filtro")
with c2:
    render_kpi("SLA operacional estimado", format_pct(sla_operacional), "Base: cargas não entregues x ApproxSLA")
with c3:
    render_kpi("Cargas não finalizadas", format_int(nao_finalizadas), f"{format_int(em_transito)} em trânsito | {format_int(pendentes)} pendentes")
with c4:
    render_kpi("Fora SLA / Risco 24h", f"{format_int(fora_sla)} / {format_int(risco_24h)}", "Prioridade operacional")

c5, c6, c7, c8 = st.columns(4)
with c5:
    render_kpi("Entregues", format_int(entregues), f"{format_pct(entregues / total * 100 if total else 0)} da base filtrada")
with c6:
    render_kpi("Fora do destino final", format_int(fora_destino), "Cargas ainda em outra unidade")
with c7:
    render_kpi("Principal ofensor", principal_ofensor, "OPSStation com mais carga não finalizada")
with c8:
    render_kpi("Destino crítico", destino_critico, f"Aging médio: {format_float(aging_medio)} dias")

st.markdown(
    f"""
    <div class="insight-box">
        <b>Leitura executiva:</b> a base filtrada possui <b>{format_int(total)}</b> registros. 
        Existem <b>{format_int(nao_finalizadas)}</b> cargas ainda não finalizadas, sendo 
        <b>{format_int(fora_sla)}</b> fora do prazo estimado e <b>{format_int(fora_destino)}</b> ainda fora do destino final.
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# ABAS PRINCIPAIS
# ============================================================
aba_exec, aba_tracking, aba_sla, aba_ofensores, aba_detalhe = st.tabs(
    ["📊 Executivo", "🛰️ Tracking", "⏱️ SLA & Aging", "🔥 Ofensores", "📋 Base & Exportação"]
)


# ============================================================
# ABA EXECUTIVO
# ============================================================
with aba_exec:
    st.markdown('<div class="section-title">2. Volume Operacional</div>', unsafe_allow_html=True)

    col_a, col_b = st.columns(2)

    with col_a:
        emissao_dia = df_f.groupby("Data Emissão").size().reset_index(name="Emissões")
        fig = px.line(
            emissao_dia,
            x="Data Emissão",
            y="Emissões",
            markers=True,
            title="Emissões por dia",
        )
        fig.update_layout(height=390, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        destino_vol = (
            df_f.groupby(col_destination)
            .size()
            .reset_index(name="Emissões")
            .sort_values("Emissões", ascending=False)
            .head(15)
        )
        fig = px.bar(
            destino_vol,
            x="Emissões",
            y=col_destination,
            orientation="h",
            title="Top destinos por volume",
            text="Emissões",
        )
        fig.update_layout(height=390, yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    col_c, col_d = st.columns(2)

    with col_c:
        status_dist = df_f.groupby("Status Grupo").size().reset_index(name="Quantidade")
        fig = px.pie(
            status_dist,
            values="Quantidade",
            names="Status Grupo",
            hole=0.55,
            title="Distribuição operacional por status",
        )
        fig.update_layout(height=390, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_d:
        if col_product:
            produto_vol = df_f.groupby(col_product).size().reset_index(name="Quantidade").sort_values("Quantidade", ascending=False)
            fig = px.bar(produto_vol, x=col_product, y="Quantidade", title="Volume por produto", text="Quantidade")
            fig.update_layout(height=390, xaxis_tickangle=-25, margin=dict(l=20, r=20, t=55, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Coluna ProductType não encontrada.")


# ============================================================
# ABA TRACKING
# ============================================================
with aba_tracking:
    st.markdown('<div class="section-title">3. Tracking Operacional</div>', unsafe_allow_html=True)

    df_aberto = df_f[df_f["Não finalizada"]].copy()

    c1, c2 = st.columns(2)

    with c1:
        paradas_ops = (
            df_aberto.groupby(col_ops)
            .agg(Quantidade=("AWB", "count"), Aging_Medio=("Aging Dias", "mean"))
            .reset_index()
            .sort_values("Quantidade", ascending=False)
            .head(20)
        )
        fig = px.bar(
            paradas_ops,
            x="Quantidade",
            y=col_ops,
            orientation="h",
            title="Onde as cargas não finalizadas estão agora",
            text="Quantidade",
            hover_data={"Aging_Medio": ":.1f"},
        )
        fig.update_layout(height=430, yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        destino_ops = (
            df_aberto.groupby([col_destination, col_ops])
            .size()
            .reset_index(name="Quantidade")
            .sort_values("Quantidade", ascending=False)
            .head(40)
        )
        if not destino_ops.empty:
            fig = px.density_heatmap(
                destino_ops,
                x=col_ops,
                y=col_destination,
                z="Quantidade",
                title="Matriz operacional: DestinationCode x OPSStation",
                text_auto=True,
            )
            fig.update_layout(height=430, margin=dict(l=20, r=20, t=55, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Não há cargas não finalizadas para montar a matriz.")

    st.markdown('<div class="section-title">Fluxo operacional detalhado</div>', unsafe_allow_html=True)

    if col_origin:
        fluxo_base = df_aberto.copy()
        fluxo_base["Origem"] = fluxo_base[col_origin].astype(str).str.strip().str.upper()
        fluxo_base["Unidade Atual"] = fluxo_base[col_ops].astype(str).str.strip().str.upper()
        fluxo_base["Destino"] = fluxo_base[col_destination].astype(str).str.strip().str.upper()
        fluxo_base["Fluxo"] = (
            fluxo_base["Origem"] + " → " + fluxo_base["Unidade Atual"] + " → " + fluxo_base["Destino"]
        )

        fluxo_detalhado = (
            fluxo_base.groupby(["Origem", "Unidade Atual", "Destino", "Fluxo"])
            .agg(
                Qtde_AWBs=("AWB", "count"),
                Fora_SLA=("Risco SLA", lambda s: (s == "Fora SLA").sum()),
                Risco_24h=("Risco SLA", lambda s: (s == "Risco 24h").sum()),
                Aging_Medio_Dias=("Aging Dias", "mean"),
                Peso_Total=("Peso", "sum"),
                Status_Mais_Comum=("Status Grupo", lambda s: s.mode().iloc[0] if not s.mode().empty else "-"),
            )
            .reset_index()
            .sort_values(["Qtde_AWBs", "Fora_SLA", "Aging_Medio_Dias"], ascending=False)
        )

        if not fluxo_detalhado.empty:
            fluxo_detalhado["% do Total"] = (fluxo_detalhado["Qtde_AWBs"] / fluxo_detalhado["Qtde_AWBs"].sum()) * 100
            fluxo_detalhado["Aging_Medio_Dias"] = fluxo_detalhado["Aging_Medio_Dias"].round(1)
            fluxo_detalhado["% do Total"] = fluxo_detalhado["% do Total"].round(1)
            fluxo_detalhado["Peso_Total"] = fluxo_detalhado["Peso_Total"].round(2)

            total_fluxos = len(fluxo_detalhado)
            maior_fluxo = fluxo_detalhado.iloc[0]
            fluxos_fora_sla = int((fluxo_detalhado["Fora_SLA"] > 0).sum())
            aging_fluxo_medio = fluxo_detalhado["Aging_Medio_Dias"].mean()

            f1, f2, f3, f4 = st.columns(4)
            with f1:
                render_kpi("Fluxos únicos", format_int(total_fluxos), "Origem → Unidade atual → Destino")
            with f2:
                render_kpi("Maior fluxo", str(maior_fluxo["Fluxo"]), f"{format_int(maior_fluxo['Qtde_AWBs'])} AWBs")
            with f3:
                render_kpi("Fluxos com fora SLA", format_int(fluxos_fora_sla), "Fluxos que precisam de atenção")
            with f4:
                render_kpi("Aging médio dos fluxos", f"{format_float(aging_fluxo_medio)} dias", "Base: cargas não finalizadas")

            st.markdown(
                """
                <div class="insight-box">
                    <b>Leitura do fluxo:</b> esta visão substitui o Sankey para manter todas as informações,
                    porém em um formato mais limpo, filtrável e útil para tomada de decisão operacional.
                    Use o ranking para ver os maiores fluxos e a tabela para investigar todos os caminhos da carga.
                </div>
                """,
                unsafe_allow_html=True,
            )

            c_fluxo1, c_fluxo2 = st.columns(2)

            with c_fluxo1:
                top_fluxos = fluxo_detalhado.head(20).copy()
                fig = px.bar(
                    top_fluxos.sort_values("Qtde_AWBs", ascending=True),
                    x="Qtde_AWBs",
                    y="Fluxo",
                    orientation="h",
                    title="Top 20 fluxos operacionais por volume",
                    text="Qtde_AWBs",
                    hover_data=["Fora_SLA", "Risco_24h", "Aging_Medio_Dias", "Status_Mais_Comum"],
                )
                fig.update_layout(height=620, margin=dict(l=20, r=20, t=55, b=20))
                st.plotly_chart(fig, use_container_width=True)

            with c_fluxo2:
                top_criticos = fluxo_detalhado.sort_values(
                    ["Fora_SLA", "Risco_24h", "Aging_Medio_Dias", "Qtde_AWBs"],
                    ascending=False,
                ).head(20)
                fig = px.scatter(
                    top_criticos,
                    x="Qtde_AWBs",
                    y="Aging_Medio_Dias",
                    size="Fora_SLA",
                    hover_name="Fluxo",
                    hover_data=["Risco_24h", "Status_Mais_Comum", "% do Total"],
                    title="Fluxos críticos: volume x aging x fora SLA",
                )
                fig.update_layout(height=620, margin=dict(l=20, r=20, t=55, b=20))
                st.plotly_chart(fig, use_container_width=True)

            st.subheader("Matriz de fluxo: Unidade atual x Destino")
            matriz_fluxo = (
                fluxo_base.groupby(["Unidade Atual", "Destino"])
                .size()
                .reset_index(name="Quantidade")
                .sort_values("Quantidade", ascending=False)
            )
            if not matriz_fluxo.empty:
                top_unidades = matriz_fluxo.groupby("Unidade Atual")["Quantidade"].sum().nlargest(25).index
                top_destinos = matriz_fluxo.groupby("Destino")["Quantidade"].sum().nlargest(25).index
                matriz_plot = matriz_fluxo[
                    matriz_fluxo["Unidade Atual"].isin(top_unidades) & matriz_fluxo["Destino"].isin(top_destinos)
                ]
                fig = px.density_heatmap(
                    matriz_plot,
                    x="Unidade Atual",
                    y="Destino",
                    z="Quantidade",
                    title="Heatmap operacional — onde a carga está x para onde deveria ir",
                    text_auto=True,
                )
                fig.update_layout(height=620, margin=dict(l=20, r=20, t=55, b=20))
                st.plotly_chart(fig, use_container_width=True)

            st.subheader("Tabela completa de fluxo operacional")
            st.dataframe(
                fluxo_detalhado[
                    [
                        "Origem",
                        "Unidade Atual",
                        "Destino",
                        "Fluxo",
                        "Qtde_AWBs",
                        "% do Total",
                        "Fora_SLA",
                        "Risco_24h",
                        "Aging_Medio_Dias",
                        "Peso_Total",
                        "Status_Mais_Comum",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            fluxo_excel = gerar_excel(fluxo_detalhado)
            st.download_button(
                label="📥 Baixar fluxo operacional em Excel",
                data=fluxo_excel,
                file_name="fluxo_operacional_detalhado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.info("Não há cargas não finalizadas para montar o fluxo operacional detalhado.")
    else:
        st.info("Para montar o fluxo operacional completo, a coluna OriginCode precisa estar disponível.")

# ============================================================
# ABA SLA & AGING
# ============================================================
with aba_sla:
    st.markdown('<div class="section-title">4. SLA, Risco e Aging</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        risco = df_f.groupby("Risco SLA").size().reset_index(name="Quantidade").sort_values("Quantidade", ascending=False)
        fig = px.bar(risco, x="Risco SLA", y="Quantidade", title="Distribuição de risco SLA", text="Quantidade")
        fig.update_layout(height=390, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        aging = (
            df_f[df_f["Não finalizada"]]
            .groupby("Faixa Aging")
            .size()
            .reset_index(name="Quantidade")
        )
        ordem = ["0-24h", "24-48h", "48-72h", ">72h", "Sem data"]
        aging["ordem"] = aging["Faixa Aging"].apply(lambda x: ordem.index(x) if x in ordem else 99)
        aging = aging.sort_values("ordem")
        fig = px.bar(aging, x="Faixa Aging", y="Quantidade", title="Aging de cargas não finalizadas", text="Quantidade")
        fig.update_layout(height=390, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    c3, c4 = st.columns(2)

    with c3:
        evolucao = (
            df_f.groupby("Data Emissão")
            .agg(Total=("AWB", "count"), Fora_SLA=("Risco SLA", lambda s: (s == "Fora SLA").sum()))
            .reset_index()
        )
        evolucao["SLA Estimado %"] = (1 - evolucao["Fora_SLA"] / evolucao["Total"].replace(0, pd.NA)) * 100
        fig = px.line(
            evolucao,
            x="Data Emissão",
            y="SLA Estimado %",
            markers=True,
            title="Evolução do SLA estimado por dia",
        )
        fig.update_yaxes(range=[0, 105])
        fig.update_layout(height=390, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        sla_dest = (
            df_f.groupby(col_destination)
            .agg(Total=("AWB", "count"), Fora_SLA=("Risco SLA", lambda s: (s == "Fora SLA").sum()))
            .reset_index()
        )
        sla_dest["SLA Estimado %"] = (1 - sla_dest["Fora_SLA"] / sla_dest["Total"].replace(0, pd.NA)) * 100
        sla_dest = sla_dest.sort_values("SLA Estimado %", ascending=True).head(15)
        fig = px.bar(
            sla_dest,
            x="SLA Estimado %",
            y=col_destination,
            orientation="h",
            title="SLA estimado por destino - piores destinos",
            text=sla_dest["SLA Estimado %"].round(1),
            hover_data=["Total", "Fora_SLA"],
        )
        fig.update_xaxes(range=[0, 105])
        fig.update_layout(height=390, yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# ABA OFENSORES
# ============================================================
with aba_ofensores:
    st.markdown('<div class="section-title">5. Ranking de Ofensores</div>', unsafe_allow_html=True)

    df_aberto = df_f[df_f["Não finalizada"]].copy()

    rank_ops = (
        df_aberto.groupby(col_ops)
        .agg(
            Cargas=("AWB", "count"),
            Fora_SLA=("Risco SLA", lambda s: (s == "Fora SLA").sum()),
            Risco_24h=("Risco SLA", lambda s: (s == "Risco 24h").sum()),
            Fora_Destino=("Fora do destino", "sum"),
            Aging_Medio=("Aging Dias", "mean"),
            Peso_Total=("Peso", "sum"),
        )
        .reset_index()
        .sort_values(["Fora_SLA", "Cargas"], ascending=False)
    )

    rank_dest = (
        df_aberto.groupby(col_destination)
        .agg(
            Cargas=("AWB", "count"),
            Fora_SLA=("Risco SLA", lambda s: (s == "Fora SLA").sum()),
            Risco_24h=("Risco SLA", lambda s: (s == "Risco 24h").sum()),
            Aging_Medio=("Aging Dias", "mean"),
            Peso_Total=("Peso", "sum"),
        )
        .reset_index()
        .sort_values(["Fora_SLA", "Cargas"], ascending=False)
    )

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("OPSStation ofensora")
        st.dataframe(rank_ops, use_container_width=True, hide_index=True)

    with c2:
        st.subheader("DestinationCode crítico")
        st.dataframe(rank_dest, use_container_width=True, hide_index=True)

    c3, c4 = st.columns(2)

    with c3:
        fig = px.bar(rank_ops.head(15), x="Fora_SLA", y=col_ops, orientation="h", title="Top OPSStation por fora SLA", text="Fora_SLA")
        fig.update_layout(height=420, yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with c4:
        fig = px.bar(rank_dest.head(15), x="Fora_SLA", y=col_destination, orientation="h", title="Top destinos por fora SLA", text="Fora_SLA")
        fig.update_layout(height=420, yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-title">AWBs prioritárias</div>', unsafe_allow_html=True)
    prioridade = df_f[df_f["Risco SLA"].isin(["Fora SLA", "Risco 24h"])].copy()
    prioridade = prioridade.sort_values(["Risco SLA", "Aging Dias"], ascending=[True, False])
    cols_prioridade = [
        "AWB",
        col_origin,
        col_destination,
        col_ops,
        col_status,
        "Status Grupo",
        "Risco SLA",
        "ExecutionDateTime_dt",
        "ApproxSLA_dt",
        "Aging Dias",
        "Peso",
    ]
    cols_prioridade = [c for c in cols_prioridade if c is not None and c in prioridade.columns]
    st.dataframe(prioridade[cols_prioridade], use_container_width=True, hide_index=True)


# ============================================================
# ABA BASE E EXPORTAÇÃO
# ============================================================
with aba_detalhe:
    st.markdown('<div class="section-title">6. Base filtrada e exportação</div>', unsafe_allow_html=True)

    colunas_exibir = [
        "AWB",
        col_origin,
        col_destination,
        col_ops,
        col_status,
        col_status_en,
        "Status Grupo",
        "Risco SLA",
        col_billto,
        col_product,
        col_delivery_request,
        "ExecutionDateTime_dt",
        "ApproxSLA_dt",
        col_flt_no,
        "FltDt_dt",
        col_flt_origin,
        col_flt_destination,
        "Aging Dias",
        "Faixa Aging",
        "Carga no destino final",
        "Peso",
        col_shipper,
        col_consignee,
    ]
    colunas_exibir = [c for c in colunas_exibir if c is not None and c in df_f.columns]

    st.dataframe(df_f[colunas_exibir], use_container_width=True, hide_index=True)

    excel_bytes = gerar_excel(df_f[colunas_exibir])
    st.download_button(
        label="📥 Baixar base filtrada em Excel",
        data=excel_bytes,
        file_name="base_filtrada_performance_awb.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    csv_bytes = df_f[colunas_exibir].to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        label="📥 Baixar base filtrada em CSV",
        data=csv_bytes,
        file_name="base_filtrada_performance_awb.csv",
        mime="text/csv",
    )

    with st.expander("🔧 Diagnóstico das colunas lidas"):
        st.write("Colunas encontradas:", list(df.columns))
        st.write(
            {
                "AWBPrefix": col_awb_prefix,
                "AWBNumber": col_awb_number,
                "OriginCode": col_origin,
                "DestinationCode": col_destination,
                "ExecutionDateTime": col_execution,
                "OPSStation": col_ops,
                "StatusDescription": col_status,
                "StatusDescriptionEN": col_status_en,
                "ApproxSLA": col_approx_sla,
                "BillTo": col_billto,
                "ProductType": col_product,
                "GrossWt": col_gross_wt,
            }
        )


# ============================================================
# RODAPÉ
# ============================================================
st.caption(
    "Dashboard desenvolvida para análise operacional: emissões, tracking, SLA, aging, ofensores e fluxo DestinationCode x OPSStation."
)
