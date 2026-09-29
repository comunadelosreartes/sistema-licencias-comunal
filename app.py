import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import numpy as np
from datetime import datetime, date

# Configuración de página
st.set_page_config(page_title="Sistema de Licencias Comunal", page_icon="📜", layout="wide")

# Conexión a Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def cargar_datos():
    # Carga de solapas
    df_emp = conn.read(worksheet="Empleados")
    df_saldos = conn.read(worksheet="Saldos_Iniciales")
    df_hist = conn.read(worksheet="Historial_Licencias")
    df_feriados = conn.read(worksheet="Feriados")
    df_config = conn.read(worksheet="Configuracion")
    
    return df_emp, df_saldos, df_hist, df_feriados, df_config

try:
    df_emp, df_saldos, df_hist, df_feriados, df_config = cargar_datos()
except Exception as e:
    st.error(f"Error al conectar con Google Sheets. Verifique la estructura de solapas: {e}")
    st.stop()

# --- HELPER FUNCTIONS ---

def obtener_config(parametro, valor_default):
    if not df_config.empty and 'Parametro' in df_config.columns:
        res = df_config[df_config['Parametro'] == parametro]
        if not res.empty:
            return float(res.iloc[0]['Valor'])
    return valor_default

MAX_TRAMITE_ANUAL = int(obtener_config("MAX_DIAS_TRAMITE_ANUAL", 8))
MAX_TRAMITE_MENSUAL = int(obtener_config("MAX_DIAS_TRAMITE_MENSUAL", 2))

def obtener_feriados_set():
    if not df_feriados.empty and 'Fecha' in df_feriados.columns:
        return set(pd.to_datetime(df_feriados['Fecha']).dt.date)
    return set()

FERIADOS_SET = obtener_feriados_set()

def calcular_dias_habiles(inicio, fin):
    curr = inicio
    dias = 0
    while curr <= fin:
        if curr.weekday() < 5 and curr not in FERIADOS_SET:
            dias += 1
        curr += pd.Timedelta(days=1)
    return dias

def calcular_dias_estatuto(fecha_antiguedad, anio_periodo):
    if pd.isna(fecha_antiguedad):
        return 15
    try:
        fecha_ant = pd.to_datetime(fecha_antiguedad, format="%d/%m/%Y").date()
    except:
        try:
            fecha_ant = pd.to_datetime(fecha_antiguedad).date()
        except:
            return 15
            
    corte = date(anio_periodo, 12, 31)
    dias_ant = (corte - fecha_ant).days
    anios = dias_ant / 365.25

    if anios < 0.5:
        meses = max(1, int(np.ceil(dias_ant / 30.43)))
        return min(meses, 15)
    elif anios <= 5:
        return 15
    elif anios <= 10:
        return 20
    elif anios <= 15:
        return 25
    elif anios <= 25:
        return 30
    else:
        return 35

# --- MENU PRINCIPAL ---
st.sidebar.title("📌 Menú Principal")
opcion = st.sidebar.radio("Seleccione una opción:", [
    "📜 Historial y Saldos por Legajo",
    "➕ Cargar Licencia",
    "📊 Ver Base Completa"
])

# Limpieza y preparación de datos de empleados
df_emp_activos = df_emp[df_emp['ACTIVO'].astype(str).str.upper() == 'SI'].copy() if 'ACTIVO' in df_emp.columns else df_emp.copy()
df_emp_activos['LEGAJO'] = df_emp_activos['LEGAJO'].astype(str)
df_emp_activos['NOMBRE_COMPLETO'] = df_emp_activos['APELLIDO'].astype(str) + ", " + df_emp_activos['NOMBRE'].astype(str)

