import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import linregress
from streamlit_gsheets import GSheetsConnection
from streamlit_oauth import OAuth2Component
from datetime import datetime
import uuid
import requests
import base64
import json

# =============================================================================
# CONFIGURACIÓN BÁSICA DE LA PÁGINA
# =============================================================================
st.set_page_config(page_title="Proyecto Lab VI - Usach", layout="wide")

# =============================================================================
# MÓDULO 4: AUTENTICACIÓN OAUTH Y BARRERA DE SEGURIDAD
# =============================================================================

if "correo" not in st.session_state:
    st.session_state["correo"] = None
if "nombre" not in st.session_state:
    st.session_state["nombre"] = None
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

CLIENT_ID = st.secrets["google_oauth"]["client_id"]
CLIENT_SECRET = st.secrets["google_oauth"]["client_secret"]
REDIRECT_URI = st.secrets["google_oauth"]["redirect_uri"]

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZE_URL, TOKEN_URL, TOKEN_URL, REVOKE_URL)

if not st.session_state["autenticado"]:
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
        access_token = result["token"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get("https://www.googleapis.com/oauth2/v1/userinfo", headers=headers)
        user_info = resp.json()
        
        correo_usuario = user_info.get("email", "")
        nombre_usuario = user_info.get("name", "")
        
        if correo_usuario.endswith("@usach.cl"):
            st.session_state["autenticado"] = True
            st.session_state["correo"] = correo_usuario
            st.session_state["nombre"] = nombre_usuario
            st.rerun()
        else:
            st.error(f"Acceso denegado: El correo {correo_usuario} no pertenece a la universidad.")
            requests.post(REVOKE_URL, data={"token": access_token})
            
    st.stop()

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
                    {"nombre": "r_Radio_Haz_mm", "unidad": "mm", "tipo": "float", "descripcion": "Promedio de ambos lados"}
                ]
            }
        }
    },
    "TELTRON TEL 2534": {
        "experimentos": {
            "Punto A - Cañon Axial (anillo lejano AA')": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Vp_Voltaje_Placas_Enfoque", "unidad": "V", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Distancia_AE_mm", "unidad": "mm", "tipo": "float", "valor_defecto": 80.0},
                    {"nombre": "Diametro_AA_mm", "unidad": "mm", "tipo": "float", "valor_defecto": 102.0}
                ]
            },
            "Punto E - Cañon Axial (anillo cercano EE')": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Vp_Voltaje_Placas_Enfoque", "unidad": "V", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Diametro_EE_mm", "unidad": "mm", "tipo": "float", "valor_defecto": 102.0}
                ]
            },
            "Perpendicular - anillo AA'": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Vp_Voltaje_Placas_Enfoque", "unidad": "V", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Distancia_AE_mm", "unidad": "mm", "tipo": "float", "valor_defecto": 80.0}
                ]
            }
        }
    },
    "TELTRON Tipo S 1000617": {
        "experimentos": {
            "Exp 1: Balance de Campos (Fuerza Nula)": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Anodo", "unidad": "V", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Vp_Voltaje_Placas", "unidad": "V", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Distancia_L_Nula", "unidad": "mm", "tipo": "float", "valor_defecto": 0.0}
                ]
            },
            "Exp 2: Deflexion Magnetica Pura": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Anodo", "unidad": "V", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "valor_defecto": 0.0},
                    {"nombre": "Coordenada_x", "unidad": "mm", "tipo": "float", "valor_defecto": 47.0},
                    {"nombre": "Coordenada_y", "unidad": "mm", "tipo": "float", "valor_defecto": 0.0}
                ]
            }
        }
    }
}

def calcular_campo_pasco(I, R, N):
    return (4 / 5) ** (1.5) * (MU_0 * N * I) / R

def calcular_r_geom_thomson(c_mm, a_mm):
    c = c_mm / 1000
    a = a_mm / 1000
    return (c ** 2 + a ** 2) / (2 * a)

