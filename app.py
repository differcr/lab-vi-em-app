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
        extra_params={"prompt": "select_account", "hd": "usach.cl"}
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

# AQUI SE DEFINEN LAS PESTAÑAS (Esto faltaba y causaba el NameError)
tab1, tab2 = st.tabs(["Módulo de Adquisición", "Dashboard de Análisis"])

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
            
            vp = None
            vb = None
            param_geometrico = None
            
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
                # ==========================================
                # 1. MOTOR DE CÁLCULO FÍSICO
                # ==========================================
                e_m_calculado = None
                error_porcentual = None
                valor_teorico = 1.758820e11 # C/kg
                mu_0 = 4 * np.pi * 1e-7

                try:
                    if "1 - PASCO" in equipo:
                        # Constantes del equipo PASCO SE-9629
                        N_espiras = 130
                        R_bobina = 0.15
                        B = (8 * mu_0 * N_espiras * ib) / (np.sqrt(125) * R_bobina)
                        e_m_calculado = (2 * va) / ((B**2) * (param_geometrico**2))
                        
                    elif "2 - TELTRON Doble Cañón" in equipo:
                        # ATENCIÓN: Reemplaza N_espiras y R_bobina con los de tu guía de laboratorio TELTRON
                        N_espiras = 320   # Valor típico Teltron, ¡Verificar!
                        R_bobina = 0.068  # Valor típico Teltron, ¡Verificar!
                        B = (8 * mu_0 * N_espiras * ib) / (np.sqrt(125) * R_bobina)
                        # Fórmula de deflexión magnética estándar
                        e_m_calculado = (2 * va) / ((B**2) * (param_geometrico**2))
                        
                    elif "3 - TELTRON Thomson" in equipo:
                        # ATENCIÓN: Inserta aquí la ecuación exacta de campos cruzados de tu guía
                        # e_m_calculado = ... 
                        pass 

                    # Calcular el error si se obtuvo un valor
                    if e_m_calculado is not None:
                        error_porcentual = abs((e_m_calculado - valor_teorico) / valor_teorico) * 100

                except Exception as e:
                    st.error("Error matemático en el cálculo. Revise los parámetros ingresados.")

                # ==========================================
                # 2. GUARDADO EN GOOGLE SHEETS
                # ==========================================
                df_existente = conn.read()
                
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
                    # Opcional: También podemos guardar el cálculo en la nube directamente
                    "e_m_Calculado": e_m_calculado if e_m_calculado else np.nan,
                    "Error_Porcentual": error_porcentual if error_porcentual else np.nan,
                    "Observaciones": "Dato válido"
                }])
                
                # Actualizar Sheets (Asegúrate de que Worksheet coincide con tu Excel, por ej "Hoja 1" o "Sheet1")
                df_actualizado = pd.concat([df_existente, nueva_fila], ignore_index=True)
                conn.update(worksheet="Sheet1", data=df_actualizado)
                
                # ==========================================
                # 3. INTERFAZ DE RESULTADOS (FEEDBACK VISUAL)
                # ==========================================
                st.success("¡Datos guardados correctamente en la base institucional!")
                
                if e_m_calculado is not None:
                    st.markdown("### Resultados Preliminares del Ensayo")
                    col_res1, col_res2, col_res3 = st.columns(3)
                    
                    col_res1.metric(label="Relación e/m Obtenida", value=f"{e_m_calculado:.4e} C/kg")
                    col_res2.metric(label="Valor Teórico", value=f"{valor_teorico:.4e} C/kg")
                    
                    # Mostrar el error en rojo si es muy alto, o normal si es bajo
                    if error_porcentual <= 15.0:
                        col_res3.metric(label="Error Experimental", value=f"{error_porcentual:.2f} %", delta="Aceptable", delta_color="normal")
                    else:
                        col_res3.metric(label="Error Experimental", value=f"{error_porcentual:.2f} %", delta="Alta Desviación", delta_color="inverse")