# --- OPCIÓN 1: HISTORIAL Y SALDOS POR LEGAJO ---
if opcion == "📜 Historial y Saldos por Legajo":
    st.title("📜 Ficha de Licencias y Saldos Disponibles")
    
    opciones_empleados = dict(zip(df_emp_activos['LEGAJO'], df_emp_activos['LEGAJO'] + " - " + df_emp_activos['NOMBRE_COMPLETO']))
    legajo_sel = st.selectbox("Seleccione un Agente:", options=list(opciones_empleados.keys()), format_func=lambda x: opciones_empleados[x])
    
    if legajo_sel:
        emp_info = df_emp_activos[df_emp_activos['LEGAJO'] == legajo_sel].iloc[0]
        st.subheader(f"👤 {emp_info['NOMBRE_COMPLETO']} (Legajo: {legajo_sel})")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Área", str(emp_info.get('AREA', 'N/A')))
        col2.metric("Fecha Antigüedad", str(emp_info.get('FECHA ANTIGUEDAD', 'N/A')))
        
        # Cálculo de Saldos
        saldos_user = df_saldos[df_saldos['Legajo'].astype(str) == legajo_sel].copy() if not df_saldos.empty else pd.DataFrame()
        hist_user = df_hist[df_hist['Legajo'].astype(str) == legajo_sel].copy() if not df_hist.empty else pd.DataFrame()
        
        st.markdown("---")
        st.subheader("🟢 Estado de Saldos de Vacaciones")
        
        # Agrupar tomados por período
        tomados_por_periodo = {}
        if not hist_user.empty and 'Tipo_Licencia' in hist_user.columns:
            vacs = hist_user[hist_user['Tipo_Licencia'] == 'Vacaciones']
            if not vacs.empty and 'Periodo' in vacs.columns:
                tomados_por_periodo = vacs.groupby('Periodo')['Dias'].sum().to_dict()
                
        periodos = sorted(list(set(saldos_user['Periodo'].tolist() if not saldos_user.empty else [2024, 2025, 2026])))
        
        resumen_saldos = []
        for p in periodos:
            p = int(p)
            asig = saldos_user[saldos_user['Periodo'] == p]['Dias_Asignados'].sum() if not saldos_user.empty and p in saldos_user['Periodo'].values else calcular_dias_estatuto(emp_info.get('FECHA ANTIGUEDAD'), p)
            tomados = tomados_por_periodo.get(p, 0)
            disp = asig - tomados
            resumen_saldos.append({"Período": p, "Asignados": asig, "Tomados": tomados, "Disponible": disp})
            
        df_res_saldos = pd.DataFrame(resumen_saldos)
        st.dataframe(df_res_saldos, use_container_width=True)
        
        # Control Trámites
        if not hist_user.empty and 'Tipo_Licencia' in hist_user.columns:
            tramites_anio = hist_user[(hist_user['Tipo_Licencia'] == 'Día de Trámite') & (pd.to_datetime(hist_user['Fecha_Inicio']).dt.year == date.today().year)]['Dias'].sum()
        else:
            tramites_anio = 0
            
        st.info(f"📋 **Días de Trámite tomados en {date.today().year}:** {tramites_anio} / {MAX_TRAMITE_ANUAL} días máximos anuales.")

        st.markdown("---")
        st.subheader("📜 Historial de Licencias Consumidas")
        if not hist_user.empty:
            st.dataframe(hist_user[['Fecha_Inicio', 'Fecha_Fin', 'Dias', 'Tipo_Licencia', 'Periodo', 'Observaciones']], use_container_width=True)
        else:
            st.write("No hay licencias registradas para este legajo.")

# --- OPCIÓN 2: CARGAR LICENCIA ---
elif opcion == "➕ Cargar Licencia":
    st.title("➕ Registrar Nueva Licencia")
    
    opciones_empleados = dict(zip(df_emp_activos['LEGAJO'], df_emp_activos['LEGAJO'] + " - " + df_emp_activos['NOMBRE_COMPLETO']))
    
    with st.form("form_licencia"):
        legajo_sel = st.selectbox("Empleado:", options=list(opciones_empleados.keys()), format_func=lambda x: opciones_empleados[x])
        tipo_lic = st.selectbox("Tipo de Licencia:", ["Vacaciones", "Día de Trámite", "Licencia Médica", "Razones Particulares", "Otra"])
        
        col_f1, col_f2 = st.columns(2)
        f_inicio = col_f1.date_input("Fecha de Inicio:", value=date.today())
        f_fin = col_f2.date_input("Fecha de Fin:", value=date.today())
        
        obs = st.text_input("Observaciones:")
        
        submitted = st.form_submit_button("💾 Guardar Licencia en Google Sheets")
        
        if submitted:
            if f_fin < f_inicio:
                st.error("La fecha de fin no puede ser anterior a la fecha de inicio.")
            else:
                dias_habiles = calcular_dias_habiles(f_inicio, f_fin)
                emp_info = df_emp_activos[df_emp_activos['LEGAJO'] == legajo_sel].iloc[0]
                
                # Validaciones Trámite Particular
                valido = True
                if tipo_lic == "Día de Trámite":
                    hist_user = df_hist[df_hist['Legajo'].astype(str) == legajo_sel] if not df_hist.empty else pd.DataFrame()
                    if not hist_user.empty:
                        tramites_anio = hist_user[(hist_user['Tipo_Licencia'] == 'Día de Trámite') & (pd.to_datetime(hist_user['Fecha_Inicio']).dt.year == f_inicio.year)]['Dias'].sum()
                        if tramites_anio + dias_habiles > MAX_TRAMITE_ANUAL:
                            st.error(f"Supera el máximo anual de Días de Trámite ({MAX_TRAMITE_ANUAL} días). Ya posee {tramites_anio} tomados.")
                            valido = False
                            
                if valido:
                    nueva_fila = pd.DataFrame([{
                        "Legajo": legajo_sel,
                        "Empleado": emp_info['NOMBRE_COMPLETO'],
                        "Area": emp_info.get('AREA', ''),
                        "Tipo_Licencia": tipo_lic,
                        "Periodo": f_inicio.year,
                        "Fecha_Inicio": f_inicio.strftime("%Y-%m-%d"),
                        "Fecha_Fin": f_fin.strftime("%Y-%m-%d"),
                        "Dias": dias_habiles,
                        "Observaciones": obs
                    }])
                    
                    df_actualizado = pd.concat([df_hist, nueva_fila], ignore_index=True)
                    conn.update(worksheet="Historial_Licencias", data=df_actualizado)
                    st.success(f"¡Licencia registrada con éxito! ({dias_habiles} días hábiles computados)")
                    st.cache_data.clear()

# --- OPCIÓN 3: VER BASE COMPLETA ---
elif opcion == "📊 Ver Base Completa":
    st.title("📊 Base Completa de Licencias Registradas")
    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True)
    else:
        st.info("Aún no hay licencias cargadas en la base de datos.")