def calcular_R_tel2534_punto_axial(distancia_ae_mm, diametro_anillo_mm):
    x_mm = distancia_ae_mm + 2.0
    y_mm = diametro_anillo_mm / 2.0
    return calcular_r_geom_thomson(x_mm, y_mm)

def calcular_R_tel2534_punto_E(diametro_ee_mm):
    x_mm = 2.0
    y_mm = diametro_ee_mm / 2.0
    return calcular_r_geom_thomson(x_mm, y_mm)

def calcular_R_tel2534_perpendicular(distancia_ae_mm):
    return (distancia_ae_mm / 1000) / 2

def calcular_em_fila(row, equipo, experimento):
    """Cálculo individual de e/m por cada fila del Data Editor."""
    try:
        if equipo == "PASCO SE-9629":
            U = float(row.get('Va_Voltaje_Acelerador', 0))
            I = float(row.get('Ih_Corriente_Bobinas', 0))
            r = float(row.get('r_Radio_Haz_mm', 0)) / 1000.0
            if U <= 0 or I <= 0 or r <= 0: return np.nan
            B = calcular_campo_pasco(I, equipos_parametros[equipo]["R"], equipos_parametros[equipo]["N"])
            return (2 * U) / ((B * r)**2)
            
        elif equipo == "TELTRON TEL 2534":
            U = float(row.get('Va_Voltaje_Acelerador', 0))
            I = float(row.get('Ih_Corriente_Bobinas', 0))
            if U <= 0 or I <= 0: return np.nan
            
            if "Punto A" in experimento:
                ae = float(row.get('Distancia_AE_mm', 80))
                d_aa = float(row.get('Diametro_AA_mm', 102))
                R = calcular_R_tel2534_punto_axial(ae, d_aa)
            elif "Punto E" in experimento:
                d_ee = float(row.get('Diametro_EE_mm', 102))
                R = calcular_R_tel2534_punto_E(d_ee)
            elif "Perpendicular" in experimento:
                ae = float(row.get('Distancia_AE_mm', 80))
                R = calcular_R_tel2534_perpendicular(ae)
            else: return np.nan
            
            if R <= 0: return np.nan
            k_B = equipos_parametros[equipo]["k_B"]
            factor = 2 / (k_B**2)
            return (U / (I**2)) * (factor / (R**2))
            
        elif equipo == "TELTRON Tipo S 1000617":
            if experimento == "Exp 2: Deflexion Magnetica Pura":
                U = float(row.get('Va_Voltaje_Anodo', 0))
                I = float(row.get('Ih_Corriente_Bobinas', 0))
                c = float(row.get('Coordenada_x', 0))
                a = float(row.get('Coordenada_y', 0))
                if U <= 0 or I <= 0 or a <= 0: return np.nan
                r = calcular_r_geom_thomson(c, a)
                B = equipos_parametros[equipo]["k_B"] * I
                return (2 * U) / ((B * r)**2)
                
            elif experimento == "Exp 1: Balance de Campos (Fuerza Nula)":
                U = float(row.get('Va_Voltaje_Anodo', 0))
                Vp = float(row.get('Vp_Voltaje_Placas', 0))
                I = float(row.get('Ih_Corriente_Bobinas', 0))
                d_mm = float(row.get('Distancia_L_Nula', 0))
                if U <= 0 or I <= 0 or Vp <= 0 or d_mm <= 0: return np.nan
                d = d_mm / 1000.0
                B = equipos_parametros[equipo]["k_B"] * I
                E = Vp / d
                return ((E / B)**2) / (2 * U)
    except:
        return np.nan
    return np.nan

# =============================================================================
# MÓDULO 2: SISTEMA DE ALERTAS Y LIMPIEZA LÓGICA (SOFT DELETION)
# =============================================================================

