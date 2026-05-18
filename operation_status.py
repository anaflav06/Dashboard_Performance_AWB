from __future__ import annotations

from io import BytesIO
import re
import unicodedata

import pandas as pd
import plotly.express as px
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
        overflow-wrap: anywhere;
    }
    .kpi-title { color: #627084; font-size: 13px; font-weight: 700; margin-bottom: 8px; }
    .kpi-value { color: #003B71; font-size: 25px; font-weight: 900; line-height: 1.1; }
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


def format_int(valor: float | int | None) -> str:
    try:
        if valor is None or pd.isna(valor):
            return "0"
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


def limpar_awb(valor: object, remover_prefixo_577: bool = True) -> str:
    """Normaliza AWB para comparação entre bases.
    Ex.: 57798194235 -> 98194235 | 98194235.0 -> 98194235
    """
    if pd.isna(valor):
        return ""
    txt = str(valor).strip()
    txt = re.sub(r"\.0$", "", txt)
    txt = re.sub(r"\D", "", txt)
    if remover_prefixo_577 and txt.startswith("577") and len(txt) > 8:
        txt = txt[3:]
    return txt.zfill(8) if txt else ""


def limpar_awb_completa(valor: object) -> str:
    if pd.isna(valor):
        return ""
    txt = str(valor).strip()
    txt = re.sub(r"\.0$", "", txt)
    txt = re.sub(r"\D", "", txt)
    return txt


def classificar_status(valor: object) -> str:
    txt = norm_txt(valor)
    if any(x in txt for x in ["entregue", "delivered"]):
        return "Entregue"
    if any(x in txt for x in ["pendente entrega", "out for delivery", "saiu para entrega"]):
        return "Pendente entrega"
    if any(x in txt for x in ["pendente embarque", "accepted", "aguardando embarque"]):
        return "Pendente embarque"
    if any(x in txt for x in ["transito", "transferencia", "transferido", "manifestado", "voo", "rota", "route"]):
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


def definir_risco_estimado(row: pd.Series) -> str:
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


def classificar_prazo_real(row: pd.Series) -> str:
    data_prevista = row.get("Data Prevista Entrega")
    data_entrega = row.get("Data Real Entrega")
    if pd.isna(data_prevista):
        return "Sem data prevista"
    if pd.isna(data_entrega):
        return "Sem entrega"
    if data_entrega.normalize() <= data_prevista.normalize():
        return "Dentro do prazo"
    return "Fora do prazo"


def detectar_ocorrencia(row: pd.Series, cols: list[str]) -> str:
    texto = " ".join(str(row.get(c, "")) for c in cols if c in row.index)
    texto_n = norm_txt(texto)

    achados = []
    if any(x in texto_n for x in ["avaria", "damaged", "damage"]):
        achados.append("Avaria")
    if any(x in texto_n for x in ["extravio", "loss", "lost", "perda"]):
        achados.append("Extravio")
    if "msca" in texto_n:
        achados.append("MSCA")
    if any(x in texto_n for x in ["found", "localizada", "localizado", "carga localizada"]):
        achados.append("FOUND / Carga localizada")
    return " | ".join(dict.fromkeys(achados)) if achados else "Sem ocorrência crítica"


def gerar_excel_abas(abas: dict[str, pd.DataFrame]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#003B71", "font_color": "white", "border": 1})
        for nome_aba, df_export in abas.items():
            safe_name = nome_aba[:31]
            df_export.to_excel(writer, sheet_name=safe_name, index=False)
            worksheet = writer.sheets[safe_name]
            for col_num, value in enumerate(df_export.columns.values):
                worksheet.write(0, col_num, value, header_fmt)
                worksheet.set_column(col_num, col_num, min(max(len(str(value)) + 2, 12), 38))
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
        <p>Torre de controle operacional com duas bases: tracking operacional + entrega real, SLA, ocorrências críticas e fluxo entre unidades.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# UPLOAD DAS DUAS PLANILHAS
# ============================================================
with st.sidebar:
    st.header("📁 Arquivos")
    arquivo_operacao = st.file_uploader(
        "1) Planilha Operation Status / AWBStatusAtPieceLevel",
        type=["xlsx", "xls", "csv"],
        key="operacao",
    )
    arquivo_comissao = st.file_uploader(
        "2) Planilha Commission Report Franchise",
        type=["xlsx", "xls", "csv"],
        key="comissao",
    )

if arquivo_operacao is None:
    st.info("Carregue a planilha Operation Status para iniciar a análise.")
    st.stop()

try:
    df = carregar_arquivo(arquivo_operacao)
except Exception as exc:
    st.error(f"Erro ao ler a planilha Operation Status: {exc}")
    st.stop()

if df.empty:
    st.warning("A planilha Operation Status está vazia.")
    st.stop()

# Segunda planilha é opcional para permitir uso parcial, mas ativa o SLA real quando carregada.
df_comm = None
if arquivo_comissao is not None:
    try:
        df_comm = carregar_arquivo(arquivo_comissao)
    except Exception as exc:
        st.error(f"Erro ao ler a planilha Commission Report Franchise: {exc}")
        st.stop()


# ============================================================
# MAPEAMENTO DA PLANILHA 1 - OPERATION STATUS
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
    st.error("Não encontrei estas colunas obrigatórias na Operation Status: " + ", ".join(faltantes))
    st.write("Colunas encontradas na planilha:", list(df.columns))
    st.stop()


# ============================================================
# TRATAMENTO DA BASE 1
# ============================================================
df_work = df.copy()

if col_awb_prefix and col_awb_number:
    df_work["AWB"] = (
        df_work[col_awb_prefix].apply(limpar_awb_completa).str.zfill(3)
        + df_work[col_awb_number].apply(limpar_awb).str.zfill(8)
    )
    df_work["AWB_MATCH"] = df_work[col_awb_number].apply(limpar_awb)
elif col_awb_number:
    df_work["AWB"] = df_work[col_awb_number].apply(limpar_awb_completa)
    df_work["AWB_MATCH"] = df_work[col_awb_number].apply(limpar_awb)
else:
    df_work["AWB"] = df_work.index.astype(str)
    df_work["AWB_MATCH"] = df_work.index.astype(str)

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
df_work["Risco SLA Estimado"] = df_work.apply(definir_risco_estimado, axis=1)
# Mantém compatibilidade com gráficos antigos.
df_work["Risco SLA"] = df_work["Risco SLA Estimado"]

if col_gross_wt:
    df_work["Peso"] = pd.to_numeric(df_work[col_gross_wt], errors="coerce").fillna(0)
else:
    df_work["Peso"] = 0


# ============================================================
# TRATAMENTO DA BASE 2 - COMMISSION REPORT
# ============================================================
tem_commission = df_comm is not None and not df_comm.empty
col_comm_awb = col_comm_data_prev = col_comm_entrega = col_comm_dest = None
col_comm_peso_taxado = col_comm_total = col_comm_entregaprazo = None
cols_ocorrencia: list[str] = []

if tem_commission:
    col_comm_awb = encontrar_coluna(df_comm, ["AWB", "AWB_CONSULTA"])
    col_comm_data_prev = encontrar_coluna(df_comm, ["DATA"])
    col_comm_entrega = encontrar_coluna(df_comm, ["ENTREGA"])
    col_comm_dest = encontrar_coluna(df_comm, ["UNIDADEDESTINO"])
    col_comm_peso_taxado = encontrar_coluna(df_comm, ["PESOTAXADO"])
    col_comm_total = encontrar_coluna(df_comm, ["TOTAL"])
    col_comm_entregaprazo = encontrar_coluna(df_comm, ["ENTREGAPRAZO"])

    for opcao in [
        "OCORRENCIA_01", "OCORRENCIA_02", "OCORRENCIA_03",
        "COMENTARIO_01", "COMENTARIO_02", "COMENTARIO_03",
    ]:
        c = encontrar_coluna(df_comm, [opcao])
        if c:
            cols_ocorrencia.append(c)

    faltantes_comm = [
        nome for nome, col in {
            "AWB": col_comm_awb,
            "DATA": col_comm_data_prev,
            "ENTREGA": col_comm_entrega,
        }.items() if col is None
    ]
    if faltantes_comm:
        st.error("Não encontrei estas colunas obrigatórias na Commission Report: " + ", ".join(faltantes_comm))
        st.write("Colunas encontradas na Commission Report:", list(df_comm.columns))
        st.stop()

    df_comm_work = df_comm.copy()
    df_comm_work["AWB_COMPLETA_COMMISSION"] = df_comm_work[col_comm_awb].apply(limpar_awb_completa)
    df_comm_work["AWB_MATCH"] = df_comm_work[col_comm_awb].apply(limpar_awb)
    df_comm_work["Data Prevista Entrega"] = pd.to_datetime(df_comm_work[col_comm_data_prev], errors="coerce", dayfirst=True)
    df_comm_work["Data Real Entrega"] = pd.to_datetime(df_comm_work[col_comm_entrega], errors="coerce", dayfirst=True)
    df_comm_work["Status Prazo Real"] = df_comm_work.apply(classificar_prazo_real, axis=1)
    df_comm_work["Ocorrência Especial"] = df_comm_work.apply(lambda r: detectar_ocorrencia(r, cols_ocorrencia), axis=1)

    if col_comm_peso_taxado:
        df_comm_work["Peso Taxado"] = pd.to_numeric(df_comm_work[col_comm_peso_taxado], errors="coerce").fillna(0)
    else:
        df_comm_work["Peso Taxado"] = 0

    if col_comm_total:
        df_comm_work["Total Frete"] = pd.to_numeric(df_comm_work[col_comm_total], errors="coerce").fillna(0)
    else:
        df_comm_work["Total Frete"] = 0

    # Reduz para 1 linha por AWB_MATCH para evitar duplicidade no merge.
    agg_dict = {
        "AWB_COMPLETA_COMMISSION": "first",
        "Data Prevista Entrega": "min",
        "Data Real Entrega": "min",
        "Status Prazo Real": lambda s: s.mode().iloc[0] if not s.mode().empty else "-",
        "Ocorrência Especial": lambda s: " | ".join(sorted(set(x for x in s.astype(str) if x and x != "Sem ocorrência crítica"))) or "Sem ocorrência crítica",
        "Peso Taxado": "sum",
        "Total Frete": "sum",
    }
    if col_comm_dest:
        df_comm_work["Unidade Destino Commission"] = df_comm_work[col_comm_dest].astype(str)
        agg_dict["Unidade Destino Commission"] = "first"
    if col_comm_entregaprazo:
        df_comm_work["Entrega Prazo Dias"] = pd.to_numeric(df_comm_work[col_comm_entregaprazo], errors="coerce")
        agg_dict["Entrega Prazo Dias"] = "max"

    for c in cols_ocorrencia:
        agg_dict[c] = lambda s: " | ".join(sorted(set(str(x) for x in s.dropna().astype(str) if str(x).strip())))

    df_comm_reduzida = df_comm_work.groupby("AWB_MATCH", as_index=False).agg(agg_dict)
    df_work = df_work.merge(df_comm_reduzida, on="AWB_MATCH", how="left")
    df_work["Encontrada na Commission"] = df_work["AWB_COMPLETA_COMMISSION"].notna()
    df_work["Status Prazo Real"] = df_work["Status Prazo Real"].fillna("Sem dados Commission")
    df_work["Ocorrência Especial"] = df_work["Ocorrência Especial"].fillna("Sem dados Commission")
    df_work["Peso Taxado"] = df_work["Peso Taxado"].fillna(0)
    df_work["Total Frete"] = df_work["Total Frete"].fillna(0)

    # Se existe SLA real, usa este como visão principal de SLA.
    df_work["Risco SLA"] = df_work["Status Prazo Real"].replace(
        {"Dentro do prazo": "Dentro do prazo", "Fora do prazo": "Fora SLA", "Sem entrega": "Sem entrega"}
    )
else:
    df_work["Encontrada na Commission"] = False
    df_work["AWB_COMPLETA_COMMISSION"] = ""
    df_work["Data Prevista Entrega"] = pd.NaT
    df_work["Data Real Entrega"] = pd.NaT
    df_work["Status Prazo Real"] = "Sem dados Commission"
    df_work["Ocorrência Especial"] = "Sem dados Commission"
    df_work["Peso Taxado"] = 0
    df_work["Total Frete"] = 0


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
    periodo = st.date_input(
        "Período de emissão",
        value=(min_data, max_data),
        min_value=min_data,
        max_value=max_data,
        format="DD/MM/YYYY",
    )
    if isinstance(periodo, tuple) and len(periodo) == 2:
        data_ini, data_fim = periodo
        df_f = df_f[(df_f["Data Emissão"] >= data_ini) & (df_f["Data Emissão"] <= data_fim)]
        st.caption(f"Período selecionado: {data_ini.strftime('%d/%m/%Y')} - {data_fim.strftime('%d/%m/%Y')}")

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
    risco_sel = st.multiselect("SLA / Prazo", risco_options, default=["Todos"])
    if risco_sel and "Todos" not in risco_sel:
        df_f = df_f[df_f["Risco SLA"].astype(str).isin(risco_sel)]

    ocorr_options = ["Todos"] + sorted(df_f["Ocorrência Especial"].dropna().astype(str).unique())
    ocorr_sel = st.multiselect("Ocorrência especial", ocorr_options, default=["Todos"])
    if ocorr_sel and "Todos" not in ocorr_sel:
        df_f = df_f[df_f["Ocorrência Especial"].astype(str).isin(ocorr_sel)]

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
entregues_operacao = int((df_f["Status Grupo"] == "Entregue").sum())
nao_finalizadas = int(df_f["Não finalizada"].sum())
em_transito = int((df_f["Status Grupo"] == "Em trânsito").sum())
pendentes = int(df_f["Status Grupo"].str.contains("Pendente", na=False).sum())
fora_sla = int((df_f["Risco SLA"] == "Fora SLA").sum())
risco_24h = int((df_f["Risco SLA"] == "Risco 24h").sum())
sem_entrega = int((df_f["Status Prazo Real"] == "Sem entrega").sum())
fora_destino = int((df_f["Não finalizada"] & df_f["Fora do destino"]).sum())
aging_medio = df_f.loc[df_f["Não finalizada"], "Aging Dias"].mean()
peso_total = df_f["Peso"].sum()
com_match = int(df_f["Encontrada na Commission"].sum())

base_sla_real = df_f[df_f["Status Prazo Real"].isin(["Dentro do prazo", "Fora do prazo"])]
dentro_prazo = int((df_f["Status Prazo Real"] == "Dentro do prazo").sum())
fora_prazo = int((df_f["Status Prazo Real"] == "Fora do prazo").sum())
sla_real = dentro_prazo / len(base_sla_real) * 100 if len(base_sla_real) else None

avarias = int(df_f["Ocorrência Especial"].str.contains("Avaria", na=False).sum())
extravios = int(df_f["Ocorrência Especial"].str.contains("Extravio", na=False).sum())
msca = int(df_f["Ocorrência Especial"].str.contains("MSCA", na=False).sum())
found = int(df_f["Ocorrência Especial"].str.contains("FOUND|localizada", case=False, na=False).sum())

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
    render_kpi("SLA real", format_pct(sla_real), "Base: DATA prevista x ENTREGA")
with c3:
    render_kpi("Dentro / Fora prazo", f"{format_int(dentro_prazo)} / {format_int(fora_prazo)}", "Entrega oficial Commission")
with c4:
    render_kpi("Sem entrega oficial", format_int(sem_entrega), "AWBs sem data de entrega")

c5, c6, c7, c8 = st.columns(4)
with c5:
    render_kpi("Cargas não finalizadas", format_int(nao_finalizadas), f"{format_int(em_transito)} em trânsito | {format_int(pendentes)} pendentes")
with c6:
    render_kpi("Fora do destino final", format_int(fora_destino), "Cargas ainda em outra unidade")
with c7:
    render_kpi("Avaria / Extravio", f"{format_int(avarias)} / {format_int(extravios)}", "Ocorrências críticas")
with c8:
    render_kpi("MSCA / FOUND", f"{format_int(msca)} / {format_int(found)}", "Carga localizada ou ocorrência MSCA")

c9, c10, c11, c12 = st.columns(4)
with c9:
    render_kpi("Match entre planilhas", f"{format_int(com_match)} / {format_int(total)}", "AWB com 577 removido para cruzamento")
with c10:
    render_kpi("Principal ofensor", principal_ofensor, "OPSStation com mais carga não finalizada")
with c11:
    render_kpi("Destino crítico", destino_critico, f"Aging médio: {format_float(aging_medio)} dias")
with c12:
    render_kpi("Total financeiro", f"R$ {format_float(df_f['Total Frete'].sum(), 2)}", "Soma TOTAL da Commission")

st.markdown(
    f"""
    <div class="insight-box">
        <b>Leitura executiva:</b> a base filtrada possui <b>{format_int(total)}</b> registros. 
        A dashboard encontrou <b>{format_int(com_match)}</b> AWBs na segunda planilha usando a chave sem o prefixo 577.
        No SLA real, existem <b>{format_int(dentro_prazo)}</b> entregas dentro do prazo, 
        <b>{format_int(fora_prazo)}</b> fora do prazo e <b>{format_int(sem_entrega)}</b> sem entrega oficial.
    </div>
    """,
    unsafe_allow_html=True,
)

# Download rápido dos registros que alimentam os KPIs da visão executiva
colunas_download_kpi = [
    "AWB", "AWB_MATCH", "AWB_COMPLETA_COMMISSION", "Encontrada na Commission",
    col_origin, col_destination, col_ops, col_status, col_status_en,
    "Status Grupo", "Risco SLA", "Risco SLA Estimado", "Status Prazo Real", "Ocorrência Especial",
    col_billto, col_product, col_delivery_request,
    "ExecutionDateTime_dt", "ApproxSLA_dt", "Data Prevista Entrega", "Data Real Entrega",
    col_flt_no, "FltDt_dt", col_flt_origin, col_flt_destination,
    "Aging Dias", "Faixa Aging", "Carga no destino final", "Peso", "Peso Taxado", "Total Frete",
    col_shipper, col_consignee,
]
colunas_download_kpi += [c for c in cols_ocorrencia if c in df_f.columns]
colunas_download_kpi = [c for c in colunas_download_kpi if c is not None and c in df_f.columns]

excel_kpis_bytes = gerar_excel_abas({"Registros Filtrados": df_f[colunas_download_kpi].copy()})
st.download_button(
    label=f"📥 Baixar os {format_int(total)} registros desta análise",
    data=excel_kpis_bytes,
    file_name="registros_filtrados_visao_executiva.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)


# ============================================================
# ABAS PRINCIPAIS
# ============================================================
aba_exec, aba_tracking, aba_sla, aba_ocorrencias, aba_ofensores, aba_detalhe = st.tabs(
    ["📊 Executivo", "🛰️ Tracking", "⏱️ SLA Real & Aging", "🚨 Ocorrências", "🔥 Ofensores", "📋 Base & Exportação"]
)


# ============================================================
# ABA EXECUTIVO
# ============================================================
with aba_exec:
    st.markdown('<div class="section-title">2. Volume Operacional</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)

    with col_a:
        emissao_dia = df_f.groupby("Data Emissão").size().reset_index(name="Emissões")
        fig = px.line(emissao_dia, x="Data Emissão", y="Emissões", markers=True, title="Emissões por dia")
        fig.update_layout(height=390, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        destino_vol = df_f.groupby(col_destination).size().reset_index(name="Emissões").sort_values("Emissões", ascending=False).head(15)
        fig = px.bar(destino_vol, x="Emissões", y=col_destination, orientation="h", title="Top destinos por volume", text="Emissões")
        fig.update_layout(height=390, yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    col_c, col_d = st.columns(2)
    with col_c:
        status_dist = df_f.groupby("Status Grupo").size().reset_index(name="Quantidade")
        fig = px.pie(status_dist, values="Quantidade", names="Status Grupo", hole=0.55, title="Distribuição operacional por status")
        fig.update_layout(height=390, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_d:
        prazo_dist = df_f.groupby("Status Prazo Real").size().reset_index(name="Quantidade").sort_values("Quantidade", ascending=False)
        fig = px.bar(prazo_dist, x="Status Prazo Real", y="Quantidade", title="SLA real: DATA prevista x ENTREGA", text="Quantidade")
        fig.update_layout(height=390, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# ABA TRACKING
# ============================================================
with aba_tracking:
    st.markdown('<div class="section-title">3. Tracking Operacional</div>', unsafe_allow_html=True)
    df_aberto = df_f[df_f["Não finalizada"]].copy()

    paradas_ops = df_aberto.groupby(col_ops).agg(Quantidade=("AWB", "count"), Aging_Medio=("Aging Dias", "mean")).reset_index().sort_values("Quantidade", ascending=False).head(20)
    fig = px.bar(paradas_ops, x="Quantidade", y=col_ops, orientation="h", title="Onde as cargas não finalizadas estão agora", text="Quantidade", hover_data={"Aging_Medio": ":.1f"})
    fig.update_layout(height=520, yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=55, b=20))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-title">Fluxo operacional detalhado</div>', unsafe_allow_html=True)
    if col_origin:
        fluxo_base = df_aberto.copy()
        fluxo_base["Origem"] = fluxo_base[col_origin].astype(str).str.strip().str.upper()
        fluxo_base["Unidade Atual"] = fluxo_base[col_ops].astype(str).str.strip().str.upper()
        fluxo_base["Destino"] = fluxo_base[col_destination].astype(str).str.strip().str.upper()
        fluxo_base["Fluxo"] = fluxo_base["Origem"] + " → " + fluxo_base["Unidade Atual"] + " → " + fluxo_base["Destino"]

        fluxo_detalhado = (
            fluxo_base.groupby(["Origem", "Unidade Atual", "Destino", "Fluxo"])
            .agg(
                Qtde_AWBs=("AWB", "count"),
                Fora_SLA=("Risco SLA", lambda s: (s == "Fora SLA").sum()),
                Sem_Entrega=("Status Prazo Real", lambda s: (s == "Sem entrega").sum()),
                Ocorrencias_Criticas=("Ocorrência Especial", lambda s: (s != "Sem ocorrência crítica").sum()),
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

            f1, f2, f3, f4 = st.columns(4)
            with f1:
                render_kpi("Fluxos únicos", format_int(len(fluxo_detalhado)), "Origem → Unidade atual → Destino")
            with f2:
                render_kpi("Maior fluxo", str(fluxo_detalhado.iloc[0]["Fluxo"]), f"{format_int(fluxo_detalhado.iloc[0]['Qtde_AWBs'])} AWBs")
            with f3:
                render_kpi("Fluxos com fora SLA", format_int((fluxo_detalhado["Fora_SLA"] > 0).sum()), "Fluxos que precisam de atenção")
            with f4:
                render_kpi("Ocorrências críticas", format_int(fluxo_detalhado["Ocorrencias_Criticas"].sum()), "Avaria, extravio, MSCA ou FOUND")

            c_fluxo1, c_fluxo2 = st.columns(2)
            with c_fluxo1:
                top_fluxos = fluxo_detalhado.head(20).copy()
                fig = px.bar(top_fluxos.sort_values("Qtde_AWBs", ascending=True), x="Qtde_AWBs", y="Fluxo", orientation="h", title="Top 20 fluxos operacionais por volume", text="Qtde_AWBs", hover_data=["Fora_SLA", "Sem_Entrega", "Ocorrencias_Criticas", "Aging_Medio_Dias", "Status_Mais_Comum"])
                fig.update_layout(height=620, margin=dict(l=20, r=20, t=55, b=20))
                st.plotly_chart(fig, use_container_width=True)

            with c_fluxo2:
                top_criticos = fluxo_detalhado.sort_values(["Fora_SLA", "Sem_Entrega", "Ocorrencias_Criticas", "Aging_Medio_Dias", "Qtde_AWBs"], ascending=False).head(20)
                fig = px.scatter(top_criticos, x="Qtde_AWBs", y="Aging_Medio_Dias", size="Fora_SLA", hover_name="Fluxo", hover_data=["Sem_Entrega", "Ocorrencias_Criticas", "Status_Mais_Comum", "% do Total"], title="Fluxos críticos: volume x aging x fora SLA")
                fig.update_layout(height=620, margin=dict(l=20, r=20, t=55, b=20))
                st.plotly_chart(fig, use_container_width=True)

            st.subheader("Tabela completa de fluxo operacional")
            st.dataframe(fluxo_detalhado, use_container_width=True, hide_index=True)
        else:
            st.info("Não há cargas não finalizadas para montar o fluxo operacional detalhado.")
    else:
        st.info("Para montar o fluxo operacional completo, a coluna OriginCode precisa estar disponível.")


# ============================================================
# ABA SLA REAL & AGING
# ============================================================
with aba_sla:
    st.markdown('<div class="section-title">4. SLA Real, Risco e Aging</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)

    with c1:
        prazo = df_f.groupby("Status Prazo Real").size().reset_index(name="Quantidade").sort_values("Quantidade", ascending=False)
        fig = px.bar(prazo, x="Status Prazo Real", y="Quantidade", title="SLA real por status", text="Quantidade")
        fig.update_layout(height=390, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        aging = df_f[df_f["Não finalizada"]].groupby("Faixa Aging").size().reset_index(name="Quantidade")
        ordem = ["0-24h", "24-48h", "48-72h", ">72h", "Sem data"]
        aging["ordem"] = aging["Faixa Aging"].apply(lambda x: ordem.index(x) if x in ordem else 99)
        aging = aging.sort_values("ordem")
        fig = px.bar(aging, x="Faixa Aging", y="Quantidade", title="Aging de cargas não finalizadas", text="Quantidade")
        fig.update_layout(height=390, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    sla_dest = df_f[df_f["Status Prazo Real"].isin(["Dentro do prazo", "Fora do prazo"])].groupby(col_destination).agg(Total=("AWB", "count"), Dentro=("Status Prazo Real", lambda s: (s == "Dentro do prazo").sum()), Fora=("Status Prazo Real", lambda s: (s == "Fora do prazo").sum())).reset_index()
    if not sla_dest.empty:
        sla_dest["SLA Real %"] = sla_dest["Dentro"] / sla_dest["Total"] * 100
        sla_dest = sla_dest.sort_values("SLA Real %", ascending=True).head(15)
        fig = px.bar(sla_dest, x="SLA Real %", y=col_destination, orientation="h", title="SLA real por destino - piores destinos", text=sla_dest["SLA Real %"].round(1), hover_data=["Total", "Dentro", "Fora"])
        fig.update_xaxes(range=[0, 105])
        fig.update_layout(height=430, yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados suficientes para SLA por destino.")

    st.subheader("Timeline previsto x entregue")
    timeline_cols = ["AWB", col_destination, col_ops, "Data Prevista Entrega", "Data Real Entrega", "Status Prazo Real", "Ocorrência Especial"]
    timeline_cols = [c for c in timeline_cols if c in df_f.columns]
    st.dataframe(df_f[timeline_cols].sort_values("Data Prevista Entrega", na_position="last"), use_container_width=True, hide_index=True)


# ============================================================
# ABA OCORRÊNCIAS
# ============================================================
with aba_ocorrencias:
    st.markdown('<div class="section-title">5. Ocorrências Críticas</div>', unsafe_allow_html=True)

    ocorr = df_f[df_f["Ocorrência Especial"].ne("Sem ocorrência crítica") & df_f["Ocorrência Especial"].ne("Sem dados Commission")].copy()

    c1, c2 = st.columns(2)
    with c1:
        if not ocorr.empty:
            ocorr_dist = ocorr.groupby("Ocorrência Especial").size().reset_index(name="Quantidade").sort_values("Quantidade", ascending=False)
            fig = px.bar(ocorr_dist, x="Ocorrência Especial", y="Quantidade", title="Distribuição de ocorrências especiais", text="Quantidade")
            fig.update_layout(height=390, xaxis_tickangle=-25, margin=dict(l=20, r=20, t=55, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhuma ocorrência crítica encontrada nos filtros atuais.")

    with c2:
        if not ocorr.empty:
            ocorr_dest = ocorr.groupby(col_destination).size().reset_index(name="Quantidade").sort_values("Quantidade", ascending=False).head(15)
            fig = px.bar(ocorr_dest, x="Quantidade", y=col_destination, orientation="h", title="Ocorrências por destino", text="Quantidade")
            fig.update_layout(height=390, yaxis={"categoryorder": "total ascending"}, margin=dict(l=20, r=20, t=55, b=20))
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("AWBs com ocorrência crítica")
    cols_ocorr_exibir = ["AWB", "AWB_COMPLETA_COMMISSION", col_origin, col_destination, col_ops, "Status Grupo", "Status Prazo Real", "Ocorrência Especial", "Data Prevista Entrega", "Data Real Entrega", "Peso Taxado", "Total Frete"]
    cols_ocorr_exibir += [c for c in cols_ocorrencia if c in df_f.columns]
    cols_ocorr_exibir = [c for c in cols_ocorr_exibir if c in df_f.columns]
    st.dataframe(ocorr[cols_ocorr_exibir] if not ocorr.empty else pd.DataFrame(columns=cols_ocorr_exibir), use_container_width=True, hide_index=True)


# ============================================================
# ABA OFENSORES
# ============================================================
with aba_ofensores:
    st.markdown('<div class="section-title">6. Ranking de Ofensores</div>', unsafe_allow_html=True)
    df_aberto = df_f[df_f["Não finalizada"]].copy()

    rank_ops = df_aberto.groupby(col_ops).agg(
        Cargas=("AWB", "count"),
        Fora_SLA=("Risco SLA", lambda s: (s == "Fora SLA").sum()),
        Sem_Entrega=("Status Prazo Real", lambda s: (s == "Sem entrega").sum()),
        Ocorrencias_Criticas=("Ocorrência Especial", lambda s: ((s != "Sem ocorrência crítica") & (s != "Sem dados Commission")).sum()),
        Fora_Destino=("Fora do destino", "sum"),
        Aging_Medio=("Aging Dias", "mean"),
        Peso_Total=("Peso", "sum"),
    ).reset_index().sort_values(["Fora_SLA", "Sem_Entrega", "Ocorrencias_Criticas", "Cargas"], ascending=False)

    rank_dest = df_f.groupby(col_destination).agg(
        Cargas=("AWB", "count"),
        Fora_SLA=("Risco SLA", lambda s: (s == "Fora SLA").sum()),
        Sem_Entrega=("Status Prazo Real", lambda s: (s == "Sem entrega").sum()),
        Ocorrencias_Criticas=("Ocorrência Especial", lambda s: ((s != "Sem ocorrência crítica") & (s != "Sem dados Commission")).sum()),
        Aging_Medio=("Aging Dias", "mean"),
        Peso_Total=("Peso", "sum"),
        Total_Frete=("Total Frete", "sum"),
    ).reset_index().sort_values(["Fora_SLA", "Sem_Entrega", "Ocorrencias_Criticas", "Cargas"], ascending=False)

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
    prioridade = df_f[(df_f["Risco SLA"].isin(["Fora SLA", "Risco 24h", "Sem entrega"])) | (df_f["Ocorrência Especial"].str.contains("Avaria|Extravio|MSCA|FOUND|localizada", case=False, na=False))].copy()
    prioridade = prioridade.sort_values(["Risco SLA", "Aging Dias"], ascending=[True, False])
    cols_prioridade = ["AWB", "AWB_COMPLETA_COMMISSION", col_origin, col_destination, col_ops, col_status, "Status Grupo", "Risco SLA", "Status Prazo Real", "Ocorrência Especial", "ExecutionDateTime_dt", "ApproxSLA_dt", "Data Prevista Entrega", "Data Real Entrega", "Aging Dias", "Peso", "Peso Taxado", "Total Frete"]
    cols_prioridade = [c for c in cols_prioridade if c is not None and c in prioridade.columns]
    st.dataframe(prioridade[cols_prioridade], use_container_width=True, hide_index=True)


# ============================================================
# ABA BASE E EXPORTAÇÃO
# ============================================================
with aba_detalhe:
    st.markdown('<div class="section-title">7. Base filtrada e exportação</div>', unsafe_allow_html=True)

    colunas_exibir = [
        "AWB", "AWB_MATCH", "AWB_COMPLETA_COMMISSION", "Encontrada na Commission",
        col_origin, col_destination, col_ops, col_status, col_status_en,
        "Status Grupo", "Risco SLA", "Risco SLA Estimado", "Status Prazo Real", "Ocorrência Especial",
        col_billto, col_product, col_delivery_request,
        "ExecutionDateTime_dt", "ApproxSLA_dt", "Data Prevista Entrega", "Data Real Entrega",
        col_flt_no, "FltDt_dt", col_flt_origin, col_flt_destination,
        "Aging Dias", "Faixa Aging", "Carga no destino final", "Peso", "Peso Taxado", "Total Frete",
        col_shipper, col_consignee,
    ]
    colunas_exibir += [c for c in cols_ocorrencia if c in df_f.columns]
    colunas_exibir = [c for c in colunas_exibir if c is not None and c in df_f.columns]

    st.dataframe(df_f[colunas_exibir], use_container_width=True, hide_index=True)

    # Abas de exportação
    base_export = df_f[colunas_exibir].copy()
    resumo_sla = df_f.groupby("Status Prazo Real").size().reset_index(name="Quantidade")
    resumo_ocorr = df_f.groupby("Ocorrência Especial").size().reset_index(name="Quantidade")
    rank_dest_export = df_f.groupby(col_destination).agg(Cargas=("AWB", "count"), Fora_SLA=("Risco SLA", lambda s: (s == "Fora SLA").sum()), Sem_Entrega=("Status Prazo Real", lambda s: (s == "Sem entrega").sum()), Ocorrencias_Criticas=("Ocorrência Especial", lambda s: ((s != "Sem ocorrência crítica") & (s != "Sem dados Commission")).sum()), Total_Frete=("Total Frete", "sum")).reset_index()

    excel_bytes = gerar_excel_abas({
        "Base Filtrada": base_export,
        "Resumo SLA": resumo_sla,
        "Ocorrencias": resumo_ocorr,
        "Ranking Destinos": rank_dest_export,
    })
    st.download_button(
        label="📥 Baixar relatório consolidado em Excel",
        data=excel_bytes,
        file_name="relatorio_consolidado_performance_awb.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    csv_bytes = base_export.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        label="📥 Baixar base filtrada em CSV",
        data=csv_bytes,
        file_name="base_filtrada_performance_awb.csv",
        mime="text/csv",
    )

    with st.expander("🔧 Diagnóstico das colunas lidas"):
        st.write("Colunas Operation Status:", list(df.columns))
        st.write("Colunas Commission Report:", list(df_comm.columns) if df_comm is not None else "Planilha não carregada")
        st.write(
            {
                "AWBPrefix": col_awb_prefix,
                "AWBNumber": col_awb_number,
                "OriginCode": col_origin,
                "DestinationCode": col_destination,
                "ExecutionDateTime": col_execution,
                "OPSStation": col_ops,
                "StatusDescription": col_status,
                "ApproxSLA": col_approx_sla,
                "BillTo": col_billto,
                "Commission AWB": col_comm_awb,
                "Commission DATA": col_comm_data_prev,
                "Commission ENTREGA": col_comm_entrega,
                "Commission ocorrências": cols_ocorrencia,
            }
        )


# ============================================================
# RODAPÉ
# ============================================================
st.caption(
    "Dashboard desenvolvida para análise operacional com duas planilhas: tracking, entrega real, SLA, aging, ofensores, ocorrências e fluxo operacional."
)
