import streamlit as st
import pandas as pd
from datetime import date
from google.oauth2.service_account import Credentials
import gspread

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema Comunal de Licencias",
    page_icon="📜",
    layout="wide"
)

# -----------------------------------------------------------------------------
# CONEXIÓN A GOOGLE SHEETS
# -----------------------------------------------------------------------------
@st.cache_resource
def obtener_cliente_gspread():
    try:
        sa_info = dict(st.secrets["service_account"])
        
        # Corregir saltos de línea de la private_key
        if "private_key" in sa_info:
            key = sa_info["private_key"]
            key = key.replace("\\n", "\n")
            if not key.startswith("-----BEGIN PRIVATE KEY-----"):
                key = "-----BEGIN PRIVATE KEY-----\n" + key
            if not key.endswith("-----END PRIVATE KEY-----\n") and not key.endswith("-----END PRIVATE KEY-----"):
                key = key + "\n-----END PRIVATE KEY-----\n"
            sa_info["private_key"] = key

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error de Autenticación: {e}")
        return None

def cargar_datos():
    gc = obtener_cliente_gspread()
    if not gc:
        return pd.DataFrame()
    
    try:
        sheet_url = st.secrets["spreadsheet_url"]
        sh = gc.open_by_url(sheet_url)
        worksheet = sh.worksheet("Historial_Licencias")
        
        # Leer filas
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        if not df.empty and "Legajo" in df.columns:
            df["Legajo"] = df["Legajo"].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"Error al leer la planilla: {e}")
        return pd.DataFrame(columns=[
            "Legajo", "Empleado", "Area", "Tipo_Licencia", 
            "Periodo", "Fecha_Inicio", "Fecha_Fin", "Dias", "Observaciones"
        ])

df_licencias = cargar_datos()

# -----------------------------------------------------------------------------
# MENÚ LATERAL Y NAVEGACIÓN
# -----------------------------------------------------------------------------
st.sidebar.title("📌 Menú Principal")
opcion = st.sidebar.radio(
    "Seleccione una opción:",
    ["📜 Historial por Legajo", "➕ Cargar Licencia", "📊 Ver Base Completa"]
)

# =============================================================================
# OPCIÓN 1: HISTORIAL Y FICHA POR LEGAJO
# =============================================================================
if opcion == "📜 Historial por Legajo":
    st.title("📜 Ficha Histórica de Licencias")
    st.caption("Consulte el detalle de vacaciones y licencias gozadas por cada agente comunal.")

    if not df_licencias.empty and "Legajo" in df_licencias.columns and df_licencias["Legajo"].dropna().count() > 0:
        df_licencias["Combo_Agente"] = df_licencias["Legajo"].astype(str) + " - " + df_licencias["Empleado"].astype(str)
        lista_agentes = sorted(df_licencias["Combo_Agente"].unique().tolist())

        col_search, _ = st.columns([2, 2])
        with col_search:
            agente_sel = st.selectbox("🔎 Buscar Agente (Legajo o Nombre):", options=lista_agentes)

        legajo_elegido = agente_sel.split(" - ")[0].strip()
        df_agente = df_licencias[df_licencias["Legajo"] == legajo_elegido].copy()

        nombre_agente = df_agente["Empleado"].iloc[0] if not df_agente.empty else "N/A"
        area_agente = df_agente["Area"].iloc[0] if ("Area" in df_agente.columns and not df_agente.empty) else "N/A"
        total_dias = pd.to_numeric(df_agente["Dias"], errors="coerce").sum() if not df_agente.empty else 0

        st.divider()

        c1, c2, c3 = st.columns(3)
        c1.metric("N° Legajo", legajo_elegido)
        c2.metric("Área / Sector", area_agente)
        c3.metric("Total Días Tomados (Histórico)", f"{int(total_dias)} días")

        st.subheader(f"📋 Registros de {nombre_agente}")
        
        columnas_visibles = ["Periodo", "Tipo_Licencia", "Fecha_Inicio", "Fecha_Fin", "Dias", "Observaciones"]
        df_mostrar = df_agente[columnas_visibles].sort_values(by="Periodo", ascending=False)
        
        st.dataframe(
            df_mostrar,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Periodo": "Período / Año",
                "Tipo_Licencia": "Tipo",
                "Fecha_Inicio": "Desde",
                "Fecha_Fin": "Hasta",
                "Dias": "Días",
                "Observaciones": "Observaciones / Ref."
            }
        )
    else:
        st.info("💡 La base de datos está conectada pero aún no tiene licencias cargadas. Usá la opción '➕ Cargar Licencia' para agregar la primera.")

# =============================================================================
# OPCIÓN 2: FORMULARIO DE CARGA DE LICENCIA
# =============================================================================
elif opcion == "➕ Cargar Licencia":
    st.title("➕ Registrar Nueva Licencia / Período Histórico")
    st.caption("Asiente períodos de vacaciones pasados o licencias vigentes en la base general.")

    with st.form("form_licencia", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            legajo_in = st.text_input("N° de Legajo:")
            nombre_in = st.text_input("Nombre y Apellido del Empleado:")
            area_in = st.text_input("Área / Sector:", value="Obras Públicas")
        with col2:
            tipo_in = st.selectbox(
                "Tipo de Licencia:", 
                ["Ordinaria / Vacaciones", "Razones Particulares", "Salud / Médica", "Especial"]
            )
            periodo_in = st.text_input("Período / Año al que corresponde:", value="2024")
            dias_in = st.number_input("Días Tomados:", min_value=1, max_value=60, value=14)

        col3, col4 = st.columns(2)
        with col3:
            f_inicio_in = st.date_input("Fecha Inicio (Desde):", value=date.today())
        with col4:
            f_fin_in = st.date_input("Fecha Fin (Hasta):", value=date.today())

        obs_in = st.text_input("Observaciones / N° Resolución o Nota:", placeholder="Ej: Tramo completo")

        btn_guardar = st.form_submit_button("💾 Guardar Licencia en Google Sheets", type="primary")

        if btn_guardar:
            if not legajo_in.strip() or not nombre_in.strip():
                st.error("⚠️ El Legajo y el Nombre del Empleado son obligatorios.")
            else:
                nuevo_registro = [
                    legajo_in.strip(),
                    nombre_in.strip(),
                    area_in.strip(),
                    tipo_in,
                    periodo_in.strip(),
                    f_inicio_in.strftime("%Y-%m-%d"),
                    f_fin_in.strftime("%Y-%m-%d"),
                    int(dias_in),
                    obs_in.strip()
                ]

                try:
                    gc = obtener_cliente_gspread()
                    sh = gc.open_by_url(st.secrets["spreadsheet_url"])
                    ws = sh.worksheet("Historial_Licencias")
                    ws.append_row(nuevo_registro)
                    st.success(f"🎉 ¡Licencia registrada correctamente para {nombre_in.strip()}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar en Google Sheets: {e}")

# =============================================================================
# OPCIÓN 3: VER BASE COMPLETA
# =============================================================================
elif opcion == "📊 Ver Base Completa":
    st.title("📊 Base Completa de Licencias")
    st.caption("Visión global de todos los registros asentados en el sistema.")

    if not df_licencias.empty:
        st.dataframe(df_licencias, use_container_width=True, hide_index=True)
    else:
        st.info("La base de datos no contiene registros.")