def limpiar_base_datos(df, df_anulaciones=None):
    if df_anulaciones is not None and not df_anulaciones.empty:
        df = df[~df['ID_Medicion'].isin(df_anulaciones['ID_Medicion_Anular'])]

    invalida = pd.Series(False, index=df.index)
    for col_voltaje in ['Va_Voltaje_Acelerador', 'Va_Voltaje_Anodo']:
        if col_voltaje in df.columns:
            invalida = invalida | (pd.to_numeric(df[col_voltaje], errors='coerce') <= 0)

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
        return None, None, None

    x_vals = []
    y_vals = []

    if equipo_nombre == "PASCO SE-9629":
        R = equipos_parametros[equipo_nombre]["R"]
        N = equipos_parametros[equipo_nombre]["N"]
        for _, row in datos.iterrows():
            U = pd.to_numeric(row.get('Va_Voltaje_Acelerador'), errors='coerce')
            I_H = pd.to_numeric(row.get('Ih_Corriente_Bobinas'), errors='coerce')
            r_mm = pd.to_numeric(row.get('r_Radio_Haz_mm'), errors='coerce')
            if pd.isna(U) or pd.isna(I_H) or pd.isna(r_mm): continue
            r = r_mm / 1000
            B = calcular_campo_pasco(I_H, R, N)
            y_vals.append(2 * U)
            x_vals.append((B * r)**2)

    elif equipo_nombre == "TELTRON TEL 2534":
        for _, row in datos.iterrows():
            U = pd.to_numeric(row.get('Va_Voltaje_Acelerador'), errors='coerce')
            I_H = pd.to_numeric(row.get('Ih_Corriente_Bobinas'), errors='coerce')
            if pd.isna(U) or pd.isna(I_H): continue
            y_vals.append(U)
            x_vals.append(I_H**2)

    elif equipo_nombre == "TELTRON Tipo S 1000617":
        if experimento == "Exp 2: Deflexion Magnetica Pura":
            k_B = equipos_parametros[equipo_nombre]["k_B"]
            for _, row in datos.iterrows():
                U = pd.to_numeric(row.get('Va_Voltaje_Anodo'), errors='coerce')
                I_H = pd.to_numeric(row.get('Ih_Corriente_Bobinas'), errors='coerce')
                c = pd.to_numeric(row.get('Coordenada_x'), errors='coerce')
                a = pd.to_numeric(row.get('Coordenada_y'), errors='coerce')
                if pd.isna(U) or pd.isna(I_H) or pd.isna(c) or pd.isna(a): continue
                r = calcular_r_geom_thomson(c, a)
                B = k_B * I_H
                y_vals.append(2 * U)
                x_vals.append((B * r)**2)

        elif experimento == "Exp 1: Balance de Campos (Fuerza Nula)":
            k_B = equipos_parametros[equipo_nombre]["k_B"]
            for _, row in datos.iterrows():
                U = pd.to_numeric(row.get('Va_Voltaje_Anodo'), errors='coerce')
                Vp = pd.to_numeric(row.get('Vp_Voltaje_Placas'), errors='coerce')
                I_H = pd.to_numeric(row.get('Ih_Corriente_Bobinas'), errors='coerce')
                d_mm = pd.to_numeric(row.get('Distancia_L_Nula'), errors='coerce')
                if pd.isna(U) or pd.isna(Vp) or pd.isna(I_H) or pd.isna(d_mm) or d_mm == 0: continue
                d = d_mm / 1000
                B = k_B * I_H
                E = Vp / d
                y_vals.append(2 * U)
                x_vals.append((E / B)**2)

    if len(x_vals) < 3:
        return None, None, None

    x_array = np.array(x_vals)
    y_array = np.array(y_vals)
    res = linregress(x_array, y_array)
    pendiente = res.slope
    incerteza_ajuste = res.stderr

    if equipo_nombre == "TELTRON TEL 2534":
        radios = []
        for _, row in datos.iterrows():
            if experimento == "Punto A - Cañon Axial (anillo lejano AA')":
                ae = pd.to_numeric(row.get('Distancia_AE_mm'), errors='coerce')
                d_aa = pd.to_numeric(row.get('Diametro_AA_mm'), errors='coerce')
                if pd.isna(ae) or pd.isna(d_aa) or d_aa == 0: continue
                radios.append(calcular_R_tel2534_punto_axial(ae, d_aa))
            elif experimento == "Punto E - Cañon Axial (anillo cercano EE')":
                d_ee = pd.to_numeric(row.get('Diametro_EE_mm'), errors='coerce')
                if pd.isna(d_ee) or d_ee == 0: continue
                radios.append(calcular_R_tel2534_punto_E(d_ee))
            elif experimento == "Perpendicular - anillo AA'":
                ae = pd.to_numeric(row.get('Distancia_AE_mm'), errors='coerce')
                if pd.isna(ae): continue
                radios.append(calcular_R_tel2534_perpendicular(ae))

        if radios:
            R_medio = np.mean(radios)
        else:
            st.warning("No hay mediciones geométricas válidas para calcular R en TEL 2534.")
            return None, None, None

        k_B = equipos_parametros[equipo_nombre]["k_B"]
        factor = 2 / (k_B**2)
        em_experimental = pendiente * (factor / (R_medio**2))
        incerteza_final = incerteza_ajuste * (factor / (R_medio**2))
    elif equipo_nombre == "TELTRON Tipo S 1000617" and experimento == "Exp 1: Balance de Campos (Fuerza Nula)":
        em_experimental = 1.0 / pendiente
        incerteza_final = incerteza_ajuste / (pendiente**2)
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
# APLICACIÓN PRINCIPAL
# =============================================================================

