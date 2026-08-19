import streamlit as st
import pandas as pd
import numpy as np
import requests
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
from streamlit_oauth import OAuth2Component

# ==========================================
# CONFIGURACIÓN BÁSICA
# ==========================================
st.set_page_config(page_title="Proyecto Lab VI - Usach", layout="wide")
st.title("Laboratorio: Estimación e/m")

conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# MÓDULO DE AUTENTICACIÓN GOOGLE (SSO)
# ==========================================
CLIENT_ID = st.secrets["google_oauth"]["client_id"]
CLIENT_SECRET = st.secrets["google_oauth"]["client_secret"]
REDIRECT_URI = st.secrets["google_oauth"]["redirect_uri"]

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZE_URL, TOKEN_URL, REVOKE_URL)

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.subheader("Acceso Institucional Restringido")
    st.info("Solo los usuarios con dominio @usach.cl pueden registrar datos experimentales.")
    
    result = oauth2.authorize_button(
        name="Iniciar sesión con Google",
        icon="https://www.google.com/favicon.ico",
        redirect_uri=REDIRECT_URI,
        scope="email profile",
        key="google_login",
        use_container_width=True,
        extras_params={"prompt": "select_account", "hd": "usach.cl"}
    )
    
    if result and "token" in result:
        st.session_state.token = result["token"]["access_token"]
        
        headers = {"Authorization": f"Bearer {st.session_state.token}"}
        user_info = requests.get("https://www.googleapis.com/oauth2/v1/userinfo", headers=headers).json()
        
        correo_usuario = user_info.get("email", "")
        nombre_usuario = user_info.get("name", "")
        
        if correo_usuario.endswith("@usach.cl"):
            st.session_state.autenticado = True
            st.session_state.correo = correo_usuario
            st.session_state.nombre = nombre_usuario
            st.rerun()
        else:
            st.error(f"Acceso denegado: El correo {correo_usuario} no pertenece a la universidad.")
            requests.post(REVOKE_URL, data={"token": st.session_state.token})
    
    st.stop()

# ==========================================
# INTERFAZ WEB PRINCIPAL (Una vez logueado)
# ==========================================
st.success(f"Sesión verificada: {st.session_state.nombre} ({st.session_state.correo})")

tab1, tab2 = st.tabs(["Módulo de Adquisición", "Dashboard de Análisis"])

