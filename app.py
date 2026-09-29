import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread
import streamlit.components.v1 as components

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
        if "private_key" in sa_info:
            key = sa_info["private_key"].replace("\\n", "\n")
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

def obtener_feriados_set():
    if not df_feriados.empty and 'Fecha' in df_feriados.columns:
        try:
            return set(pd.to_datetime(df_feriados['Fecha'], dayfirst=True, errors='coerce').dt.date)
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
        curr += timedelta(days=1)
    return dias

def calcular_fecha_fin_por_dias(inicio, cantidad_dias_habiles):
    curr = inicio
    dias_contados = 0
    while True:
        if curr.weekday() < 5 and curr not in FERIADOS_SET:
            dias_contados += 1
        if dias_contados == cantidad_dias_habiles:
            return curr
        curr += timedelta(days=1)

def calcular_dias_estatuto(fecha_antiguedad, anio_periodo):
    if pd.isna(fecha_antiguedad) or not fecha_antiguedad:
        return 15
    try:
        fecha_ant = pd.to_datetime(fecha_antiguedad, format="%d/%m/%Y").date()
    except:
        try:
            fecha_ant = pd.to_datetime(fecha_antiguedad, dayfirst=True, errors='coerce').date()
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

def generar_html_impresion(legajo, nombre, dni, area, tipo_lic, periodo, dias, f_inicio, f_fin, obs):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>Formulario Unificado de Licencia</title>
    <style>
        @page {{ size: A4; margin: 15mm; }}
        body {{ font-family: Arial, sans-serif; font-size: 12px; color: #111; line-height: 1.4; margin: 0; padding: 15px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #004080; padding-bottom: 10px; margin-bottom: 15px; }}
        .header-left {{ font-size: 18px; font-weight: bold; color: #004080; }}
        .header-right {{ text-align: right; font-size: 12px; color: #444; }}
        .doc-title {{ text-align: center; background-color: #f0f4f8; padding: 8px; border: 1px solid #004080; font-weight: bold; font-size: 13px; text-transform: uppercase; margin-bottom: 15px; }}
        .section-header {{ font-size: 11px; font-weight: bold; background-color: #004080; color: white; padding: 4px 8px; text-transform: uppercase; margin-top: 15px; margin-bottom: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; }}
        td {{ padding: 5px 8px; vertical-align: top; border-bottom: 1px solid #eee; }}
        .label {{ font-weight: bold; width: 28%; color: #222; }}
        .signatures {{ margin-top: 45px; display: flex; justify-content: space-between; }}
        .sig-box {{ width: 45%; text-align: center; font-size: 11px; }}
        .sig-line {{ border-top: 1px dashed #333; margin-top: 45px; margin-bottom: 5px; }}
        .footer {{ position: fixed; bottom: 0; left: 0; right: 0; text-align: center; font-size: 9px; color: #666; border-top: 1px solid #ccc; padding-top: 5px; }}
        @media print {{
            .no-print {{ display: none; }}
        }}
    </style>
    </head>
    <body>
        <div class="no-print" style="margin-bottom: 15px;">
            <button onclick="window.print()" style="padding: 10px 20px; background-color: #004080; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">🖨️ Imprimir Formulario A4</button>
        </div>

        <div class="header">
            <div class="header-left">COMUNA DE LOS REARTES</div>
            <div class="header-right">
                <strong>Oficina de Recursos Humanos</strong><br>
                Gestión Administrativa
            </div>
        </div>

        <div class="doc-title">Formulario Unificado de Solicitud y Autorización de Licencia</div>
        <p style="text-align: right; margin-bottom: 15px;"><strong>Fecha de Emisión:</strong> {date.today().strftime('%d/%m/%Y')}</p>

        <div class="section-header">1. Datos del Agente Solicitante</div>
        <table>
            <tr><td class="label">Legajo N°:</td><td>{legajo}</td><td class="label">D.N.I. N°:</td><td>{dni}</td></tr>
            <tr><td class="label">Apellido y Nombre:</td><td colspan="3"><strong>{nombre}</strong></td></tr>
            <tr><td class="label">Área / Sector:</td><td colspan="3">{area}</td></tr>
        </table>

        <div class="section-header">2. Detalle de la Solicitud de Licencia</div>
        <p>Por medio de la presente, el/la agente arriba consignado/a solicita formalmente la concesión de licencia según el siguiente detalle:</p>
        <table>
            <tr><td class="label">Tipo de Licencia:</td><td>{tipo_lic}</td></tr>
            <tr><td class="label">Período(s) Correspondiente(s):</td><td>{periodo}</td></tr>
            <tr><td class="label">Cantidad Computada:</td><td><strong>{dias} día(s) hábil(es)</strong></td></tr>
            <tr><td class="label">Vigencia:</td><td>Desde el día <strong>{f_inicio}</strong> hasta el día <strong>{f_fin}</strong> inclusive.</td></tr>
            <tr><td class="label">Observaciones / Ref:</td><td>{obs if obs else 'Sin observaciones'}</td></tr>
        </table>

        <div style="margin-top: 35px; text-align: right;">
            <div style="display: inline-block; width: 230px; text-align: center;">
                <div style="border-top: 1px solid #333; margin-top: 35px;"></div>
                <strong>FIRMA DEL AGENTE</strong><br>
                Aclaración: {nombre}<br>
                D.N.I. N°: {dni}
            </div>
        </div>

        <div class="section-header">3. Constancia de Autorización Comunal</div>
        <p>En la fecha arriba indicada, habiéndose constatado el cumplimiento de los requisitos normativos y la disponibilidad de días según registros oficiales, se OTORGA Y AUTORIZA la licencia solicitada.</p>

        <div class="signatures">
            <div class="sig-box">
                <div class="sig-line"></div>
                <strong>JEFE / DIRECTOR DE ÁREA</strong><br>
                Aclaración: ............................................<br>
                Cargo: ....................................................
            </div>
            <div class="sig-box">
                <div class="sig-line"></div>
                <strong>PRESIDENTE COMUNAL</strong><br>
                Lic. María Inés Ramello
            </div>
        </div>

        <div class="footer">
            Comuna de Los Reartes - Valle de Calamuchita - Córdoba | Oficina de Recursos Humanos
        </div>
    </body>
    </html>
    """

# -----------------------------------------------------------------------------
# MENÚ LATERAL Y NAVEGACIÓN
# -----------------------------------------------------------------------------
st.sidebar.title("📌 Menú Principal")
opcion = st.sidebar.radio(
    "Seleccione una opción:",
    ["📜 Historial y Saldos por Legajo", "➕ Cargar Licencia", "📊 Ver Base Completa"]
)

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
            c2.metric("D.N.I.", str(emp_info.get('DNI', 'N/A')))
            c3.metric("Fecha Antigüedad", str(emp_info.get('FECHA ANTIGUEDAD', 'N/A')))
            
            saldos_user = df_saldos[df_saldos['Legajo'] == legajo_sel].copy() if not df_saldos.empty else pd.DataFrame()
            hist_user = df_hist[df_hist['Legajo'] == legajo_sel].copy() if not df_hist.empty else pd.DataFrame()
            
            st.divider()
            st.subheader("🟢 Estado de Saldos de Vacaciones")
            
            tomados_por_periodo = {}
            if not hist_user.empty and 'Tipo_Licencia' in hist_user.columns:
                hist_user['Dias'] = pd.to_numeric(hist_user['Dias'], errors='coerce').fillna(0)
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
            
            if not hist_user.empty and 'Tipo_Licencia' in hist_user.columns:
                hist_user['Dias'] = pd.to_numeric(hist_user['Dias'], errors='coerce').fillna(0)
                anio_actual = date.today().year
                filtro_tipo = hist_user['Tipo_Licencia'].astype(str).str.contains("Trámite|Tramite", case=False, na=False)
                
                if 'Periodo' in hist_user.columns:
                    filtro_anio = (hist_user['Periodo'].astype(str).str.strip() == str(anio_actual)) | \
                                  (pd.to_datetime(hist_user['Fecha_Inicio'], dayfirst=True, errors='coerce').dt.year == anio_actual)
                else:
                    filtro_anio = pd.to_datetime(hist_user['Fecha_Inicio'], dayfirst=True, errors='coerce').dt.year == anio_actual
                
                tramites_anio = hist_user[filtro_tipo & filtro_anio]['Dias'].sum()
            else:
                tramites_anio = 0
                
            st.info(f"📋 **Días de Trámite solicitados en {date.today().year}:** {int(tramites_anio)} / {MAX_TRAMITE_ANUAL} días máximos anuales.")

            st.divider()
            st.subheader("📜 Historial de Licencias Consumidas y Reimpresión")
            if not hist_user.empty:
                cols_vis = [c for c in ['Periodo', 'Tipo_Licencia', 'Fecha_Inicio', 'Fecha_Fin', 'Dias', 'Observaciones'] if c in hist_user.columns]
                st.dataframe(hist_user[cols_vis], use_container_width=True, hide_index=True)
                
                st.markdown("#### 🖨️ Reimprimir Autorización Histórica")
                lic_idx = st.selectbox("Seleccione la licencia a reimprimir:", range(len(hist_user)), format_func=lambda i: f"{hist_user.iloc[i].get('Tipo_Licencia')} - Desde {hist_user.iloc[i].get('Fecha_Inicio')} ({hist_user.iloc[i].get('Dias')} días)")
                
                if st.button("Generar Planilla A4 para Reimpresión"):
                    lic_sel = hist_user.iloc[lic_idx]
                    html_doc = generar_html_impresion(
                        legajo=str(legajo_sel),
                        nombre=str(emp_info['NOMBRE_COMPLETO']),
                        dni=str(emp_info.get('DNI', '')),
                        area=str(emp_info.get('AREA', '')),
                        tipo_lic=str(lic_sel.get('Tipo_Licencia', '')),
                        periodo=str(lic_sel.get('Periodo', date.today().year)),
                        dias=str(lic_sel.get('Dias', 1)),
                        f_inicio=str(lic_sel.get('Fecha_Inicio', '')),
                        f_fin=str(lic_sel.get('Fecha_Fin', '')),
                        obs=str(lic_sel.get('Observaciones', ''))
                    )
                    components.html(html_doc, height=650, scrolling=True)
            else:
                st.write("No hay licencias registradas para este legajo.")

# =============================================================================
# OPCIÓN 2: FORMULARIO DE CARGA DE LICENCIA CON PREVIEW E IMPRESIÓN
# =============================================================================
elif opcion == "➕ Cargar Licencia":
    st.title("➕ Registrar Nueva Licencia")
    st.caption("Asiente solicitudes de licencias o vacaciones con pre-cálculo automático e impresión.")

    if not df_emp_activos.empty:
        opciones_empleados = dict(zip(df_emp_activos['LEGAJO'], df_emp_activos['LEGAJO'] + " - " + df_emp_activos['NOMBRE_COMPLETO']))
        
        legajo_sel = st.selectbox("Empleado / Agente:", options=list(opciones_empleados.keys()), format_func=lambda x: opciones_empleados[x])
        emp_info = df_emp_activos[df_emp_activos['LEGAJO'] == legajo_sel].iloc[0]
        
        col_t1, col_t2 = st.columns(2)
        tipo_lic = col_t1.selectbox("Tipo de Licencia:", ["Vacaciones", "Día de Trámite", "Licencia Médica", "Razones Particulares", "Otra"])
        periodo_lic = col_t2.text_input("Periodo (Año):", value=str(date.today().year))
        
        # Modalidad de Selección de Fechas
        modo_fechas = st.radio("Modalidad de Cálculo de Fechas:", ["Por Rango (Desde / Hasta)", "Por Cantidad de Días Hábiles (Desde + N° Días)"], horizontal=True)
        
        if modo_fechas == "Por Rango (Desde / Hasta)":
            col_f1, col_f2 = st.columns(2)
            f_inicio = col_f1.date_input("Fecha de Inicio (Desde):", value=date.today())
            f_fin = col_f2.date_input("Fecha de Fin (Hasta):", value=date.today())
            if f_fin >= f_inicio:
                dias_habiles = calcular_dias_habiles(f_inicio, f_fin)
            else:
                st.error("⚠️ La fecha final debe ser posterior a la fecha de inicio.")
                dias_habiles = 0
        else:
            col_f1, col_f2 = st.columns(2)
            f_inicio = col_f1.date_input("Fecha de Inicio (Desde):", value=date.today())
            cant_dias_input = col_f2.number_input("Cantidad de Días Hábiles a solicitar:", min_value=1, max_value=60, value=1, step=1)
            f_fin = calcular_fecha_fin_por_dias(f_inicio, cant_dias_input)
            dias_habiles = cant_dias_input

        obs = st.text_input("Observaciones / N° Resolución o Nota:")
        
        # ---------------------------------------------------------------------
        # BANNER / TARJETA DE PREVIEW ANTES DE GUARDAR
        # ---------------------------------------------------------------------
        st.divider()
        st.subheader("📋 Resumen Previo de la Solicitud")
        
        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("Fecha Inicio", f_inicio.strftime("%d/%m/%Y"))
        col_p2.metric("Fecha Fin (inclusive)", f_fin.strftime("%d/%m/%Y"))
        col_p3.metric("Días Hábiles Computados", f"{dias_habiles} día(s)")

        valido = True
        if tipo_lic == "Día de Trámite":
            hist_user = df_hist[df_hist['Legajo'] == legajo_sel] if not df_hist.empty else pd.DataFrame()
            if not hist_user.empty and 'Tipo_Licencia' in hist_user.columns:
                hist_user['Dias'] = pd.to_numeric(hist_user['Dias'], errors='coerce').fillna(0)
                filtro_tipo = hist_user['Tipo_Licencia'].astype(str).str.contains("Trámite|Tramite", case=False, na=False)
                filtro_anio = (hist_user['Periodo'].astype(str).str.strip() == str(f_inicio.year)) if 'Periodo' in hist_user.columns else (pd.to_datetime(hist_user['Fecha_Inicio'], dayfirst=True, errors='coerce').dt.year == f_inicio.year)
                tramites_anio = hist_user[filtro_tipo & filtro_anio]['Dias'].sum()
                
                if tramites_anio + dias_habiles > MAX_TRAMITE_ANUAL:
                    st.warning(f"⚠️️ Alerta: Con esta solicitud superará el máximo anual de Días de Trámite ({MAX_TRAMITE_ANUAL} días). Actualmente registra {int(tramites_anio)} días tomados.")

        # Guardar en Google Sheets
        if st.button("💾 Guardar Licencia en Google Sheets", type="primary"):
            if f_fin < f_inicio:
                st.error("No se puede guardar una licencia con fecha de fin anterior a la fecha de inicio.")
            else:
                nuevo_registro = [
                    str(legajo_sel),
                    str(emp_info['NOMBRE_COMPLETO']),
                    str(emp_info.get('AREA', '')),
                    tipo_lic,
                    str(periodo_lic),
                    f_inicio.strftime("%d/%m/%Y"),
                    f_fin.strftime("%d/%m/%Y"),
                    int(dias_habiles),
                    obs.strip()
                ]
                
                try:
                    gc = obtener_cliente_gspread()
                    sh = gc.open_by_url(st.secrets["spreadsheet_url"])
                    ws = sh.worksheet("Historial_Licencias")
                    ws.append_row(nuevo_registro)
                    st.success(f"🎉 ¡Licencia registrada correctamente en Google Sheets! ({dias_habiles} días hábiles computados)")
                    st.session_state['ultima_licencia'] = {
                        "legajo": str(legajo_sel),
                        "nombre": str(emp_info['NOMBRE_COMPLETO']),
                        "dni": str(emp_info.get('DNI', '')),
                        "area": str(emp_info.get('AREA', '')),
                        "tipo_lic": tipo_lic,
                        "periodo": str(periodo_lic),
                        "dias": str(dias_habiles),
                        "f_inicio": f_inicio.strftime("%d/%m/%Y"),
                        "f_fin": f_fin.strftime("%d/%m/%Y"),
                        "obs": obs.strip()
                    }
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Error al guardar en Google Sheets: {e}")

        # Si recién se guardó una licencia, mostramos la opción de impresión inmediata
        if 'ultima_licencia' in st.session_state:
            st.divider()
            st.subheader("🖨️ Generar y Descargar Autorización")
            lic_data = st.session_state['ultima_licencia']
            
            html_doc = generar_html_impresion(
                legajo=lic_data['legajo'],
                nombre=lic_data['nombre'],
                dni=lic_data['dni'],
                area=lic_data['area'],
                tipo_lic=lic_data['tipo_lic'],
                periodo=lic_data['periodo'],
                dias=lic_data['dias'],
                f_inicio=lic_data['f_inicio'],
                f_fin=lic_data['f_fin'],
                obs=lic_data['obs']
            )
            components.html(html_doc, height=650, scrolling=True)

# =============================================================================
# OPCIÓN 3: VER BASE COMPLETA
# =============================================================================
elif opcion == "📊 Ver Base Completa":
    st.title("📊 Base Completa de Licencias Registradas")
    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay licencias cargadas en la base de datos.")