st.sidebar.write(f"Conectado como: **{st.session_state['correo']}**")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state["correo"] = None
    st.session_state["nombre"] = None
    st.session_state["autenticado"] = False
    st.rerun()

st.title("Laboratorio: Estimación e/m")
conn = st.connection("gsheets", type=GSheetsConnection)

tab1, tab2 = st.tabs(["Módulo de Adquisición", "Dashboard de Análisis"])

imagenes_equipos = {
    "PASCO SE-9629": "pasco_se9629.jpg",
    "TELTRON TEL 2534": "teltron_2534.jpg",
    "TELTRON Tipo S 1000617": "teltron_thomson.jpg"
}

# --- PESTAÑA 1: MÓDULO DE ADQUISICIÓN ---
with tab1:
    st.header("Ingreso de Mediciones por Lotes")

    equipo_seleccionado = st.selectbox("Seleccione Equipo", list(protocolo_adquisicion.keys()))

    if equipo_seleccionado:
        experimentos_disponibles = list(protocolo_adquisicion[equipo_seleccionado]["experimentos"].keys())
        experimento_seleccionado = st.selectbox("Seleccione Experimento", experimentos_disponibles)

        try:
            st.image(imagenes_equipos[equipo_seleccionado], caption=f"Montaje: {equipo_seleccionado}", width=400)
        except Exception:
            st.info("Sube la imagen del equipo al repositorio para visualizarla aquí.")

        st.markdown("---")
        st.subheader("Datos Generales e Incertidumbre")
        
        col_gen1, col_gen2 = st.columns(2)
        with col_gen1:
            correo = st.text_input("Correo Institucional", value=st.session_state['correo'], disabled=True)
            integrantes = st.text_input("Integrantes del grupo")
        with col_gen2:
            delta_v = st.number_input("Incertidumbre Voltaje (ΔV) [V]", value=1.0, format="%.2f", step=0.1)
            delta_i = st.number_input("Incertidumbre Corriente (ΔI) [A]", value=0.01, format="%.3f", step=0.01)
            delta_r = st.number_input("Incertidumbre Radio/Dist. (Δr) [mm]", value=1.0, format="%.2f", step=0.1)

        st.markdown("---")
        st.subheader("Tabla de Datos Experimentales")
        
        # Generar DataFrame vacío dinámicamente según el experimento seleccionado
        campos = protocolo_adquisicion[equipo_seleccionado]["experimentos"][experimento_seleccionado]["campos_requeridos"]
        columnas_dinamicas = {campo["nombre"]: [float(campo.get("valor_defecto", 0.0))] * 5 for campo in campos}
        df_vacio = pd.DataFrame(columnas_dinamicas)
        df_vacio.index = range(1, len(df_vacio) + 1)
        
        # El usuario edita los datos directamente
        df_editado = st.data_editor(df_vacio, num_rows="dynamic", use_container_width=True)

        if st.button("Procesar Lote y Guardar", type="primary"):
            # Encontrar qué columna almacena el voltaje acelerador o ánodo
            col_voltaje = [c for c in df_editado.columns if "Voltaje" in c][0]
            
            # Filtrar mediciones válidas
            df_validos = df_editado[df_editado[col_voltaje] > 0].copy()
            
            if df_validos.empty:
                st.warning("Debe ingresar al menos una medición válida para procesar.")
            else:
                # 1. Calcular e/m fila por fila
                df_validos['e_m_Calculado'] = df_validos.apply(
                    lambda row: calcular_em_fila(row, equipo_seleccionado, experimento_seleccionado), axis=1
                )
                
                # Descartar filas que dieron error matemático en el cálculo
                df_validos = df_validos.dropna(subset=['e_m_Calculado'])
                df_validos = df_validos[df_validos['e_m_Calculado'] > 0]
                
                if df_validos.empty:
                    st.warning("Las mediciones ingresadas no son suficientes o viables para calcular e/m.")
                else:
                    # 2. Propagación de error (Aproximación simplificada instrumental fila a fila)
                    termino_v = (delta_v / df_validos[col_voltaje])**2
                    termino_i = (2 * delta_i / df_validos['Ih_Corriente_Bobinas'])**2
                    df_validos['Error_Instrumental'] = df_validos['e_m_Calculado'] * np.sqrt(termino_v + termino_i)
                    
                    # =========================================================================
                    # 3. ANÁLISIS DE REGRESIÓN PARA EL LOTE EN VEZ DE PROMEDIO
                    # =========================================================================
                    x_vals = []
                    y_vals = []
                    
                    for _, row in df_validos.iterrows():
                        try:
                            if equipo_seleccionado == "PASCO SE-9629":
                                U = float(row.get('Va_Voltaje_Acelerador', 0))
                                I = float(row.get('Ih_Corriente_Bobinas', 0))
                                r = float(row.get('r_Radio_Haz_mm', 0)) / 1000.0
                                B = calcular_campo_pasco(I, equipos_parametros[equipo_seleccionado]["R"], equipos_parametros[equipo_seleccionado]["N"])
                                y_vals.append(2 * U)
                                x_vals.append((B * r)**2)
                                
                            elif equipo_seleccionado == "TELTRON TEL 2534":
                                U = float(row.get('Va_Voltaje_Acelerador', 0))
                                I = float(row.get('Ih_Corriente_Bobinas', 0))
                                y_vals.append(U)
                                x_vals.append(I**2)
                                
                            elif equipo_seleccionado == "TELTRON Tipo S 1000617":
                                if experimento_seleccionado == "Exp 2: Deflexion Magnetica Pura":
                                    U = float(row.get('Va_Voltaje_Anodo', 0))
                                    I = float(row.get('Ih_Corriente_Bobinas', 0))
                                    c = float(row.get('Coordenada_x', 0))
                                    a = float(row.get('Coordenada_y', 0))
                                    r = calcular_r_geom_thomson(c, a)
                                    B = equipos_parametros[equipo_seleccionado]["k_B"] * I
                                    y_vals.append(2 * U)
                                    x_vals.append((B * r)**2)
                                    
                                elif experimento_seleccionado == "Exp 1: Balance de Campos (Fuerza Nula)":
                                    U = float(row.get('Va_Voltaje_Anodo', 0))
                                    Vp = float(row.get('Vp_Voltaje_Placas', 0))
                                    I = float(row.get('Ih_Corriente_Bobinas', 0))
                                    d_mm = float(row.get('Distancia_L_Nula', 0))
                                    d = d_mm / 1000.0
                                    B = equipos_parametros[equipo_seleccionado]["k_B"] * I
                                    E = Vp / d
                                    y_vals.append(2 * U)
                                    x_vals.append((E / B)**2)
                        except Exception:
                            continue

                    # Extraer pendiente si hay 2 o más puntos
                    if len(x_vals) >= 2:
                        x_array = np.array(x_vals)
                        y_array = np.array(y_vals)
                        res = linregress(x_array, y_array)
                        pendiente = res.slope
                        incerteza_ajuste = res.stderr
                        
                        if equipo_seleccionado == "TELTRON TEL 2534":
                            radios = []
                            for _, row in df_validos.iterrows():
                                if "Punto A" in experimento_seleccionado:
                                    ae = float(row.get('Distancia_AE_mm', 80))
                                    d_aa = float(row.get('Diametro_AA_mm', 102))
                                    radios.append(calcular_R_tel2534_punto_axial(ae, d_aa))
                                elif "Punto E" in experimento_seleccionado:
                                    d_ee = float(row.get('Diametro_EE_mm', 102))
                                    radios.append(calcular_R_tel2534_punto_E(d_ee))
                                elif "Perpendicular" in experimento_seleccionado:
                                    ae = float(row.get('Distancia_AE_mm', 80))
                                    radios.append(calcular_R_tel2534_perpendicular(ae))
                            R_medio = np.mean(radios) if radios else 0.05
                            k_B = equipos_parametros[equipo_seleccionado]["k_B"]
                            factor = 2 / (k_B**2)
                            em_lote = pendiente * (factor / (R_medio**2))
                            em_std = incerteza_ajuste * (factor / (R_medio**2))
                            
                        elif equipo_seleccionado == "TELTRON Tipo S 1000617" and experimento_seleccionado == "Exp 1: Balance de Campos (Fuerza Nula)":
                            em_lote = 1.0 / pendiente
                            em_std = incerteza_ajuste / (pendiente**2)
                        else:
                            em_lote = pendiente
                            em_std = incerteza_ajuste
                            
                        metodo = "Regresión Lineal"
                    else:
                        # Si solo meten 1 dato, usamos el e/m puntual como salvavidas
                        em_lote = df_validos['e_m_Calculado'].iloc[0] if not df_validos.empty else 0.0
                        em_std = 0.0
                        metodo = "Medición Única"

                    err_lote = np.abs((em_lote - EM_TEORICO) / EM_TEORICO) * 100
                    # =========================================================================
                    
                    st.success(f"Se procesaron {len(df_validos)} mediciones utilizando {metodo}.")
                    col_res1, col_res2, col_res3 = st.columns(3)
                    col_res1.metric(label="e/m Lote (Pendiente)", value=f"{em_lote:.4e}")
                    col_res2.metric(label="Error Std (Ajuste)", value=f"± {em_std:.4e}")
                    
                    if err_lote <= 15.0:
                        col_res3.metric(label="Error % Lote", value=f"{err_lote:.2f} %", delta="Aceptable", delta_color="normal")
                    else:
                        col_res3.metric(label="Error % Lote", value=f"{err_lote:.2f} %", delta="Desviación Alta", delta_color="inverse")
                    
                    # 4. Guardar en Base de Datos Google Sheets
                    df_existente = conn.read()
                    filas_para_guardar = []
                    
                    for index, row in df_validos.iterrows():
                        nueva_fila_dict = {
                            "ID_Medicion": f"MED-{uuid.uuid4().hex[:12]}",
                            "Fecha_Ingreso": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "Correo": correo,
                            "Integrantes": integrantes,
                            "Equipo": equipo_seleccionado,
                            "Experimento": experimento_seleccionado,
                            "e_m_Calculado": row['e_m_Calculado'], # Mantiene el puntual para gráficos de puntos
                            "Error_Porcentual": err_lote,          # Asigna el error global de la regresión a toda la tanda
                            "Observaciones": f"Lote ({metodo}). e/m: {em_lote:.2e} ± {em_std:.2e}"
                        }
                        # Adjuntar los datos puros medidos
                        for campo in df_editado.columns:
                            nueva_fila_dict[campo] = row[campo]
                            
                        filas_para_guardar.append(nueva_fila_dict)
                    
                    df_nuevas_filas = pd.DataFrame(filas_para_guardar)
                    df_actualizado = pd.concat([df_existente, df_nuevas_filas], ignore_index=True)
                    
                    conn.update(worksheet="Sheet1", data=df_actualizado)
                    st.info("Datos del lote respaldados en la base institucional de Google Sheets.")

