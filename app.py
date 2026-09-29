import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime
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
# CONEXIÓN A GOOGLE SHEETS VIA GSPREAD (SECRETS EXISTENTES)
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

@st.cache_data(ttl=60)
def cargar_todas_las_solapas():
    gc = obtener_cliente_gspread()
    if not gc:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    try:
        sheet_url = st.secrets["spreadsheet_url"]
        sh = gc.open_by_url(sheet_url)
        
        # Helper para leer solapas de forma segura
        def leer_worksheet(nombre):
            try:
                ws = sh.worksheet(nombre)
                return pd.DataFrame(ws.get_all_records())
            except Exception:
                return pd.DataFrame()

        df_emp = leer_worksheet("Empleados")
        df_saldos = leer_worksheet("Saldos_Iniciales")
        df_hist = leer_worksheet("Historial_Licencias")
        df_feriados = leer_worksheet("Feriados")
        df_config = leer_worksheet("Configuracion")

        # Normalizar Legajo a string
        if not df_emp.empty and "LEGAJO" in df_emp.columns:
            df_emp["LEGAJO"] = df_emp["LEGAJO"].astype(str).str.strip()
        if not df_saldos.empty and "Legajo" in df_saldos.columns:
            df_saldos["Legajo"] = df_saldos["Legajo"].astype(str).str.strip()
        if not df_hist.empty and "Legajo" in df_hist.columns:
            df_hist["Legajo"] = df_hist["Legajo"].astype(str).str.strip()

        return df_emp, df_saldos, df_hist, df_feriados, df_config

    except Exception as e:
        st.error(f"Error al acceder a las solapas de Google Sheets: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_emp, df_saldos, df_hist, df_feriados, df_config = cargar_todas_las_solapas()

# -----------------------------------------------------------------------------
# FUNCIONES AUXILIARES DE CÁLCULO Y REGLAS (ESTATUTO & CONFIGURACIÓN)
# -----------------------------------------------------------------------------
def obtener_config(parametro, valor_default):
    if not df_config.empty and 'Parametro' in df_config.columns:
        res = df_config[df_config['Parametro'] == parametro]
        if not res.empty:
            try:
                return float(res.iloc[0]['Valor'])
            except:
                return valor_default
    return valor_default

MAX_TRAMITE_ANUAL = int(obtener_config("MAX_DIAS_TRAMITE_ANUAL", 8))
MAX_TRAMITE_MENSUAL = int(obtener_config("MAX_DIAS_TRAMITE_MENSUAL", 2))

def obtener_feriados_set():
    if not df_feriados.empty and 'Fecha' in df_feriados.columns:
        try:
            return set(pd.to_datetime(df_feriados['Fecha']).dt.date)
        except:
            return set()
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
    if pd.isna(fecha_antiguedad) or not fecha_antiguedad:
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

# -----------------------------------------------------------------------------
# MENÚ LATERAL Y NAVEGACIÓN
# -----------------------------------------------------------------------------
st.sidebar.title("📌 Menú Principal")
opcion = st.sidebar.radio(
    "Seleccione una opción:",
    ["📜 Historial y Saldos por Legajo", "➕ Cargar Licencia", "📊 Ver Base Completa"]
)

# Preparación de datos de empleados
if not df_emp.empty:
    df_emp_activos = df_emp[df_emp['ACTIVO'].astype(str).str.upper() == 'SI'].copy() if 'ACTIVO' in df_emp.columns else df_emp.copy()
    if 'APELLIDO' in df_emp_activos.columns and 'NOMBRE' in df_emp_activos.columns:
        df_emp_activos['NOMBRE_COMPLETO'] = df_emp_activos['APELLIDO'].astype(str) + ", " + df_emp_activos['NOMBRE'].astype(str)
    else:
        df_emp_activos['NOMBRE_COMPLETO'] = df_emp_activos['LEGAJO'].astype(str)
else:
    df_emp_activos = pd.DataFrame()

# =============================================================================
# OPCIÓN 1: HISTORIAL Y SALDOS POR LEGAJO
# =============================================================================
if opcion == "📜 Historial y Saldos por Legajo":
    st.title("📜 Ficha de Licencias y Saldos Disponibles")
    st.caption("Consulte el saldo de vacaciones según estatuto y el historial de licencias gozadas.")

    if not df_emp_activos.empty:
        opciones_empleados = dict(zip(df_emp_activos['LEGAJO'], df_emp_activos['LEGAJO'] + " - " + df_emp_activos['NOMBRE_COMPLETO']))
        legajo_sel = st.selectbox("🔎 Seleccione o busque un Agente:", options=list(opciones_empleados.keys()), format_func=lambda x: opciones_empleados[x])
        
        if legajo_sel:
            emp_info = df_emp_activos[df_emp_activos['LEGAJO'] == legajo_sel].iloc[0]
            st.subheader(f"👤 {emp_info['NOMBRE_COMPLETO']} (Legajo: {legajo_sel})")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Área / Sector", str(emp_info.get('AREA', 'N/A')))
            c2.metric("Fecha Antigüedad", str(emp_info.get('FECHA ANTIGUEDAD', 'N/A')))
            
            # Filtrar registros del usuario
            saldos_user = df_saldos[df_saldos['Legajo'] == legajo_sel].copy() if not df_saldos.empty else pd.DataFrame()
            hist_user = df_hist[df_hist['Legajo'] == legajo_sel].copy() if not df_hist.empty else pd.DataFrame()
            
            st.divider()
            st.subheader("🟢 Estado de Saldos de Vacaciones")
            
            # Días tomados por período (filtrando Vacaciones / Ordinaria)
            tomados_por_periodo = {}
            if not hist_user.empty and 'Tipo_Licencia' in hist_user.columns:
                vacs = hist_user[hist_user['Tipo_Licencia'].astype(str).str.contains("Vacaciones|Ordinaria", case=False, na=False)]
                if not vacs.empty and 'Periodo' in vacs.columns:
                    tomados_por_periodo = vacs.groupby('Periodo')['Dias'].sum().to_dict()
                    
            periodos = sorted(list(set(saldos_user['Periodo'].tolist() if not saldos_user.empty else [2024, 2025, 2026])))
            
            resumen_saldos = []
            for p in periodos:
                try:
                    p_num = int(p)
                except:
                    p_num = p
                
                if not saldos_user.empty and p in saldos_user['Periodo'].values:
                    asig = saldos_user[saldos_user['Periodo'] == p]['Dias_Asignados'].sum()
                else:
                    asig = calcular_dias_estatuto(emp_info.get('FECHA ANTIGUEDAD'), p_num if isinstance(p_num, int) else 2026)
                
                tomados = tomados_por_periodo.get(p, 0)
                disp = asig - tomados
                resumen_saldos.append({"Período": p, "Días Asignados": asig, "Días Tomados": tomados, "Saldo Disponible": disp})
                
            df_res_saldos = pd.DataFrame(resumen_saldos)
            st.dataframe(df_res_saldos, use_container_width=True, hide_index=True)
            
            # Días de Trámite tomados
            if not hist_user.empty and 'Tipo_Licencia' in hist_user.columns:
                tramites_anio = hist_user[(hist_user['Tipo_Licencia'].astype(str).str.contains("Trámite", case=False, na=False)) & (pd.to_datetime(hist_user['Fecha_Inicio'], errors='coerce').dt.year == date.today().year)]['Dias'].sum()
            else:
                tramites_anio = 0
                
            st.info(f"📋 **Días de Trámite solicitados en {date.today().year}:** {int(tramites_anio)} / {MAX_TRAMITE_ANUAL} días máximos anuales.")

            st.divider()
            st.subheader("📜 Historial de Licencias Consumidas")
            if not hist_user.empty:
                cols_vis = [c for c in ['Periodo', 'Tipo_Licencia', 'Fecha_Inicio', 'Fecha_Fin', 'Dias', 'Observaciones'] if c in hist_user.columns]
                st.dataframe(hist_user[cols_vis], use_container_width=True, hide_index=True)
            else:
                st.write("No hay licencias registradas para este legajo.")
    else:
        st.info("No se encontraron datos en la solapa 'Empleados'.")

# =============================================================================
# OPCIÓN 2: FORMULARIO DE CARGA DE LICENCIA
# =============================================================================
elif opcion == "➕ Cargar Licencia":
    st.title("➕ Registrar Nueva Licencia")
    st.caption("Asiente solicitudes de licencias o vacaciones en la base de datos.")

    if not df_emp_activos.empty:
        opciones_empleados = dict(zip(df_emp_activos['LEGAJO'], df_emp_activos['LEGAJO'] + " - " + df_emp_activos['NOMBRE_COMPLETO']))
        
        with st.form("form_licencia", clear_on_submit=True):
            legajo_sel = st.selectbox("Empleado:", options=list(opciones_empleados.keys()), format_func=lambda x: opciones_empleados[x])
            tipo_lic = st.selectbox("Tipo de Licencia:", ["Vacaciones", "Día de Trámite", "Licencia Médica", "Razones Particulares", "Otra"])
            
            col_f1, col_f2 = st.columns(2)
            f_inicio = col_f1.date_input("Fecha de Inicio (Desde):", value=date.today())
            f_fin = col_f2.date_input("Fecha de Fin (Hasta):", value=date.today())
            
            obs = st.text_input("Observaciones / N° Resolución o Nota:")
            
            btn_guardar = st.form_submit_button("💾 Guardar Licencia en Google Sheets", type="primary")
            
            if btn_guardar:
                if f_fin < f_inicio:
                    st.error("⚠️ La fecha de fin no puede ser anterior a la fecha de inicio.")
                else:
                    dias_habiles = calcular_dias_habiles(f_inicio, f_fin)
                    emp_info = df_emp_activos[df_emp_activos['LEGAJO'] == legajo_sel].iloc[0]
                    
                    valido = True
                    if tipo_lic == "Día de Trámite":
                        hist_user = df_hist[df_hist['Legajo'] == legajo_sel] if not df_hist.empty else pd.DataFrame()
                        if not hist_user.empty and 'Tipo_Licencia' in hist_user.columns:
                            tramites_anio = hist_user[(hist_user['Tipo_Licencia'].astype(str).str.contains("Trámite", case=False, na=False)) & (pd.to_datetime(hist_user['Fecha_Inicio'], errors='coerce').dt.year == f_inicio.year)]['Dias'].sum()
                            if tramites_anio + dias_habiles > MAX_TRAMITE_ANUAL:
                                st.error(f"⚠️ Supera el máximo anual de Días de Trámite ({MAX_TRAMITE_ANUAL} días). Ya posee {int(tramites_anio)} tomados en el año.")
                                valido = False
                                
                    if valido:
                        nuevo_registro = [
                            str(legajo_sel),
                            str(emp_info['NOMBRE_COMPLETO']),
                            str(emp_info.get('AREA', '')),
                            tipo_lic,
                            str(f_inicio.year),
                            f_inicio.strftime("%Y-%m-%d"),
                            f_fin.strftime("%Y-%m-%d"),
                            int(dias_habiles),
                            obs.strip()
                        ]
                        
                        try:
                            gc = obtener_cliente_gspread()
                            sh = gc.open_by_url(st.secrets["spreadsheet_url"])
                            ws = sh.worksheet("Historial_Licencias")
                            ws.append_row(nuevo_registro)
                            st.success(f"🎉 ¡Licencia registrada correctamente! ({dias_habiles} días hábiles computados)")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al guardar en Google Sheets: {e}")
    else:
        st.info("Cargue la información de empleados antes de registrar licencias.")

# =============================================================================
# OPCIÓN 3: VER BASE COMPLETA
# =============================================================================
elif opcion == "📊 Ver Base Completa":
    st.title("📊 Base Completa de Licencias Registradas")
    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay licencias cargadas en la base de datos.")
