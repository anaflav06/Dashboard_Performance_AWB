from __future__ import annotations

from io import BytesIO
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

    .alert-card {
        background: #FFF3E8;
        border-left: 6px solid #FF8A00;
        padding: 14px 16px;
        border-radius: 14px;
        color: #5D3200;
        margin: 10px 0 16px 0;
        border-top: 1px solid #FFD1A3;
        border-right: 1px solid #FFD1A3;
        border-bottom: 1px solid #FFD1A3;
    }

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


def encontrar_coluna_por_posicao(df: pd.DataFrame, letra_excel: str) -> str | None:
    # A=0, B=1, ... BE=56
    letra_excel = letra_excel.strip().upper()
    num = 0
    for ch in letra_excel:
        if not ("A" <= ch <= "Z"):
            return None
        num = num * 26 + (ord(ch) - ord("A") + 1)
    idx = num - 1
    if 0 <= idx < len(df.columns):
        return df.columns[idx]
    return None


def normalizar_awb(valor: object) -> str:
    """Remove caracteres, tira prefixo 577 quando existir e preserva zeros à esquerda quando possível."""
    if pd.isna(valor):
        return ""
    txt = str(valor).strip()
    txt = txt.replace(".0", "") if txt.endswith(".0") else txt
    apenas = "".join(ch for ch in txt if ch.isdigit())
    if apenas.startswith("577") and len(apenas) > 8:
        apenas = apenas[3:]
    return apenas.lstrip("0") or apenas


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


def detectar_ocorrencia_texto(valor: object, palavras: list[str]) -> bool:
    txt = norm_txt(valor)
    return any(p in txt for p in palavras)


def status_nao_finalizado(status_grupo: object) -> bool:
    return str(status_grupo) != "Entregue"


def faixa_aging_horas(horas: float | int | None) -> str:
    if horas is None or pd.isna(horas):
        return "Sem data"
    if horas <= 24:
        return "0-24h"
    if horas <= 48:
        return "24-48h"
    if horas <= 72:
        return "48-72h"
    return ">72h"


def classificar_sla_entrega(row: pd.Series) -> str:
    status = row.get("Status Grupo")
    prevista = row.get("Data Prevista_dt")
    entrega = row.get("Data Entrega_dt")
    approx = row.get("ApproxSLA_dt")

    if status == "Entregue":
        base_prevista = prevista if not pd.isna(prevista) else approx
        if pd.isna(base_prevista) or pd.isna(entrega):
            return "Entregue sem data"
        return "Dentro SLA" if entrega.normalize() <= base_prevista.normalize() else "Fora SLA"

    base_prevista = prevista if not pd.isna(prevista) else approx
    if pd.isna(base_prevista):
        return "Sem SLA"

    hoje = pd.Timestamp.now().normalize()
    prevista_norm = base_prevista.normalize()
    if prevista_norm < hoje:
        return "Atrasada"
    if prevista_norm == hoje:
        return "Vence hoje"
    if prevista_norm == hoje + pd.Timedelta(days=1):
        return "Vence amanhã"
    return "Em risco"


def prioridade_operacional(risco: str) -> str:
    if risco in ["Atrasada", "Fora SLA"]:
        return "ALTA"
    if risco in ["Vence hoje", "Vence amanhã"]:
        return "MÉDIA"
    if risco in ["Em risco"]:
        return "BAIXA"
    return "-"