# --- PESTAÑA 2: DASHBOARD DE ANÁLISIS ---
with tab2:
    st.header("Análisis Histórico y Regresión")

    if st.button("Actualizar y Analizar Datos"):
        df_raw = conn.read()

        if df_raw.empty or 'Equipo' not in df_raw.columns:
            st.info("Aún no hay datos históricos válidos para analizar. Ingresa al menos una medición primero.")
        else:
            df_raw = df_raw.dropna(subset=['Equipo'])
            es_legado = df_raw['ID_Medicion'].isna() | (df_raw['ID_Medicion'].astype(str).str.strip() == '') if 'ID_Medicion' in df_raw.columns else pd.Series(True, index=df_raw.index)

            df_nuevo = df_raw[~es_legado].copy()

            # === GRÁFICO DERIVA TEMPORAL ===
            st.subheader("Evolución Temporal: Error Porcentual por Equipo")
            if not df_nuevo.empty and 'Error_Porcentual' in df_nuevo.columns:
                df_plot = df_nuevo.dropna(subset=['Error_Porcentual']).copy()
                df_plot['Fecha_Ingreso'] = pd.to_datetime(df_plot['Fecha_Ingreso'])
                df_plot['Error_Porcentual'] = pd.to_numeric(df_plot['Error_Porcentual'])
                
                # Gráfico interactivo separando los colores por Equipo
                st.scatter_chart(data=df_plot, x='Fecha_Ingreso', y='Error_Porcentual', color='Equipo')
            else:
                st.info("No hay datos nuevos con error porcentual calculado para graficar la deriva.")

            st.markdown("---")

            # === ANÁLISIS DE REGRESIÓN ===
            st.subheader("Análisis de Regresión: Mediciones Recientes")
            if not df_nuevo.empty and 'Experimento' in df_nuevo.columns:
                df_valido = limpiar_base_datos(df_nuevo)

                equipos_presentes = df_valido['Equipo'].unique()
                for eq in equipos_presentes:
                    st.write(f"### Equipo: {eq}")
                    experimentos_eq = df_valido[df_valido['Equipo'] == eq]['Experimento'].dropna().unique()

                    for exp in experimentos_eq:
                        st.write(f"**Experimento:** {exp}")
                        em, incerteza, fig = analisis_regresion_equipo(df_valido, eq, exp)

                        if fig:
                            st.pyplot(fig)
                            error_perc = np.abs((em - EM_TEORICO) / EM_TEORICO) * 100
                            st.metric(label="Error Porcentual (Ajuste vs Teórico)", value=f"{error_perc:.2f}%")
                            plt.close(fig)
            else:
                st.info("Aún no hay mediciones con geometría registrada para análisis de regresión.")
