import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. CONFIGURACIÓN DE LA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema de Gestión de Licencias - Comuna de Los Reartes",
    page_icon="📋",
    layout="wide"
)

st.title("📋 Sistema de Gestión de Licencias del Personal")

# -----------------------------------------------------------------------------
# 2. CONEXIÓN A GOOGLE SHEETS
# -----------------------------------------------------------------------------
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    # Se utiliza ttl=0 para forzar la lectura actualizada en tiempo real
    df_licencias = conn.read(ttl=0)
except Exception as e:
    st.error(f"Error al conectar con la base de datos de Google Sheets: {e}")
    st.stop()

# -----------------------------------------------------------------------------
# 3. SANITIZACIÓN Y LIMPIEZA DE DATOS (EVITA ERRORES DE SUMA Y COMPARACIÓN)
# -----------------------------------------------------------------------------
if not df_licencias.empty:
    # Limpieza de nombres de columnas
    df_licencias.columns = df_licencias.columns.str.strip()

    # Normalizar columna Tipo_Licencia
    if 'Tipo_Licencia' in df_licencias.columns:
        df_licencias['Tipo_Licencia'] = df_licencias['Tipo_Licencia'].astype(str).str.strip()

    # Normalizar columna Empleado / Legajo / Nombre si existen
    for col in ['Empleado', 'Nombre', 'Legajo', 'Observaciones']:
        if col in df_licencias.columns:
            df_licencias[col] = df_licencias[col].astype(str).str.strip()

    # Conversión estricta a numérico de la columna 'Dias'
    if 'Dias' in df_licencias.columns:
        df_licencias['Dias'] = pd.to_numeric(df_licencias['Dias'], errors='coerce').fillna(0)

    # Conversión del Periodo / Año a String
    if 'Periodo' in df_licencias.columns:
        df_licencias['Periodo'] = df_licencias['Periodo'].astype(str).str.strip()
else:
    st.warning("La base de datos está vacía o no se pudo cargar la planilla.")
    st.stop()

# -----------------------------------------------------------------------------
# 4. BARRA LATERAL (FILTROS Y SELECCIÓN DE EMPLEADO)
# -----------------------------------------------------------------------------
st.sidebar.header("🔍 Filtros y Búsqueda")

# Filtro por Empleado (si existe la columna en el Sheets)
col_empleado = 'Empleado' if 'Empleado' in df_licencias.columns else ('Nombre' if 'Nombre' in df_licencias.columns else None)

if col_empleado:
    lista_empleados = ["Todos"] + sorted(df_licencias[col_empleado].unique().tolist())
    empleado_seleccionado = st.sidebar.selectbox("Seleccionar Empleado:", lista_empleados)
else:
    empleado_seleccionado = "Todos"

# Filtro por Año / Periodo
lista_periodos = sorted(df_licencias['Periodo'].unique().tolist(), reverse=True)
periodo_actual = str(datetime.now().year)
index_periodo = lista_periodos.index(periodo_actual) if periodo_actual in lista_periodos else 0
periodo_seleccionado = st.sidebar.selectbox("Periodo / Año:", lista_periodos, index=index_periodo)

# Aplicar filtros al DataFrame
df_filtrado = df_licencias.copy()

if periodo_seleccionado:
    df_filtrado = df_filtrado[df_filtrado['Periodo'] == periodo_seleccionado]

if col_empleado and empleado_seleccionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado[col_empleado] == empleado_seleccionado]

# -----------------------------------------------------------------------------
# 5. CÁLCULO MUNICIPAL / COMUNAL: DÍAS DE TRÁMITE
# -----------------------------------------------------------------------------
# Máximo anual permitido por normativa comunal
MAX_DIAS_TRAMITE = 8

# Máscara exacta para evitar fallos de mayúsculas/minúsculas o espacios extra
mask_tramite = (
    (df_filtrado['Tipo_Licencia'].str.lower() == 'día de trámite') | 
    (df_filtrado['Tipo_Licencia'].str.lower() == 'dia de tramite')
)

total_dias_tramite = int(df_filtrado.loc[mask_tramite, 'Dias'].sum())

