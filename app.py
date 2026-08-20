import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import linregress
from streamlit_gsheets import GSheetsConnection
from streamlit_oauth import OAuth2Component
from datetime import datetime
import base64
import json
import requests
# =============================================================================
# MÓDULO 1: CONSTANTES, PARAMETRIZACIÓN Y FUNCIONES MATEMÁTICAS
# =============================================================================

MU_0 = 4 * np.pi * 10**-7  
EM_TEORICO = 1.758820e11   

equipos_parametros = {
    "PASCO SE-9629": {"R": 0.158, "N": 130},
    "TELTRON TEL 2534": {"D": 0.138, "k_B": 4.17e-3},
    "TELTRON Tipo S 1000617": {"R": 0.068, "N": 320, "k_B": 4.2e-3}
}

protocolo_adquisicion = {
    "PASCO SE-9629": {
        "experimentos": {
            "Deflexion Magnetica (Determinacion e/m)": { 
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "rango_valido": (0, 250)},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "rango_valido": (0, 3.5)},
                    {"nombre": "r_Radio_Haz_mm", "unidad": "mm", "tipo": "float", "descripcion": "Medir a ambos lados y promediar"}
                ]
            }
        }
    },
    "TELTRON TEL 2534": {
        "experimentos": {
            "B.16 e/m con Cañon Axial": { 
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "rango_valido": (80, 150)},
                    {"nombre": "Vp_Voltaje_Placas_Enfoque", "unidad": "V", "tipo": "float", "rango_valido": (0, 6)},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float"},
                    {"nombre": "Distancia_EE", "unidad": "mm", "tipo": "float", "descripcion": "Distancia entre anillos fundidos"}
                ]
            },
            "B.16 e/m con Cañon Perpendicular": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "rango_valido": (80, 150)},
                    {"nombre": "Vp_Voltaje_Placas_Enfoque", "unidad": "V", "tipo": "float", "rango_valido": (0, 6)},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float"},
                    {"nombre": "Distancia_AA", "unidad": "mm", "tipo": "float", "descripcion": "Diámetro del anillo"}
                ]
            }
        }
    },
    "TELTRON Tipo S 1000617": {
        "experimentos": {
            "Exp 1: Balance de Campos (Fuerza Nula)": { 
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Anodo", "unidad": "V", "tipo": "float", "rango_valido": (2000, 5000)},
                    {"nombre": "Vp_Voltaje_Placas", "unidad": "V", "tipo": "float", "rango_valido": (50, 350)},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float"},
                    {"nombre": "Distancia_L_Nula", "unidad": "mm", "tipo": "float"}
                ]
            },
            "Exp 2: Deflexion Magnetica Pura": { 
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Anodo", "unidad": "V", "tipo": "float", "rango_valido": (2000, 5000)},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float"},
                    {"nombre": "Coordenada_x", "unidad": "mm", "tipo": "float"},
                    {"nombre": "Coordenada_y", "unidad": "mm", "tipo": "float"}
                ]
            }
        }
    }
}

def calcular_campo_pasco(I, R, N):
    return (4/5)**(1.5) * (MU_0 * N * I) / R

def calcular_r_geom_thomson(c_mm, a_mm):
    c = c_mm / 1000
    a = a_mm / 1000
    return (c**2 + a**2) / (2 * a)

def calcular_r_geom_doble_canon(x_mm, y_mm):
    x = x_mm / 1000
    y = y_mm / 1000
    return (x**2 + y**2) / (2 * y)

# =============================================================================
# MÓDULO 2: SISTEMA DE ALERTAS Y LIMPIEZA LÓGICA (SOFT DELETION)
# =============================================================================

def limpiar_base_datos(df, df_anulaciones=None):
    if df_anulaciones is not None and not df_anulaciones.empty:
        df = df[~df['ID_Medicion'].isin(df_anulaciones['ID_Medicion_Anular'])]
        
    invalida = pd.Series(False, index=df.index)
    if 'Va_Voltaje_Acelerador' in df.columns:
        invalida = invalida | (pd.to_numeric(df['Va_Voltaje_Acelerador'], errors='coerce') <= 0)
    if 'Ih_Corriente_Bobinas' in df.columns:
        invalida = invalida | (pd.to_numeric(df['Ih_Corriente_Bobinas'], errors='coerce') <= 0)
            
    df_limpio = df[~invalida].copy()
    return df_limpio

# =============================================================================
# MÓDULO 3: ANÁLISIS DE REGRESIÓN Y EXTRACCIÓN DE e/m
# =============================================================================

