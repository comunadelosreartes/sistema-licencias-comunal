import streamlit as st
import pandas as pd
from datetime import date
from streamlit_gsheets import GSheetsConnection

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema Comunal de Licencias",
    page_icon="📜",
    layout="wide"
)

# Conexión con la pestaña Historial_Licencias que acabamos de crear
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_datos():
    try:
        df = conn.read(worksheet="Historial_Licencias", ttl=0)
        # Limpiar datos
        if not df.empty and "Legajo" in df.columns:
            df["Legajo"] = df["Legajo"].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"Error al leer la base de Google Sheets: {e}")
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
        
        # Crear lista combinada Legajo - Nombre para el selector
        df_licencias["Combo_Agente"] = df_licencias["Legajo"].astype(str) + " - " + df_licencias["Empleado"].astype(str)
        lista_agentes = sorted(df_licencias["Combo_Agente"].unique().tolist())

        col_search, _ = st.columns([2, 2])
        with col_search:
            agente_sel = st.selectbox("🔎 Buscar Agente (Legajo o Nombre):", options=lista_agentes)

        legajo_elegido = agente_sel.split(" - ")[0].strip()
        df_agente = df_licencias[df_licencias["Legajo"] == legajo_elegido].copy()

        # Datos del agente
        nombre_agente = df_agente["Empleado"].iloc[0] if not df_agente.empty else "N/A"
        area_agente = df_agente["Area"].iloc[0] if ("Area" in df_agente.columns and not df_agente.empty) else "N/A"
        total_dias = pd.to_numeric(df_agente["Dias"], errors="coerce").sum() if not df_agente.empty else 0

        st.divider()

        # Resumen general
        c1, c2, c3 = st.columns(3)
        c1.metric("N° Legajo", legajo_elegido)
        c2.metric("Área / Sector", area_agente)
        c3.metric("Total Días Tomados (Histórico)", f"{int(total_dias)} días")

        st.subheader(f"📋 Registros de {nombre_agente}")
        
        if not df_agente.empty:
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
            st.info("No hay licencias registradas para este legajo.")

    else:
        st.info("💡 La base de datos aún no tiene licencias registradas. Utilice la opción '➕ Cargar Licencia' del menú para agregar la primera.")

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

        obs_in = st.text_input("Observaciones / N° Resolución o Nota:", placeholder="Ej: Tramo completo / Solicitud 45")

        btn_guardar = st.form_submit_button("💾 Guardar Licencia en Google Sheets", type="primary")

        if btn_guardar:
            if not legajo_in.strip() or not nombre_in.strip():
                st.error("⚠️ El Legajo y el Nombre del Empleado son obligatorios.")
            else:
                nuevo_reg = pd.DataFrame([{
                    "Legajo": legajo_in.strip(),
                    "Empleado": nombre_in.strip(),
                    "Area": area_in.strip(),
                    "Tipo_Licencia": tipo_in,
                    "Periodo": periodo_in.strip(),
                    "Fecha_Inicio": f_inicio_in.strftime("%Y-%m-%d"),
                    "Fecha_Fin": f_fin_in.strftime("%Y-%m-%d"),
                    "Dias": int(dias_in),
                    "Observaciones": obs_in.strip()
                }])

                try:
                    df_actual = cargar_datos()
                    df_unido = pd.concat([df_actual, nuevo_reg], ignore_index=True)
                    conn.update(worksheet="Historial_Licencias", data=df_unido)
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
        st.info("La base de datos está vacía.")