# Métrica / Banner superior
if empleado_seleccionado != "Todos":
    st.info(f"📋 **Días de Trámite solicitados en {periodo_seleccionado} para {empleado_seleccionado}:** {total_dias_tramite} / {MAX_DIAS_TRAMITE} días máximos anuales.")
else:
    st.info(f"📋 **Total Días de Trámite registrados en {periodo_seleccionado}:** {total_dias_tramite} días acumulados globalmente.")

# -----------------------------------------------------------------------------
# 6. RESUMEN DE LICENCIAS POR TIPO (MÉTRICAS RÁPIDAS)
# -----------------------------------------------------------------------------
st.subheader("📊 Resumen de Consumo de Licencias")

col1, col2, col3, col4 = st.columns(4)

totales_por_tipo = df_filtrado.groupby(df_filtrado['Tipo_Licencia'].str.title())['Dias'].sum().to_dict()

with col1:
    st.metric("Días de Trámite", f"{total_dias_tramite} / {MAX_DIAS_TRAMITE}")

with col2:
    dias_ordinaria = int(totales_por_tipo.get('Licencia Anual Ordinaria', totales_por_tipo.get('Anual Ordinaria', 0)))
    st.metric("Anual Ordinaria", f"{dias_ordinaria} días")

with col3:
    dias_medica = int(totales_por_tipo.get('Licencia Médica', totales_por_tipo.get('Medica', 0)))
    st.metric("Licencia Médica", f"{dias_medica} días")

with col4:
    total_general = int(df_filtrado['Dias'].sum())
    st.metric("Total Días Solicitados", f"{total_general} días")

st.markdown("---")

# -----------------------------------------------------------------------------
# 7. TABLA DE HISTORIAL DE LICENCIAS CONSUMIDAS
# -----------------------------------------------------------------------------
st.subheader("📜 Historial de Licencias Consumidas")

if not df_filtrado.empty:
    # Ordenar por fecha si existe columna Fecha_Inicio
    if 'Fecha_Inicio' in df_filtrado.columns:
        df_filtrado['Fecha_Inicio_DT'] = pd.to_datetime(df_filtrado['Fecha_Inicio'], errors='coerce', dayfirst=True)
        df_filtrado = df_filtrado.sort_values(by='Fecha_Inicio_DT', ascending=False).drop(columns=['Fecha_Inicio_DT'])

    st.dataframe(
        df_filtrado,
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No hay registros que coincidan con los filtros seleccionados.")

# -----------------------------------------------------------------------------
# 8. FORMULARIO PARA REGISTRAR NUEVA LICENCIA
# -----------------------------------------------------------------------------
with st.expander("➕ Registrar Nueva Licencia"):
    with st.form("form_nueva_licencia", clear_on_submit=True):
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            emp_input = st.text_input("Nombre / Empleado:")
            tipo_input = st.selectbox("Tipo de Licencia:", [
                "Día de Trámite",
                "Licencia Anual Ordinaria",
                "Licencia Médica",
                "Razones Particulares",
                "Capacitación",
                "Otra"
            ])
            periodo_input = st.text_input("Periodo (Año):", value=str(datetime.now().year))

        with col_f2:
            f_inicio = st.date_input("Fecha Inicio:")
            f_fin = st.date_input("Fecha Fin:")
            dias_input = st.number_input("Cantidad de Días:", min_value=0.5, step=0.5, value=1.0)
            obs_input = st.text_input("Observaciones:")

        btn_guardar = st.form_submit_button("Guardar Licencia")

        if btn_guardar:
            nueva_fila = pd.DataFrame([{
                "Periodo": periodo_input,
                "Empleado": emp_input,
                "Tipo_Licencia": tipo_input,
                "Fecha_Inicio": f_inicio.strftime("%d/%m/%Y"),
                "Fecha_Fin": f_fin.strftime("%d/%m/%Y"),
                "Dias": dias_input,
                "Observaciones": obs_input
            }])
            
            # Concatenar y actualizar Google Sheets
            df_actualizado = pd.concat([df_licencias, nueva_fila], ignore_index=True)
            try:
                conn.update(data=df_actualizado)
                st.success("¡Licencia registrada correctamente en Google Sheets!")
                st.rerun()
            except Exception as err:
                st.error(f"Error al guardar en Google Sheets: {err}")