def analisis_regresion_equipo(df_limpio, equipo_nombre, experimento=None):
    if experimento:
        datos = df_limpio[(df_limpio['Equipo'] == equipo_nombre) & (df_limpio['Experimento'] == experimento)].copy()
    else:
        datos = df_limpio[df_limpio['Equipo'] == equipo_nombre].copy()
        
    if len(datos) < 3:
        st.warning(f"Datos insuficientes para análisis de regresión en {equipo_nombre}.")
        return None, None, None
        
    x_vals = []
    y_vals = []
    
    if equipo_nombre == "PASCO SE-9629":
        R = equipos_parametros[equipo_nombre]["R"]
        N = equipos_parametros[equipo_nombre]["N"]
        for _, row in datos.iterrows():
            U = pd.to_numeric(row.get('Va_Voltaje_Acelerador'))
            I_H = pd.to_numeric(row.get('Ih_Corriente_Bobinas'))
            r = pd.to_numeric(row.get('r_Radio_Haz_mm')) / 1000 
            B = calcular_campo_pasco(I_H, R, N)
            y_vals.append(2 * U)
            x_vals.append((B * r)**2)
            
    elif equipo_nombre == "TELTRON TEL 2534":
        for _, row in datos.iterrows():
            U = pd.to_numeric(row.get('Va_Voltaje_Acelerador'))
            I_H = pd.to_numeric(row.get('Ih_Corriente_Bobinas'))
            y_vals.append(U)
            x_vals.append(I_H**2)
            
    elif equipo_nombre == "TELTRON Tipo S 1000617":
        if experimento == "Exp 2: Deflexion Magnetica Pura":
            k_B = equipos_parametros[equipo_nombre]["k_B"]
            for _, row in datos.iterrows():
                U = pd.to_numeric(row.get('Va_Voltaje_Anodo'))
                I_H = pd.to_numeric(row.get('Ih_Corriente_Bobinas'))
                c = pd.to_numeric(row.get('Coordenada_x'))
                a = pd.to_numeric(row.get('Coordenada_y'))
                r = calcular_r_geom_thomson(c, a)
                B = k_B * I_H
                y_vals.append(2 * U)
                x_vals.append((B * r)**2)
                
    if len(x_vals) < 3:
        st.warning("No hay suficientes datos válidos para este equipo/experimento.")
        return None, None, None
        
    x_array = np.array(x_vals)
    y_array = np.array(y_vals)
    res = linregress(x_array, y_array)
    pendiente = res.slope
    incerteza_ajuste = res.stderr
    
    if equipo_nombre == "TELTRON TEL 2534":
        if 'R_Calculado_m' in datos.columns:
            R_medio = pd.to_numeric(datos['R_Calculado_m']).mean()
        else:
            R_medio = 0.05
        em_experimental = pendiente * (1.15e5 / (R_medio**2))
        incerteza_final = incerteza_ajuste * (1.15e5 / (R_medio**2))
    else:
        em_experimental = pendiente
        incerteza_final = incerteza_ajuste
        
    fig = generar_grafico_regresion(x_array, y_array, res, equipo_nombre, em_experimental, incerteza_final)
    return em_experimental, incerteza_final, fig

def generar_grafico_regresion(x, y, res, titulo, em_val, error):
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(x, y, color='darkblue', alpha=0.7, label='Datos Filtrados')
    ax.plot(x, res.intercept + res.slope * x, 'r--', label=f'Ajuste Lineal (R²={res.rvalue**2:.3f})')
    ax.set_title(f'Estimación e/m: {titulo}')
    ax.set_xlabel('Variable Independiente (Teórica)')
    ax.set_ylabel('Variable Dependiente (Teórica)')
    
    texto_res = f"e/m exp: {em_val:.3e} C/kg\nError Std: ±{error:.3e} C/kg"
    ax.text(0.05, 0.95, texto_res, transform=ax.transAxes, fontsize=11,
             verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))
             
    ax.legend()
    ax.grid(True, linestyle=':', alpha=0.6)
    fig.tight_layout()
    return fig

# =============================================================================
# MÓDULO 4: AUTENTICACIÓN OAUTH Y APLICACIÓN PRINCIPAL
# =============================================================================

st.set_page_config(page_title="Proyecto Lab VI - Usach", layout="wide")

# Configuración de Google OAuth 2.0 extraída de st.secrets
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


