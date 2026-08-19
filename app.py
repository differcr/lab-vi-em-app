import streamlit as st
import pandas as pd
import numpy as np
import requests # <--- Nueva librería para consultar a Google
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
from streamlit_oauth import OAuth2Component # <--- Nueva librería para el botón

# ==========================================
# CONFIGURACIÓN BÁSICA
# ==========================================
st.set_page_config(page_title="Proyecto Lab VI - Usach", layout="wide")
st.title("Laboratorio: Estimación e/m")

conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# MÓDULO DE AUTENTICACIÓN GOOGLE (SSO)
# ==========================================
# Extraemos las credenciales desde secrets.toml
CLIENT_ID = st.secrets["google_oauth"]["client_id"]
CLIENT_SECRET = st.secrets["google_oauth"]["client_secret"]
REDIRECT_URI = st.secrets["google_oauth"]["redirect_uri"]

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Instanciar el componente de OAuth
oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZE_URL, TOKEN_URL, REVOKE_URL)

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.subheader("Acceso Institucional Restringido")
    st.info("Solo los usuarios con dominio @usach.cl pueden registrar datos experimentales.")
    
    # Creamos el botón oficial de Google
    result = oauth2.authorize_button(
        name="Iniciar sesión con Google",
        icon="https://www.google.com/favicon.ico",
        redirect_uri=REDIRECT_URI,
        scope="email profile",
        key="google_login",
        use_container_width=True
    )
    
    # Si el usuario se loguea y Google devuelve un token:
    if result and "token" in result:
        st.session_state.token = result["token"]["access_token"]
        
        # Hacemos una consulta rápida a Google para saber el correo de quien inició sesión
        headers = {"Authorization": f"Bearer {st.session_state.token}"}
        user_info = requests.get("https://www.googleapis.com/oauth2/v1/userinfo", headers=headers).json()
        
        correo_usuario = user_info.get("email", "")
        nombre_usuario = user_info.get("name", "")
        
        # Filtro de Dominio USACH
        if correo_usuario.endswith("@usach.cl"):
            st.session_state.autenticado = True
            st.session_state.correo = correo_usuario
            st.session_state.nombre = nombre_usuario
            st.rerun() # Recargar la página para entrar a la plataforma
        else:
            st.error(f"Acceso denegado: El correo {correo_usuario} no pertenece a la universidad.")
            # Revocamos el token para cerrar su sesión inmediatamente
            requests.post(REVOKE_URL, data={"token": st.session_state.token})
    
    # Detenemos la ejecución aquí si no hay login exitoso
    st.stop()

# ==========================================
# INTERFAZ WEB PRINCIPAL (Una vez logueado)
# ==========================================
st.success(f"Sesión verificada: {st.session_state.nombre} ({st.session_state.correo})")

# ... (AQUÍ PEgas EL CÓDIGO DE LAS PESTAÑAS (TABS) QUE YA TENÍAMOS) ...

# --- PESTAÑA 1: MÓDULO DE ADQUISICIÓN ---
with tab1:
    st.header("Ingreso de Mediciones")
    
    with st.form("formulario_ingreso"):
        col1, col2 = st.columns(2)
        
        with col1:
            integrantes = st.text_input("Nombres y apellidos de los integrantes")
            equipo = st.selectbox("Seleccione Equipo Utilizado", [
                "1 - PASCO SE-9629", 
                "2 - TELTRON Doble Cañón TEL 2534", 
                "3 - TELTRON Thomson Tipo S 1000617"
            ])
            
            st.markdown("---")
            st.subheader("Variables Comunes")
            vf = st.number_input("Voltaje filamento (Vf) [V]", min_value=0.0, format="%.2f")
            va = st.number_input("Voltaje acelerador (Va) [V]", min_value=0.0, format="%.2f")
            ib = st.number_input("Corriente Bobinas (Ib) [A]", min_value=0.0, format="%.2f")

        with col2:
            st.markdown("---")
            st.subheader("Variables Específicas del Equipo")
            
            # Inicializamos variables específicas en None para evitar errores si no se usan
            vp = None
            vb = None
            param_geometrico = None
            
            # Lógica dinámica según el equipo seleccionado
            if "1 - PASCO" in equipo:
                param_geometrico = st.number_input("Radio anillo (R) [m]", min_value=0.0, format="%.4f")
                
            elif "2 - TELTRON Doble Cañón" in equipo:
                vp = st.number_input("Voltaje placas (Vp) [V]", min_value=0.0, format="%.2f")
                vb = st.number_input("Voltaje Bobinas (Vb) [V]", min_value=0.0, format="%.2f")
                param_geometrico = st.number_input("Curvatura (Ra o Re) [m]", min_value=0.0, format="%.4f")
                
            elif "3 - TELTRON Thomson" in equipo:
                vp = st.number_input("Voltaje placas (Vp) [V]", min_value=0.0, format="%.2f")
                vb = st.number_input("Voltaje Bobinas (Vb) [V]", min_value=0.0, format="%.2f")
                param_geometrico = st.number_input("Distancia FA (L) [m]", min_value=0.0, format="%.4f")

        submit = st.form_submit_button("Guardar Medición")
        
        if submit:
            if va == 0 or ib == 0 or param_geometrico == 0:
                st.warning("Alerta: Revise los datos, hay valores clave en cero.")
            else:
                # 1. Leer los datos actuales de la hoja en la nube
                df_existente = conn.read()
                
                # 2. Crear la nueva fila adaptando los valores Nulos (NaN) si no aplican
                nueva_fila = pd.DataFrame([{
                    "Fecha_Ingreso": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Correo": st.session_state.correo,
                    "Integrantes": integrantes,
                    "Equipo": equipo.split(" - ")[1],
                    "Vf_Voltaje_Filamento": vf,
                    "Va_Voltaje_Acelerador": va,
                    "Vp_Voltaje_Placas": vp if vp is not None else np.nan,
                    "Vb_Voltaje_Bobinas": vb if vb is not None else np.nan,
                    "Ib_Corriente_Bobinas": ib,
                    "Parametro_Geometrico": param_geometrico,
                    "Observaciones": "Dato válido"
                }])
                
                # 3. Unir los datos antiguos con el nuevo y actualizar Sheets
                df_actualizado = pd.concat([df_existente, nueva_fila], ignore_index=True)
                conn.update(worksheet="Sheet1", data=df_actualizado)
                
                st.success("¡Datos guardados correctamente en Google Sheets!")

# --- PESTAÑA 2: DASHBOARD DE ANÁLISIS ---
with tab2:
    st.header("Análisis Histórico y Deriva Temporal")
    
    if st.button("Actualizar Datos desde la Nube"):
        df = conn.read()
        df = df.dropna(subset=['Va_Voltaje_Acelerador'])
        
        if not df.empty:
            st.dataframe(df)
            st.info("Para aislar el cálculo matemático, agregue los filtros interactivos en las próximas etapas.")
        else:
            st.info("Aún no hay datos históricos para analizar.")