def gerar_excel_multi(abas: dict[str, pd.DataFrame]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#003B71", "font_color": "white", "border": 1})
        money_fmt = workbook.add_format({"num_format": "#,##0.00"})
        date_fmt = workbook.add_format({"num_format": "dd/mm/yyyy"})

        for nome_aba, df_export in abas.items():
            if df_export is None:
                continue
            sheet = nome_aba[:31]
            df_tmp = df_export.copy()
            df_tmp.to_excel(writer, sheet_name=sheet, index=False)
            worksheet = writer.sheets[sheet]
            for col_num, value in enumerate(df_tmp.columns.values):
                worksheet.write(0, col_num, value, header_fmt)
                largura = min(max(len(str(value)) + 2, 12), 45)
                worksheet.set_column(col_num, col_num, largura)
                if "data" in norm_txt(value) or str(value).endswith("_dt"):
                    worksheet.set_column(col_num, col_num, 16, date_fmt)
                if "valor" in norm_txt(value) or "peso" in norm_txt(value):
                    worksheet.set_column(col_num, col_num, 14, money_fmt)
            worksheet.freeze_panes(1, 0)
            worksheet.autofilter(0, 0, max(len(df_tmp), 1), max(len(df_tmp.columns) - 1, 0))
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
        <p>Performance do cliente e controle operacional com cruzamento entre AWB Operation Status e Comission Report Franchise.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# UPLOAD
# ============================================================
with st.sidebar:
    st.header("📁 Arquivos")
    arquivo_status = st.file_uploader(
        "1) AWB Operation Status",
        type=["xlsx", "xls", "csv"],
        key="arquivo_status",
    )
    arquivo_comission = st.file_uploader(
        "2) Comission Report Franchise",
        type=["xlsx", "xls", "csv"],
        key="arquivo_comission",
    )

if arquivo_status is None:
    st.info("Carregue a planilha AWB Operation Status para iniciar a análise.")
    st.stop()

try:
    df_status_raw = carregar_arquivo(arquivo_status)
except Exception as exc:
    st.error(f"Erro ao ler a planilha AWB Operation Status: {exc}")
    st.stop()

if df_status_raw.empty:
    st.warning("A planilha AWB Operation Status está vazia.")
    st.stop()

# Segunda planilha é opcional para não travar análise inicial, mas melhora SLA real.
df_com_raw = pd.DataFrame()
if arquivo_comission is not None:
    try:
        df_com_raw = carregar_arquivo(arquivo_comission)
    except Exception as exc:
        st.error(f"Erro ao ler a planilha Comission Report Franchise: {exc}")
        st.stop()


# ============================================================
# MAPEAMENTO DE COLUNAS - AWB OPERATION STATUS
# ============================================================
df = df_status_raw.copy()

col_awb_prefix = encontrar_coluna(df, ["AWBPrefix", "AWB Prefix", "Prefixo AWB"])
col_awb_number = encontrar_coluna(df, ["AWBNumber", "AWB Number", "AWB", "Numero AWB", "Número AWB"])
col_origin = encontrar_coluna(df, ["OriginCode", "Origin", "Origem"])
col_destination = encontrar_coluna(df, ["DestinationCode", "Destination", "Destino"])
col_execution = encontrar_coluna(df, ["ExecutionDateTime", "Execution Date Time", "Data Emissão", "Data Emissao"])
col_pieces = encontrar_coluna(df, ["PiecesCount", "No of Pieces", "Pieces"])
col_ops = encontrar_coluna(df, ["OPSStation", "OPS Station", "Unidade Atual", "Base Atual"])
col_flt_no = encontrar_coluna(df, ["FltNo", "FlightNo", "Voo"])
col_flt_dt = encontrar_coluna(df, ["FltDt", "FlightDate", "Data Voo"])
col_flt_origin = encontrar_coluna(df, ["FltOrigin", "FlightOrigin"])
col_flt_destination = encontrar_coluna(df, ["FltDestination", "FlightDestination"])
col_status = encontrar_coluna(df, ["StatusDescription", "Status Description", "Status"])
col_status_en = encontrar_coluna(df, ["StatusDescriptionEN", "Status Description EN"])
col_approx_sla = encontrar_coluna(df, ["ApproxSLA", "Approx SLA", "SLA", "Prazo"])
col_billto = encontrar_coluna(df, ["BillTo", "Bill To", "Cliente"])
col_product = encontrar_coluna(df, ["ProductType", "Product Type", "Produto"])
col_shipper = encontrar_coluna(df, ["Shipper", "Remetente"])
col_consignee = encontrar_coluna(df, ["Consignee", "Destinatario", "Destinatário"])
col_delivery_request = encontrar_coluna(df, ["DeliveryRequest", "Delivery Request"])
col_gross_wt = encontrar_coluna(df, ["GrossWt", "Gross Weight", "Peso"])

obrigatorias = {
    "DestinationCode": col_destination,
    "ExecutionDateTime": col_execution,
    "OPSStation": col_ops,
    "StatusDescription": col_status,
    "BillTo": col_billto,
}

faltantes = [nome for nome, col in obrigatorias.items() if col is None]
if faltantes:
    st.error("Não encontrei estas colunas obrigatórias na AWB Operation Status: " + ", ".join(faltantes))
    st.write("Colunas encontradas na planilha:", list(df.columns))
    st.stop()


# ============================================================
# TRATAMENTO DA AWB OPERATION STATUS
# ============================================================
df_work = df.copy()

if col_awb_prefix and col_awb_number:
    df_work["AWB Original"] = df_work[col_awb_prefix].astype(str).str.replace(".0", "", regex=False).str.zfill(3) + df_work[col_awb_number].astype(str).str.replace(".0", "", regex=False).str.zfill(8)
elif col_awb_number:
    df_work["AWB Original"] = df_work[col_awb_number].astype(str)
else:
    df_work["AWB Original"] = df_work.index.astype(str)

df_work["AWB Normalizada"] = df_work["AWB Original"].apply(normalizar_awb)
df_work["AWB"] = df_work["AWB Normalizada"]

df_work["ExecutionDateTime_dt"] = pd.to_datetime(df_work[col_execution], errors="coerce", dayfirst=True)
if col_approx_sla:
    df_work["ApproxSLA_dt"] = pd.to_datetime(df_work[col_approx_sla], errors="coerce", dayfirst=True)
else:
    df_work["ApproxSLA_dt"] = pd.NaT
if col_flt_dt:
    df_work["FltDt_dt"] = pd.to_datetime(df_work[col_flt_dt], errors="coerce", dayfirst=True)
else:
    df_work["FltDt_dt"] = pd.NaT

df_work = df_work.dropna(subset=["ExecutionDateTime_dt"])
if df_work.empty:
    st.warning("Nenhuma linha possui ExecutionDateTime válido.")
    st.stop()

df_work["Data Emissão"] = df_work["ExecutionDateTime_dt"].dt.date
df_work["Mês"] = df_work["ExecutionDateTime_dt"].dt.to_period("M").astype(str)
df_work["Status Grupo"] = df_work[col_status].apply(classificar_status)
df_work["Não finalizada"] = df_work["Status Grupo"].apply(status_nao_finalizado)
df_work["Carga no destino final"] = (
    df_work[col_destination].astype(str).str.strip().str.upper()
    == df_work[col_ops].astype(str).str.strip().str.upper()
)
df_work["Fora do destino"] = ~df_work["Carga no destino final"]
df_work["Horas sem movimentação"] = (
    pd.Timestamp.now() - df_work["ExecutionDateTime_dt"]
).dt.total_seconds() / 3600
df_work["Aging Dias"] = df_work["Horas sem movimentação"] / 24
df_work["Faixa Aging"] = df_work["Horas sem movimentação"].apply(faixa_aging_horas)

if col_gross_wt:
    df_work["Peso"] = pd.to_numeric(df_work[col_gross_wt], errors="coerce").fillna(0)
else:
    df_work["Peso"] = 0


# ============================================================
# TRATAMENTO DA COMISSION REPORT FRANCHISE
# ============================================================
col_com_awb = None
col_data_prevista = None
col_data_entrega = None
col_avaria = None
col_extravio = None
col_found = None

df_com = pd.DataFrame()
if not df_com_raw.empty:
    df_com = df_com_raw.copy()

    col_com_awb = encontrar_coluna(df_com, ["AWB", "AWBNumber", "AWB Number", "Conhecimento", "Numero AWB", "Número AWB"])
    if col_com_awb is None:
        col_com_awb = encontrar_coluna_por_posicao(df_com, "B")

    col_data_prevista = encontrar_coluna(df_com, ["DATA", "Data", "Data Prevista", "Previsao", "Previsão", "Prazo Entrega"])
    if col_data_prevista is None:
        col_data_prevista = encontrar_coluna_por_posicao(df_com, "F")

    col_data_entrega = encontrar_coluna(df_com, ["ENTREGA", "Entrega", "Data Entrega", "Data Oficial Entrega"])
    if col_data_entrega is None:
        col_data_entrega = encontrar_coluna_por_posicao(df_com, "G")

    col_avaria = encontrar_coluna(df_com, ["AVARIA", "Avaria"])
    if col_avaria is None:
        col_avaria = encontrar_coluna_por_posicao(df_com, "BE")

    col_extravio = encontrar_coluna(df_com, ["EXTRAVIO", "MSCA", "Extravio MSCA"])
    if col_extravio is None:
        col_extravio = encontrar_coluna_por_posicao(df_com, "BG")

    col_found = encontrar_coluna(df_com, ["FOUND", "Carga Localizada", "Localizada"])
    if col_found is None:
        col_found = encontrar_coluna_por_posicao(df_com, "BI")

    if col_com_awb is not None:
        df_com["AWB Original Comission"] = df_com[col_com_awb].astype(str)
        df_com["AWB Normalizada"] = df_com[col_com_awb].apply(normalizar_awb)
    else:
        st.warning("Não encontrei a coluna de AWB na Comission Report Franchise. O cruzamento com prazo real não será feito.")
        df_com["AWB Normalizada"] = ""

    if col_data_prevista:
        df_com["Data Prevista_dt"] = pd.to_datetime(df_com[col_data_prevista], errors="coerce", dayfirst=True)
    else:
        df_com["Data Prevista_dt"] = pd.NaT

    if col_data_entrega:
        df_com["Data Entrega_dt"] = pd.to_datetime(df_com[col_data_entrega], errors="coerce", dayfirst=True)
    else:
        df_com["Data Entrega_dt"] = pd.NaT

    if col_avaria:
        df_com["Avaria"] = df_com[col_avaria].apply(lambda x: detectar_ocorrencia_texto(x, ["avaria"]) or (str(x).strip() not in ["", "nan", "None"]))
    else:
        df_com["Avaria"] = False

    if col_extravio:
        df_com["Extravio MSCA"] = df_com[col_extravio].apply(lambda x: detectar_ocorrencia_texto(x, ["extravio", "msca"]) or (str(x).strip() not in ["", "nan", "None"]))
    else:
        df_com["Extravio MSCA"] = False

    if col_found:
        df_com["Found"] = df_com[col_found].apply(lambda x: detectar_ocorrencia_texto(x, ["found", "localizada", "localizado"]) or (str(x).strip() not in ["", "nan", "None"]))
    else:
        df_com["Found"] = False

    colunas_merge = [
        "AWB Normalizada",
        "Data Prevista_dt",
        "Data Entrega_dt",
        "Avaria",
        "Extravio MSCA",
        "Found",
    ]
    if "AWB Original Comission" in df_com.columns:
        colunas_merge.append("AWB Original Comission")

    df_com_merge = (
        df_com[colunas_merge]
        .dropna(subset=["AWB Normalizada"])
        .drop_duplicates(subset=["AWB Normalizada"], keep="last")
    )

    df_work = df_work.merge(df_com_merge, on="AWB Normalizada", how="left")
else:
    df_work["Data Prevista_dt"] = pd.NaT
    df_work["Data Entrega_dt"] = pd.NaT
    df_work["Avaria"] = False
    df_work["Extravio MSCA"] = False
    df_work["Found"] = False

for col_bool in ["Avaria", "Extravio MSCA", "Found"]:
    if col_bool not in df_work.columns:
        df_work[col_bool] = False
    df_work[col_bool] = df_work[col_bool].fillna(False).astype(bool)

if "Data Prevista_dt" not in df_work.columns:
    df_work["Data Prevista_dt"] = pd.NaT
if "Data Entrega_dt" not in df_work.columns:
    df_work["Data Entrega_dt"] = pd.NaT

df_work["SLA Real"] = df_work.apply(classificar_sla_entrega, axis=1)
df_work["Dentro SLA"] = df_work["SLA Real"].isin(["Dentro SLA"])
df_work["Fora SLA"] = df_work["SLA Real"].isin(["Fora SLA", "Atrasada"])
df_work["Prioridade"] = df_work["SLA Real"].apply(prioridade_operacional)

def calcular_horas_para_sla(row: pd.Series) -> float | None:
    prevista = row.get("Data Prevista_dt")
    if pd.isna(prevista):
        prevista = row.get("ApproxSLA_dt")
    if pd.isna(prevista):
        return None
    return (prevista - pd.Timestamp.now()).total_seconds() / 3600


df_work["Horas para SLA"] = df_work.apply(calcular_horas_para_sla, axis=1)

# Fallback: quando não tem a Comission, usa ApproxSLA para risco operacional.
sem_comission = arquivo_comission is None or df_com.empty
if sem_comission:
    def risco_fallback(row: pd.Series) -> str:
        if row.get("Status Grupo") == "Entregue":
            return "Finalizado"
        horas = row.get("Horas para SLA")
        if horas is None or pd.isna(horas):
            return "Sem SLA"
        if horas < 0:
            return "Atrasada"
        if horas <= 24:
            return "Vence hoje"
        if horas <= 48:
            return "Vence amanhã"
        return "Em risco"
    df_work["SLA Real"] = df_work.apply(risco_fallback, axis=1)
    df_work["Dentro SLA"] = df_work["SLA Real"].isin(["Finalizado"])
    df_work["Fora SLA"] = df_work["SLA Real"].isin(["Atrasada"])
    df_work["Prioridade"] = df_work["SLA Real"].apply(prioridade_operacional)


# ============================================================
# FILTROS
# ============================================================
with st.sidebar:
    st.header("🔎 Filtros")

    clientes = sorted(df_work[col_billto].dropna().astype(str).unique())
    if not clientes:
        st.error("Não há clientes na coluna BillTo.")
        st.stop()

    default_cliente_idx = 0
    for i, c in enumerate(clientes):
        if "TRES CORACOES" in c.upper() or "3 CORACOES" in c.upper():
            default_cliente_idx = i
            break

    cliente = st.selectbox("Cliente / BillTo", clientes, index=default_cliente_idx)
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

    risco_options = ["Todos"] + sorted(df_f["SLA Real"].dropna().astype(str).unique())
    risco_sel = st.multiselect("SLA / Risco", risco_options, default=["Todos"])
    if risco_sel and "Todos" not in risco_sel:
        df_f = df_f[df_f["SLA Real"].astype(str).isin(risco_sel)]

    if col_product:
        prod_options = ["Todos"] + sorted(df_f[col_product].dropna().astype(str).unique())
        prod_sel = st.multiselect("Produto", prod_options, default=["Todos"])
        if prod_sel and "Todos" not in prod_sel:
            df_f = df_f[df_f[col_product].astype(str).isin(prod_sel)]

if df_f.empty:
    st.warning("Nenhum dado encontrado para os filtros selecionados.")
    st.stop()


# ============================================================
# ALERTA DE CRUZAMENTO
# ============================================================
if not df_com.empty and "AWB Normalizada" in df_com.columns:
    awb_status_set = set(df_f["AWB Normalizada"].dropna().astype(str))
    awb_com_set = set(df_com["AWB Normalizada"].dropna().astype(str))
    awb_status_sem_com = sorted([x for x in awb_status_set if x and x not in awb_com_set])
    awb_com_sem_status = sorted([x for x in awb_com_set if x and x not in awb_status_set])
    if awb_status_sem_com:
        st.markdown(
            f"""
            <div class="alert-card">
                <b>Atenção:</b> existem <b>{format_int(len(awb_status_sem_com))}</b> AWBs da AWB Operation Status que não foram encontradas na Comission Report Franchise.
                Isso pode impactar o cálculo de data prevista x data de entrega. Use a aba de exportação para baixar a lista.
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        """
        <div class="alert-card">
            <b>Atenção:</b> a Comission Report Franchise não foi carregada. O app usará ApproxSLA quando disponível, mas a visão de data prevista x entrega oficial ficará limitada.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# KPIs PRINCIPAIS
# ============================================================
st.markdown('<div class="section-title">Resumo Geral</div>', unsafe_allow_html=True)

total = len(df_f)
entregues = int((df_f["Status Grupo"] == "Entregue").sum())
dentro_sla = int((df_f["SLA Real"] == "Dentro SLA").sum())
fora_prazo = int(df_f["SLA Real"].isin(["Fora SLA", "Atrasada"]).sum())
avarias = int(df_f["Avaria"].sum())
extravios = int(df_f["Extravio MSCA"].sum())
found = int(df_f["Found"].sum())
nao_finalizadas = int(df_f["Não finalizada"].sum())
aging_medio = df_f.loc[df_f["Não finalizada"], "Aging Dias"].mean()
sla_pct = (dentro_sla / entregues * 100) if entregues > 0 else ((total - fora_prazo) / total * 100 if total else 0)
fora_pct = (fora_prazo / total * 100) if total else 0

c1, c2, c3, c4 = st.columns(4)
with c1:
    render_kpi("AWBs emitidas", format_int(total), "Base: ExecutionDateTime")
with c2:
    render_kpi("Entregues", format_int(entregues), f"{format_pct(entregues / total * 100 if total else 0)} da base")
with c3:
    render_kpi("SLA dentro do prazo", format_pct(sla_pct), "Base: data prevista x entrega")
with c4:
    render_kpi("Fora do prazo", format_pct(fora_pct), f"{format_int(fora_prazo)} AWBs")

c5, c6, c7, c8 = st.columns(4)
with c5:
    render_kpi("Avarias", format_int(avarias), f"{format_pct(avarias / total * 100 if total else 0)} sobre emissões")
with c6:
    render_kpi("Extravios (MSCA)", format_int(extravios), f"{format_pct(extravios / total * 100 if total else 0)} sobre emissões")
with c7:
    render_kpi("Cargas localizadas", format_int(found), f"{format_pct(found / total * 100 if total else 0)} sobre emissões")
with c8:
    render_kpi("Aging médio", f"{format_float(aging_medio)} dias", "Cargas não finalizadas")


# ============================================================
# BASES AUXILIARES PARA ABAS
# ============================================================
df_aberto = df_f[df_f["Não finalizada"]].copy()
df_risco = df_f[df_f["SLA Real"].isin(["Atrasada", "Vence hoje", "Vence amanhã", "Em risco", "Sem SLA"])].copy()
df_ocorrencias = df_f[df_f[["Avaria", "Extravio MSCA", "Found"]].any(axis=1)].copy()


# ============================================================
# ABAS PRINCIPAIS
# ============================================================
aba_perf, aba_controle, aba_tracking, aba_ocorr, aba_export = st.tabs(
    [
        "📊 Performance do Cliente",
        "🚨 Controle Operacional",
        "🛰️ Onde estão parando",
        "⚠️ Ocorrências",
        "📥 Base & Exportação",
    ]
)


# ============================================================
# ABA PERFORMANCE DO CLIENTE
# ============================================================
with aba_perf:
    st.markdown('<div class="section-title">Evolução diária de emissões</div>', unsafe_allow_html=True)

    emissao_dia = df_f.groupby("Data Emissão").size().reset_index(name="AWBs Emitidas").sort_values("Data Emissão")
    emissao_dia["Média Móvel 7 dias"] = emissao_dia["AWBs Emitidas"].rolling(7, min_periods=1).mean()

    fig = go.Figure()
    fig.add_bar(x=emissao_dia["Data Emissão"], y=emissao_dia["AWBs Emitidas"], name="AWBs Emitidas", text=emissao_dia["AWBs Emitidas"], textposition="outside")
    fig.add_trace(go.Scatter(x=emissao_dia["Data Emissão"], y=emissao_dia["Média Móvel 7 dias"], mode="lines+markers", name="Média móvel 7 dias"))
    fig.update_layout(height=430, title="Evolução diária de emissões (AWBs)", margin=dict(l=20, r=20, t=60, b=20))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-title">Performance por destino</div>', unsafe_allow_html=True)
    perf_dest = (
        df_f.groupby(col_destination)
        .agg(
            AWBs_Emitidas=("AWB", "count"),
            Fora_Prazo=("SLA Real", lambda s: s.isin(["Fora SLA", "Atrasada"]).sum()),
            Dentro_SLA=("SLA Real", lambda s: (s == "Dentro SLA").sum()),
        )
        .reset_index()
    )
    perf_dest["Fora Prazo %"] = perf_dest["Fora_Prazo"] / perf_dest["AWBs_Emitidas"].replace(0, pd.NA) * 100
    perf_dest["SLA %"] = 100 - perf_dest["Fora Prazo %"].fillna(0)
    perf_dest = perf_dest.sort_values(["Fora Prazo %", "AWBs_Emitidas"], ascending=False)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(
            perf_dest.head(15).sort_values("Fora Prazo %", ascending=True),
            x="Fora Prazo %",
            y=col_destination,
            orientation="h",
            title="Destinos com maior % fora do prazo",
            text=perf_dest.head(15).sort_values("Fora Prazo %", ascending=True)["Fora Prazo %"].round(1),
            hover_data=["AWBs_Emitidas", "Fora_Prazo", "SLA %"],
        )
        fig.update_layout(height=460, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.dataframe(
            perf_dest.rename(columns={col_destination: "Destino"})[["Destino", "AWBs_Emitidas", "SLA %", "Fora_Prazo", "Fora Prazo %"]],
            use_container_width=True,
            hide_index=True,
        )

    st.markdown('<div class="section-title">Status operacional das AWBs</div>', unsafe_allow_html=True)
    c3, c4 = st.columns(2)
    with c3:
        status_dist = df_f.groupby("Status Grupo").size().reset_index(name="Quantidade")
        fig = px.pie(status_dist, values="Quantidade", names="Status Grupo", hole=0.55, title="Distribuição por status")
        fig.update_layout(height=410, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)
    with c4:
        aging = df_aberto.groupby("Faixa Aging").size().reset_index(name="Quantidade")
        ordem = ["0-24h", "24-48h", "48-72h", ">72h", "Sem data"]
        aging["ordem"] = aging["Faixa Aging"].apply(lambda x: ordem.index(x) if x in ordem else 99)
        aging = aging.sort_values("ordem")
        fig = px.pie(aging, values="Quantidade", names="Faixa Aging", hole=0.55, title="Aging das cargas em trânsito")
        fig.update_layout(height=410, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-title">Top ofensores operacionais</div>', unsafe_allow_html=True)
    c5, c6 = st.columns(2)
    with c5:
        top_dest = perf_dest.head(10).copy()
        fig = px.bar(top_dest.sort_values("Fora_Prazo"), x="Fora_Prazo", y=col_destination, orientation="h", title="Destinos com mais AWBs fora do prazo", text="Fora_Prazo")
        fig.update_layout(height=430, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)
    with c6:
        top_ops = (
            df_aberto.groupby(col_ops)
            .size()
            .reset_index(name="AWBs em trânsito")
            .sort_values("AWBs em trânsito", ascending=False)
            .head(10)
        )
        fig = px.bar(top_ops.sort_values("AWBs em trânsito"), x="AWBs em trânsito", y=col_ops, orientation="h", title="OPSStation com mais cargas paradas", text="AWBs em trânsito")
        fig.update_layout(height=430, margin=dict(l=20, r=20, t=55, b=20))
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# ABA CONTROLE OPERACIONAL
# ============================================================
with aba_controle:
    st.markdown('<div class="section-title">Controle de SLA — O que precisa atenção</div>', unsafe_allow_html=True)

    atrasadas = int((df_f["SLA Real"] == "Atrasada").sum())
    vence_hoje = int((df_f["SLA Real"] == "Vence hoje").sum())
    vence_amanha = int((df_f["SLA Real"] == "Vence amanhã").sum())
    em_risco = int((df_f["SLA Real"] == "Em risco").sum())

    a1, a2, a3, a4 = st.columns(4)
    with a1:
        render_kpi("Atrasadas", format_int(atrasadas), f"{format_pct(atrasadas / total * 100 if total else 0)} da base")
    with a2:
        render_kpi("Vence hoje", format_int(vence_hoje), f"{format_pct(vence_hoje / total * 100 if total else 0)} da base")
    with a3:
        render_kpi("Vence amanhã", format_int(vence_amanha), f"{format_pct(vence_amanha / total * 100 if total else 0)} da base")
    with a4:
        render_kpi("Em risco", format_int(em_risco), f"{format_pct(em_risco / total * 100 if total else 0)} da base")

    st.markdown(
        """
        <div class="insight-box">
            <b>Uso operacional:</b> baixe as listas abaixo para atuar nas AWBs críticas antes do fechamento do SLA.
            A prioridade ALTA considera cargas atrasadas ou fora do prazo; MÉDIA considera cargas que vencem hoje ou amanhã.
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols_lista = [
        "AWB Original",
        "AWB Normalizada",
        col_origin,
        col_destination,
        col_ops,
        col_status,
        "Status Grupo",
        "SLA Real",
        "Prioridade",
        "Data Emissão",
        "Data Prevista_dt",
        "Data Entrega_dt",
        "Horas para SLA",
        "Horas sem movimentação",
        "Faixa Aging",
    ]
    cols_lista = [c for c in cols_lista if c is not None and c in df_f.columns]

    df_risco_view = df_risco[cols_lista].sort_values(["Prioridade", "Horas para SLA"], ascending=[True, True])
    st.subheader("Lista de cargas em risco / atrasadas")
    st.dataframe(df_risco_view, use_container_width=True, hide_index=True)

    excel_risco = gerar_excel_multi({"Cargas em risco": df_risco_view})
    st.download_button(
        label="📥 Baixar AWBs em risco/atrasadas",
        data=excel_risco,
        file_name="awbs_em_risco_atrasadas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown('<div class="section-title">Sem movimentação</div>', unsafe_allow_html=True)
    sem_mov_12 = df_aberto[df_aberto["Horas sem movimentação"] > 12]
    sem_mov_24 = df_aberto[df_aberto["Horas sem movimentação"] > 24]
    sem_mov_48 = df_aberto[df_aberto["Horas sem movimentação"] > 48]

    s1, s2, s3 = st.columns(3)
    with s1:
        render_kpi("Sem movimentação >12h", format_int(len(sem_mov_12)), "Cargas paradas")
    with s2:
        render_kpi("Sem movimentação >24h", format_int(len(sem_mov_24)), "Atenção operacional")
    with s3:
        render_kpi("Sem movimentação >48h", format_int(len(sem_mov_48)), "Crítico")

    sem_mov_view = sem_mov_12[cols_lista].sort_values("Horas sem movimentação", ascending=False)
    st.dataframe(sem_mov_view, use_container_width=True, hide_index=True)


# ============================================================
# ABA ONDE ESTÃO PARANDO
# ============================================================
with aba_tracking:
    st.markdown('<div class="section-title">OPSStation — onde as cargas estão parando</div>', unsafe_allow_html=True)

    if df_aberto.empty:
        st.info("Não há cargas em aberto/não finalizadas para os filtros selecionados.")
    else:
        ops_retencao = (
            df_aberto.groupby(col_ops)
            .agg(
                AWBs_em_transito=("AWB", "count"),
                Tempo_medio_horas=("Horas sem movimentação", "mean"),
                Atrasadas=("SLA Real", lambda s: (s == "Atrasada").sum()),
            )
            .reset_index()
            .sort_values("AWBs_em_transito", ascending=False)
        )
        ops_retencao["% do total em trânsito"] = ops_retencao["AWBs_em_transito"] / ops_retencao["AWBs_em_transito"].sum() * 100

        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(
                ops_retencao.head(15).sort_values("AWBs_em_transito"),
                x="AWBs_em_transito",
                y=col_ops,
                orientation="h",
                title="Top OPSStation com mais retenção",
                text="AWBs_em_transito",
            )
            fig.update_layout(height=500, margin=dict(l=20, r=20, t=55, b=20))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.bar(
                ops_retencao.head(15).sort_values("Tempo_medio_horas"),
                x="Tempo_medio_horas",
                y=col_ops,
                orientation="h",
                title="Tempo médio parado por OPSStation (horas)",
                text=ops_retencao.head(15).sort_values("Tempo_medio_horas")["Tempo_medio_horas"].round(1),
            )
            fig.update_layout(height=500, margin=dict(l=20, r=20, t=55, b=20))
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Detalhamento por OPSStation")
        st.dataframe(ops_retencao, use_container_width=True, hide_index=True)

        cols_paradas = [
            "AWB Original",
            "AWB Normalizada",
            col_destination,
            col_ops,
            col_status,
            "SLA Real",
            "Prioridade",
            "Data Prevista_dt",
            "Horas sem movimentação",
            "Faixa Aging",
        ]
        cols_paradas = [c for c in cols_paradas if c is not None and c in df_aberto.columns]
        lista_paradas = df_aberto[cols_paradas].sort_values([col_ops, "Horas sem movimentação"], ascending=[True, False])
        st.subheader("Lista de AWBs paradas por OPSStation")
        st.dataframe(lista_paradas, use_container_width=True, hide_index=True)


# ============================================================
# ABA OCORRÊNCIAS
# ============================================================
with aba_ocorr:
    st.markdown('<div class="section-title">Avarias, extravios e cargas localizadas</div>', unsafe_allow_html=True)

    o1, o2, o3, o4 = st.columns(4)
    with o1:
        render_kpi("Avarias", format_int(avarias), f"{format_pct(avarias / total * 100 if total else 0)} sobre AWBs emitidas")
    with o2:
        render_kpi("Extravios (MSCA)", format_int(extravios), f"{format_pct(extravios / total * 100 if total else 0)} sobre AWBs emitidas")
    with o3:
        render_kpi("Found", format_int(found), f"{format_pct(found / total * 100 if total else 0)} sobre AWBs emitidas")
    with o4:
        render_kpi("Total ocorrências", format_int(len(df_ocorrencias)), f"{format_pct(len(df_ocorrencias) / total * 100 if total else 0)} da base")

    ocorr_status = pd.DataFrame(
        {
            "Tipo": ["Avaria", "Extravio MSCA", "Found"],
            "Quantidade": [avarias, extravios, found],
        }
    )
    fig = px.bar(ocorr_status, x="Tipo", y="Quantidade", title="Resumo de ocorrências", text="Quantidade")
    fig.update_layout(height=380, margin=dict(l=20, r=20, t=55, b=20))
    st.plotly_chart(fig, use_container_width=True)

    cols_ocorr = [
        "AWB Original",
        "AWB Normalizada",
        col_destination,
        col_ops,
        col_status,
        "Status Grupo",
        "SLA Real",
        "Data Emissão",
        "Data Prevista_dt",
        "Data Entrega_dt",
        "Avaria",
        "Extravio MSCA",
        "Found",
    ]
    cols_ocorr = [c for c in cols_ocorr if c is not None and c in df_ocorrencias.columns]
    st.subheader("Detalhamento das ocorrências")
    st.dataframe(df_ocorrencias[cols_ocorr], use_container_width=True, hide_index=True)


# ============================================================
# ABA EXPORTAÇÃO
# ============================================================
with aba_export:
    st.markdown('<div class="section-title">Base filtrada e exportações</div>', unsafe_allow_html=True)

    colunas_exibir = [
        "AWB Original",
        "AWB Normalizada",
        col_origin,
        col_destination,
        col_ops,
        col_status,
        col_status_en,
        "Status Grupo",
        "SLA Real",
        "Prioridade",
        col_billto,
        col_product,
        col_delivery_request,
        "Data Emissão",
        "ExecutionDateTime_dt",
        "ApproxSLA_dt",
        "Data Prevista_dt",
        "Data Entrega_dt",
        col_flt_no,
        "FltDt_dt",
        col_flt_origin,
        col_flt_destination,
        "Horas sem movimentação",
        "Aging Dias",
        "Faixa Aging",
        "Carga no destino final",
        "Peso",
        "Avaria",
        "Extravio MSCA",
        "Found",
        col_shipper,
        col_consignee,
    ]
    colunas_exibir = [c for c in colunas_exibir if c is not None and c in df_f.columns]

    st.dataframe(df_f[colunas_exibir], use_container_width=True, hide_index=True)

    # Bases de justificativa dos gráficos
    perf_dest_export = perf_dest.rename(columns={col_destination: "Destino"}).copy()
    emissao_dia_export = emissao_dia.copy()
    ops_export = pd.DataFrame()
    if not df_aberto.empty:
        ops_export = (
            df_aberto.groupby(col_ops)
            .agg(
                AWBs_em_transito=("AWB", "count"),
                Tempo_medio_horas=("Horas sem movimentação", "mean"),
                Atrasadas=("SLA Real", lambda s: (s == "Atrasada").sum()),
            )
            .reset_index()
            .sort_values("AWBs_em_transito", ascending=False)
        )

    awbs_status_sem_com_df = pd.DataFrame({"AWB não encontrada na Comission": awb_status_sem_com}) if 'awb_status_sem_com' in globals() else pd.DataFrame()
    awbs_com_sem_status_df = pd.DataFrame({"AWB não encontrada na Operation Status": awb_com_sem_status}) if 'awb_com_sem_status' in globals() else pd.DataFrame()

    abas_export = {
        "Base Filtrada": df_f[colunas_exibir],
        "Evolucao Diaria": emissao_dia_export,
        "Performance Destino": perf_dest_export,
        "OPSStation Retencao": ops_export,
        "Cargas em Risco": df_risco_view if 'df_risco_view' in globals() else pd.DataFrame(),
        "Sem Movimentacao": sem_mov_view if 'sem_mov_view' in globals() else pd.DataFrame(),
        "Ocorrencias": df_ocorrencias[cols_ocorr] if len(df_ocorrencias) and 'cols_ocorr' in globals() else pd.DataFrame(),
        "AWB sem Comission": awbs_status_sem_com_df,
        "AWB sem Status": awbs_com_sem_status_df,
    }

    excel_bytes = gerar_excel_multi(abas_export)
    st.download_button(
        label="📥 Baixar relatório completo em Excel",
        data=excel_bytes,
        file_name="relatorio_completo_performance_operacional_awb.xlsx",
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
        st.write("Colunas AWB Operation Status:", list(df_status_raw.columns))
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
        if not df_com_raw.empty:
            st.write("Colunas Comission Report Franchise:", list(df_com_raw.columns))
            st.write(
                {
                    "AWB": col_com_awb,
                    "Data prevista entrega": col_data_prevista,
                    "Data oficial entrega": col_data_entrega,
                    "Avaria BE": col_avaria,
                    "Extravio MSCA BG": col_extravio,
                    "Found BI": col_found,
                }
            )


# ============================================================
# RODAPÉ
# ============================================================
st.caption(
    "Dashboard desenvolvida para análise operacional: performance do cliente, controle de SLA, aging, ocorrências, ofensores e exportação de AWBs críticas."
)