# SI PASA LA BARRERA, SE CARGA LA APP
st.sidebar.write(f"Conectado como: **{st.session_state['user_email']}**")
if st.sidebar.button("Cerrar Sesión"):
    del st.session_state["user_email"]
    st.rerun()

st.title("Laboratorio: Estimación e/m")
conn = st.connection("gsheets", type=GSheetsConnection)

tab1, tab2 = st.tabs(["Módulo de Adquisición", "Dashboard de Análisis"])

# --- PESTAÑA 1: MÓDULO DE ADQUISICIÓN ---
with tab1:
    st.header("Ingreso de Mediciones")
    
    equipo_seleccionado = st.selectbox("Seleccione Equipo", list(protocolo_adquisicion.keys()))
    
    if equipo_seleccionado:
        experimentos_disponibles = list(protocolo_adquisicion[equipo_seleccionado]["experimentos"].keys())
        experimento_seleccionado = st.selectbox("Seleccione Experimento", experimentos_disponibles)
        
        campos = protocolo_adquisicion[equipo_seleccionado]["experimentos"][experimento_seleccionado]["campos_requeridos"]
        
        with st.form("formulario_ingreso"):
            st.subheader("Datos Generales")
            # El correo se auto-rellena y bloquea por seguridad
            correo = st.text_input("Correo Institucional", value=st.session_state['user_email'], disabled=True)
            integrantes = st.text_input("Integrantes del grupo")
            
            st.subheader(f"Mediciones - {experimento_seleccionado}")
            valores_ingresados = {}
            col1, col2 = st.columns(2)
            
            for i, campo in enumerate(campos):
                col = col1 if i % 2 == 0 else col2
                with col:
                    nombre = campo["nombre"]
                    unidad = campo["unidad"]
                    label = f"{nombre} [{unidad}]"
                    if "descripcion" in campo:
                        label += f" - {campo['descripcion']}"
                    
                    if campo["tipo"] == "float":
                        min_val = float(campo["rango_valido"][0]) if "rango_valido" in campo else 0.0
                        valores_ingresados[nombre] = st.number_input(label, min_value=min_val, format="%.4f")
            
            submit = st.form_submit_button("Guardar Medición")
            
            if submit:
                has_zero = False
                for key, val in valores_ingresados.items():
                    if ('Voltaje' in key or 'Corriente' in key) and val == 0:
                        has_zero = True
                        
                if has_zero:
                    st.warning("Alerta: Revise los datos, hay valores en cero en campos de voltaje o corriente.")
                else:
                    df_existente = conn.read()
                    
                    nueva_fila_dict = {
                        "ID_Medicion": f"MED-{int(datetime.now().timestamp())}",
                        "Fecha_Ingreso": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Correo": correo,
                        "Integrantes": integrantes,
                        "Equipo": equipo_seleccionado,
                        "Experimento": experimento_seleccionado,
                        "Observaciones": "Dato válido"
                    }
                    nueva_fila_dict.update(valores_ingresados)
                    
                    nueva_fila = pd.DataFrame([nueva_fila_dict])
                    df_actualizado = pd.concat([df_existente, nueva_fila], ignore_index=True)
                    
                    conn.update(worksheet="Sheet1", data=df_actualizado)
                    st.success("¡Datos guardados correctamente en Google Sheets!")

# --- PESTAÑA 2: DASHBOARD DE ANÁLISIS ---
with tab2:
    st.header("Análisis Histórico y Regresión")
    
    if st.button("Actualizar y Analizar Datos"):
        df_raw = conn.read()
        df_raw = df_raw.dropna(subset=['Equipo'])
        
        if not df_raw.empty:
            df_valido = limpiar_base_datos(df_raw)
            st.subheader("Datos Procesados (Filtrados)")
            st.dataframe(df_valido)
            
            st.subheader("Análisis por Equipo")
            equipos_presentes = df_valido['Equipo'].unique()
            
            for eq in equipos_presentes:
                st.write(f"### Equipo: {eq}")
                experimentos_eq = df_valido[df_valido['Equipo'] == eq]['Experimento'].unique()
                
                for exp in experimentos_eq:
                    st.write(f"**Experimento:** {exp}")
                    em, incerteza, fig = analisis_regresion_equipo(df_valido, eq, exp)
                    
                    if fig:
                        st.pyplot(fig)
                        error_perc = np.abs((em - EM_TEORICO) / EM_TEORICO) * 100
                        st.metric(label="Error Porcentual (vs Teórico)", value=f"{error_perc:.2f}%")
        else:
            st.info("Aún no hay datos históricos para analizar.")