# --- PESTAÑA 1: MÓDULO DE ADQUISICIÓN ---
with tab1:
    st.header("Ingreso de Mediciones")
    
    # 1. Información General
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        integrantes = st.text_input("Nombres y apellidos de los integrantes")
    with col_info2:
        equipo = st.selectbox("Seleccione Equipo Utilizado", [
            "1 - PASCO SE-9629", 
            "2 - TELTRON Doble Cañón TEL 2534", 
            "3 - TELTRON Thomson Tipo S 1000617"
        ])
    
    st.markdown("---")
    
    # 2. Interfaz de Ingreso por Lote
    st.subheader("Ingreso Múltiple y Análisis Estadístico")
    st.markdown("Ingrese las mediciones en la tabla inferior. Puede agregar filas dinámicamente o copiar/pegar desde Excel.")
    
    # Definición de Incertidumbres Instrumentales
    st.markdown("**1. Defina los errores instrumentales de los equipos de medida:**")
    col_err1, col_err2, col_err3 = st.columns(3)
    delta_v = col_err1.number_input("Incertidumbre Voltaje (ΔV) [V]", value=1.0, format="%.2f", step=0.1)
    delta_i = col_err2.number_input("Incertidumbre Corriente (ΔI) [A]", value=0.01, format="%.3f", step=0.01)
    delta_r = col_err3.number_input("Incertidumbre Radio (Δr) [m]", value=0.001, format="%.4f", step=0.001)
    
    st.markdown("**2. Tabla de Datos Experimentales:**")
    # Crear un DataFrame vacío con 5 filas iniciales para que el usuario llene
    df_vacio = pd.DataFrame({
        "Va_Voltaje_Acelerador": [0.0] * 5,
        "Ib_Corriente_Bobinas": [0.0] * 5,
        "Parametro_Geometrico": [0.0] * 5
    })
    
    # Editor de datos interactivo
    df_editado = st.data_editor(df_vacio, num_rows="dynamic", use_container_width=True)
    
    if st.button("Procesar Lote y Guardar", type="primary"):
        # Filtrar filas donde hayan ingresado datos reales (Voltaje > 0)
        df_validos = df_editado[df_editado["Va_Voltaje_Acelerador"] > 0].copy()
        
        if df_validos.empty:
            st.warning("Debe ingresar al menos una medición válida (con Va > 0) para procesar.")
        else:
            # ==========================================
            # MOTOR DE CÁLCULO FÍSICO (VECTORIZADO)
            # ==========================================
            valor_teorico = 1.758820e11 # C/kg
            mu_0 = 4 * np.pi * 1e-7
            
            # Asumimos parámetros del PASCO SE-9629 por defecto para el ejemplo
            N_espiras = 130
            R_bobina = 0.15
            
            # 1. Calcular el Campo Magnético B para cada fila
            df_validos['Campo_B'] = (8 * mu_0 * N_espiras * df_validos['Ib_Corriente_Bobinas']) / (np.sqrt(125) * R_bobina)
            
            # 2. Calcular e/m para cada fila
            df_validos['e_m_Calculado'] = (2 * df_validos['Va_Voltaje_Acelerador']) / ((df_validos['Campo_B']**2) * (df_validos['Parametro_Geometrico']**2))
            
            # 3. Propagación de Error Instrumental para cada medición
            termino_v = (delta_v / df_validos['Va_Voltaje_Acelerador'])**2
            termino_i = (2 * delta_i / df_validos['Ib_Corriente_Bobinas'])**2
            termino_r = (2 * delta_r / df_validos['Parametro_Geometrico'])**2
            
            df_validos['Error_Instrumental'] = df_validos['e_m_Calculado'] * np.sqrt(termino_v + termino_i + termino_r)
            
            # 4. Cálculos Estadísticos del Lote
            em_promedio = df_validos['e_m_Calculado'].mean()
            em_std = df_validos['e_m_Calculado'].std() if len(df_validos) > 1 else 0
            error_porcentual_promedio = abs((em_promedio - valor_teorico) / valor_teorico) * 100
            
            # ==========================================
            # INTERFAZ DE RESULTADOS ESTADÍSTICOS
            # ==========================================
            st.success(f"Se procesaron {len(df_validos)} mediciones exitosamente.")
            
            st.markdown("### Análisis Estadístico del Lote")
            col_res1, col_res2, col_res3 = st.columns(3)
            col_res1.metric(label="e/m Promedio (x̄)", value=f"{em_promedio:.4e}")
            col_res2.metric(label="Desviación Estándar (σ)", value=f"± {em_std:.4e}")
            
            if error_porcentual_promedio <= 15.0:
                col_res3.metric(label="Error % Promedio", value=f"{error_porcentual_promedio:.2f} %", delta="Aceptable", delta_color="normal")
            else:
                col_res3.metric(label="Error % Promedio", value=f"{error_porcentual_promedio:.2f} %", delta="Desviación Alta", delta_color="inverse")
            
            st.markdown("#### Detalle de Propagación Instrumental")
            st.dataframe(df_validos[['Va_Voltaje_Acelerador', 'Ib_Corriente_Bobinas', 'Parametro_Geometrico', 'e_m_Calculado', 'Error_Instrumental']], use_container_width=True)
            
            # ==========================================
            # GUARDADO EN GOOGLE SHEETS
            # ==========================================
            df_existente = conn.read()
            
            # Preparar las filas para guardar
            filas_para_guardar = []
            for index, row in df_validos.iterrows():
                filas_para_guardar.append({
                    "Fecha_Ingreso": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Correo": st.session_state.correo,
                    "Integrantes": integrantes,
                    "Equipo": equipo.split(" - ")[1],
                    "Vf_Voltaje_Filamento": np.nan,
                    "Va_Voltaje_Acelerador": row['Va_Voltaje_Acelerador'],
                    "Vp_Voltaje_Placas": np.nan,
                    "Vb_Voltaje_Bobinas": np.nan,
                    "Ib_Corriente_Bobinas": row['Ib_Corriente_Bobinas'],
                    "Parametro_Geometrico": row['Parametro_Geometrico'],
                    "e_m_Calculado": row['e_m_Calculado'],
                    "Error_Porcentual": error_porcentual_promedio,
                    "Observaciones": f"Lote. Err Inst: ±{row['Error_Instrumental']:.2e}"
                })
            
            df_nuevas_filas = pd.DataFrame(filas_para_guardar)
            df_actualizado = pd.concat([df_existente, df_nuevas_filas], ignore_index=True)
            
            conn.update(worksheet="Sheet1", data=df_actualizado)
            st.info("Datos del lote respaldados en la base institucional.")


# --- PESTAÑA 2: DASHBOARD DE ANÁLISIS ---
with tab2:
    st.header("Análisis Histórico y Deriva Temporal")
    
    try:
        # Cargar datos automáticamente sin necesidad de apretar un botón
        df = conn.read()
        
        # Verificamos si la columna existe antes de intentar limpiar vacíos
        if 'Va_Voltaje_Acelerador' in df.columns:
            df = df.dropna(subset=['Va_Voltaje_Acelerador'])
        elif 'Voltaje_Acelerador' in df.columns: 
            df = df.dropna(subset=['Voltaje_Acelerador'])
            
        # Si hay datos válidos, armamos el panel
        if not df.empty and len(df) > 0:
            st.success(f"Conexión exitosa: Se cargaron {len(df)} mediciones históricas.")
            
            # 1. Mostrar la tabla de datos completa
            st.subheader("Base de Datos Experimental")
            st.dataframe(df, use_container_width=True)
            
            # 2. Mostrar gráficos interactivos
            if 'Error_Porcentual' in df.columns and 'e_m_Calculado' in df.columns:
                st.markdown("---")
                st.subheader("Análisis Visual")
                col_graf1, col_graf2 = st.columns(2)
                
                with col_graf1:
                    st.markdown("**Evolución de la Relación e/m**")
                    df_em = df.dropna(subset=['e_m_Calculado'])
                    st.scatter_chart(data=df_em, x='Fecha_Ingreso', y='e_m_Calculado')
                    
                with col_graf2:
                    st.markdown("**Deriva Temporal del Error (%)**")
                    df_err = df.dropna(subset=['Error_Porcentual'])
                    st.line_chart(data=df_err, x='Fecha_Ingreso', y='Error_Porcentual', color="#ff0000")
            else:
                st.info("Los gráficos aparecerán cuando se registren cálculos de error porcentual y e/m.")
                
        else:
            st.warning("La base de datos está vacía. Ingresa la primera medición en el Módulo de Adquisición.")
            
    except Exception as e:
        st.error(f"Error de lectura. Verifica que los nombres de las columnas en Google Sheets sean correctos. Detalle técnico: {e}")
