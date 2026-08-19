import streamlit as st
import pandas as pd
import numpy as np
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# ==========================================
# CONFIGURACIÓN BÁSICA
# ==========================================
st.set_page_config(page_title="Proyecto Lab VI - Usach", layout="wide")
st.title("Laboratorio: Estimación e/m")

# Establecer conexión segura con Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# MÓDULO DE AUTENTICACIÓN INSTITUCIONAL
# ==========================================
# Inicializar el estado de la sesión si no existe
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

# Pantalla de Login (Si no está autenticado, muestra esto y detiene el código)
if not st.session_state.autenticado:
    st.subheader("Acceso Restringido")
    st.info("Para ingresar a la plataforma de adquisición, debe utilizar sus credenciales institucionales.")
    
    with st.form("login_form"):
        correo_login = st.text_input("Correo Electrónico")
        btn_ingresar = st.form_submit_button("Ingresar")
        
        if btn_ingresar:
            if correo_login.strip().endswith("@usach.cl"):
                # Guardar el correo en la sesión y cambiar estado a verdadero
                st.session_state.autenticado = True
                st.session_state.correo = correo_login.strip()
                st.rerun() # Recarga la página para mostrar el contenido
            else:
                st.error("Acceso denegado. Debe utilizar un correo con el dominio @usach.cl")
    
    # st.stop() evita que se cargue el resto de la página si no se ha iniciado sesión
    st.stop()

# ==========================================
# INTERFAZ WEB PRINCIPAL (Una vez logueado)
# ==========================================
st.success(f"Sesión iniciada como: {st.session_state.correo}")
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
