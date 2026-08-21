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

# =============================================================================
# CONFIGURACIÓN BÁSICA DE LA PÁGINA (Debe ser el primer comando de Streamlit)
# =============================================================================
st.set_page_config(page_title="Proyecto Lab VI - Usach", layout="wide")

# =============================================================================
# MÓDULO 4: AUTENTICACIÓN OAUTH Y BARRERA DE SEGURIDAD
# =============================================================================

# FIX #1: se unifica todo bajo una sola clave de sesión: "correo".
# Antes existían "user_email" (inicializada pero nunca actualizada) y
# "correo" (actualizada pero no usada en el sidebar/formulario). Ahora solo
# se usa "correo" en toda la app.
if "correo" not in st.session_state:
    st.session_state["correo"] = None
if "nombre" not in st.session_state:
    st.session_state["nombre"] = None

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
        access_token = result["token"]["access_token"]

        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get("https://www.googleapis.com/oauth2/v1/userinfo", headers=headers)
        user_info = resp.json()

        correo_usuario = user_info.get("email", "")
        nombre_usuario = user_info.get("name", "")

        if correo_usuario.endswith("@usach.cl"):
            st.session_state.autenticado = True
            st.session_state.correo = correo_usuario
            st.session_state.nombre = nombre_usuario
            st.rerun()
        else:
            st.error(f"Acceso denegado: El correo {correo_usuario} no pertenece a la universidad.")
            # FIX #9: revocamos usando el token local recién obtenido, no uno de session_state
            requests.post(REVOKE_URL, data={"token": access_token})

    st.stop()

# =============================================================================
# MÓDULO 1: CONSTANTES, PARAMETRIZACIÓN Y FUNCIONES MATEMÁTICAS
# =============================================================================

MU_0 = 4 * np.pi * 10**-7
EM_TEORICO = 1.758820e11

equipos_parametros = {
    "PASCO SE-9629": {
        "R": 0.158,
        "N": 130
    },
    "TELTRON TEL 2534": {
        "D": 0.138,
        "k_B": 4.17e-3
    },
    "TELTRON Tipo S 1000617": {
        "R": 0.068,
        "N": 320,
        "k_B": 4.2e-3
    }
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
    # FIX #12: reestructurado por completo según la guía oficial del TEL 2534
    # (Teltron Limited / traducción USACH). El equipo tiene, en realidad, TRES
    # configuraciones de medición distintas, cada una con su propia geometría
    # para calcular R — no dos experimentos genéricos "Axial"/"Perpendicular"
    # con un solo campo "Distancia" como estaba antes.
    "TELTRON TEL 2534": {
        "experimentos": {
            "Punto A - Cañon Axial (anillo lejano AA')": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "rango_valido": (0, 300), "descripcion": "Típico 80-140V según guía"},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "rango_valido": (0, 3)},
                    {"nombre": "Vp_Voltaje_Placas_Enfoque", "unidad": "V", "tipo": "float", "rango_valido": (0, 6), "descripcion": "Solo para enfocar el haz, no entra en la fórmula"},
                    {"nombre": "Distancia_AE_mm", "unidad": "mm", "tipo": "float", "descripcion": "Distancia axial medida entre anillos AA' y EE' (nominal 80mm)", "valor_defecto": 80.0},
                    {"nombre": "Diametro_AA_mm", "unidad": "mm", "tipo": "float", "descripcion": "Diámetro medido del anillo AA' (nominal 102mm)", "valor_defecto": 102.0}
                ]
            },
            "Punto E - Cañon Axial (anillo cercano EE')": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "rango_valido": (0, 300), "descripcion": "Típico 80-140V según guía"},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "rango_valido": (0, 3)},
                    {"nombre": "Vp_Voltaje_Placas_Enfoque", "unidad": "V", "tipo": "float", "rango_valido": (0, 6), "descripcion": "Solo para enfocar el haz, no entra en la fórmula"},
                    {"nombre": "Diametro_EE_mm", "unidad": "mm", "tipo": "float", "descripcion": "Diámetro medido del anillo EE' (nominal 102mm)", "valor_defecto": 102.0}
                ]
            },
            "Perpendicular - anillo AA'": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "rango_valido": (0, 300), "descripcion": "Típico 100-140V según guía"},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "rango_valido": (0, 3)},
                    {"nombre": "Vp_Voltaje_Placas_Enfoque", "unidad": "V", "tipo": "float", "rango_valido": (0, 6), "descripcion": "Solo para enfocar el haz, no entra en la fórmula"},
                    {"nombre": "Distancia_AE_mm", "unidad": "mm", "tipo": "float", "descripcion": "Distancia axial medida entre anillos AA' y EE' (nominal 80mm), usada como R=AE/2", "valor_defecto": 80.0}
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
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "rango_valido": (0, 3)},
                    {"nombre": "Distancia_L_Nula", "unidad": "mm", "tipo": "float"}
                ]
            },
            "Exp 2: Deflexion Magnetica Pura": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Anodo", "unidad": "V", "tipo": "float", "rango_valido": (2000, 5000)},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "rango_valido": (0, 3)},
                    {"nombre": "Coordenada_x", "unidad": "mm", "tipo": "float"},
                    {"nombre": "Coordenada_y", "unidad": "mm", "tipo": "float"}
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


# FIX #12: reemplaza la anterior calcular_r_geom_tel2534 (que asumía,
# incorrectamente, la misma geometría genérica del tubo Thomson usando el
# diámetro fijo de las bobinas D=0.138m). Según la guía oficial del TEL 2534
# ("The Principle of Pythagoras and the Fused Rings AA' and EE'", ec. 16.03),
# el radio de curvatura R se calcula distinto según el punto de referencia:
#
# - Punto A (cañón axial, anillo lejano AA'): x = AE + 2mm (el haz emerge
#   ~2mm antes del anillo EE'), y = AA'/2 → R = (x²+y²)/(2y)
# - Punto E (cañón axial, anillo cercano EE'): x = 2mm (offset fijo,
#   la distancia AE no aplica aquí), y = EE'/2 → R = (x²+y²)/(2y)
# - Perpendicular (anillo AA'): R = AE/2 (ecuación 16.18 de la guía,
#   geometría distinta porque el cañón perpendicular genera un círculo
#   completo, no un arco)
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


# =============================================================================
# MÓDULO 2: SISTEMA DE ALERTAS Y LIMPIEZA LÓGICA (SOFT DELETION)
# =============================================================================

def limpiar_base_datos(df, df_anulaciones=None):
    if df_anulaciones is not None and not df_anulaciones.empty:
        df = df[~df['ID_Medicion'].isin(df_anulaciones['ID_Medicion_Anular'])]

    invalida = pd.Series(False, index=df.index)

    # FIX #4: antes solo se validaba 'Va_Voltaje_Acelerador', dejando pasar
    # sin filtrar cualquier voltaje <= 0 del TELTRON Tipo S, que usa el
    # nombre de columna 'Va_Voltaje_Anodo'.
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
        st.warning(f"Datos insuficientes para análisis de regresión en {equipo_nombre}.")
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
            # FIX #6: se descartan filas con cualquier valor faltante/NaN
            # antes de que contaminen silenciosamente la regresión.
            if pd.isna(U) or pd.isna(I_H) or pd.isna(r_mm):
                continue
            r = r_mm / 1000
            B = calcular_campo_pasco(I_H, R, N)
            y_vals.append(2 * U)
            x_vals.append((B * r) ** 2)

    elif equipo_nombre == "TELTRON TEL 2534":
        for _, row in datos.iterrows():
            U = pd.to_numeric(row.get('Va_Voltaje_Acelerador'), errors='coerce')
            I_H = pd.to_numeric(row.get('Ih_Corriente_Bobinas'), errors='coerce')
            if pd.isna(U) or pd.isna(I_H):
                continue
            y_vals.append(U)
            x_vals.append(I_H ** 2)

    elif equipo_nombre == "TELTRON Tipo S 1000617":
        if experimento == "Exp 2: Deflexion Magnetica Pura":
            k_B = equipos_parametros[equipo_nombre]["k_B"]
            for _, row in datos.iterrows():
                U = pd.to_numeric(row.get('Va_Voltaje_Anodo'), errors='coerce')
                I_H = pd.to_numeric(row.get('Ih_Corriente_Bobinas'), errors='coerce')
                c = pd.to_numeric(row.get('Coordenada_x'), errors='coerce')
                a = pd.to_numeric(row.get('Coordenada_y'), errors='coerce')
                if pd.isna(U) or pd.isna(I_H) or pd.isna(c) or pd.isna(a):
                    continue
                r = calcular_r_geom_thomson(c, a)
                B = k_B * I_H
                y_vals.append(2 * U)
                x_vals.append((B * r) ** 2)

        # FIX #3: antes "Exp 1: Balance de Campos" se guardaba en el Sheet
        # pero nunca entraba a ninguna rama de análisis. En el balance de
        # fuerzas (fuerza eléctrica = fuerza magnética, deflexión nula),
        # la relación clásica es: E = v*B  =>  Vp/d = v*B, y con
        # v = sqrt(2*e*Va/m) se obtiene una recta de la forma:
        #   (Vp / (d * B))^2  =  (2/m_e_ratio) * Va   -> y = 2*Va, x = (Vp/(d*B))^2
        # Aquí "d" es la separación entre placas; como el protocolo no
        # provee ese dato por separado, se usa Distancia_L_Nula como
        # proxy de la geometría de placas.
        # NOTA: verifica esta relación contra la guía específica de tu
        # profesor antes de usar los resultados en el informe — el nombre
        # "Distancia_L_Nula" sugiere una longitud de trayectoria, y podría
        # requerir un factor geométrico adicional que este código no conoce.
        elif experimento == "Exp 1: Balance de Campos (Fuerza Nula)":
            k_B = equipos_parametros[equipo_nombre]["k_B"]
            for _, row in datos.iterrows():
                U = pd.to_numeric(row.get('Va_Voltaje_Anodo'), errors='coerce')
                Vp = pd.to_numeric(row.get('Vp_Voltaje_Placas'), errors='coerce')
                I_H = pd.to_numeric(row.get('Ih_Corriente_Bobinas'), errors='coerce')
                d_mm = pd.to_numeric(row.get('Distancia_L_Nula'), errors='coerce')
                if pd.isna(U) or pd.isna(Vp) or pd.isna(I_H) or pd.isna(d_mm) or d_mm == 0:
                    continue
                d = d_mm / 1000
                B = k_B * I_H
                E = Vp / d
                y_vals.append(2 * U)
                x_vals.append((E / B) ** 2)

    if len(x_vals) < 3:
        st.warning("No hay suficientes datos válidos para este equipo/experimento.")
        return None, None, None

    x_array = np.array(x_vals)
    y_array = np.array(y_vals)
    res = linregress(x_array, y_array)
    pendiente = res.slope
    incerteza_ajuste = res.stderr

    if equipo_nombre == "TELTRON TEL 2534":
        # FIX #12: R ya no se promedia con una fórmula genérica; se calcula
        # fila a fila según el punto de referencia (A, E o Perpendicular),
        # siguiendo exactamente la geometría de la guía oficial.
        radios = []
        for _, row in datos.iterrows():
            if experimento == "Punto A - Cañon Axial (anillo lejano AA')":
                ae = pd.to_numeric(row.get('Distancia_AE_mm'), errors='coerce')
                d_aa = pd.to_numeric(row.get('Diametro_AA_mm'), errors='coerce')
                if pd.isna(ae) or pd.isna(d_aa) or d_aa == 0:
                    continue
                radios.append(calcular_R_tel2534_punto_axial(ae, d_aa))
            elif experimento == "Punto E - Cañon Axial (anillo cercano EE')":
                d_ee = pd.to_numeric(row.get('Diametro_EE_mm'), errors='coerce')
                if pd.isna(d_ee) or d_ee == 0:
                    continue
                radios.append(calcular_R_tel2534_punto_E(d_ee))
            elif experimento == "Perpendicular - anillo AA'":
                ae = pd.to_numeric(row.get('Distancia_AE_mm'), errors='coerce')
                if pd.isna(ae):
                    continue
                radios.append(calcular_R_tel2534_perpendicular(ae))

        if radios:
            R_medio = np.mean(radios)
        else:
            st.warning("No hay mediciones geométricas válidas (distancia AE / diámetro de anillo) para calcular R en TEL 2534.")
            return None, None, None

        # El factor ya no es el número mágico hardcodeado 1.15e5; se deriva
        # de k_B (equipos_parametros), quedando sincronizado si cambia.
        k_B = equipos_parametros[equipo_nombre]["k_B"]
        factor = 2 / (k_B ** 2)
        em_experimental = pendiente * (factor / (R_medio ** 2))
        incerteza_final = incerteza_ajuste * (factor / (R_medio ** 2))
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
# APLICACIÓN PRINCIPAL (Carga solo si pasó la autenticación)
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
# Diccionario con las rutas de las imágenes (ajusta los nombres a los de tus archivos)
imagenes_equipos = {
    "PASCO SE-9629": "pasco_se9629.jpg",         # Reemplaza con la ruta o URL real
    "TELTRON TEL 2534": "teltron_2534.jpg",      # Reemplaza con la ruta o URL real
    "TELTRON Tipo S 1000617": "teltron_thomson.jpg" # Reemplaza con la ruta o URL real
}
# --- PESTAÑA 1: MÓDULO DE ADQUISICIÓN ---
with tab1:
    st.header("Ingreso de Mediciones")

    equipo_seleccionado = st.selectbox("Seleccione Equipo", list(protocolo_adquisicion.keys()))

    if equipo_seleccionado:
        experimentos_disponibles = list(protocolo_adquisicion[equipo_seleccionado]["experimentos"].keys())
        experimento_seleccionado = st.selectbox("Seleccione Experimento", experimentos_disponibles)

        campos = protocolo_adquisicion[equipo_seleccionado]["experimentos"][experimento_seleccionado]["campos_requeridos"]
        try:
            st.image(imagenes_equipos[equipo_seleccionado], caption=f"Montaje: {equipo_seleccionado}", width=400)
        except Exception as e:
            st.info("Sube la imagen del equipo al repositorio para visualizarla aquí.")
        with st.form("formulario_ingreso"):
            st.subheader("Datos Generales")
            correo = st.text_input("Correo Institucional", value=st.session_state['correo'], disabled=True)
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
                        # FIX #7: ahora se pasa también max_value cuando hay
                        # rango_valido definido, en vez de solo el mínimo.
                        # FIX #13: soporte para "valor_defecto" (precarga los
                        # valores nominales de fábrica, ej. AE=80mm, anillo=102mm
                        # según la guía del TEL 2534), para que el usuario solo
                        # tenga que ajustarlo si su medición real difiere.
                        valor_defecto = campo.get("valor_defecto")
                        if "rango_valido" in campo:
                            min_val = float(campo["rango_valido"][0])
                            max_val = float(campo["rango_valido"][1])
                            label += f" (rango válido: {min_val}–{max_val})"
                            valores_ingresados[nombre] = st.number_input(
                                label, min_value=min_val, max_value=max_val,
                                value=float(valor_defecto) if valor_defecto is not None else min_val,
                                format="%.4f"
                            )
                        else:
                            valores_ingresados[nombre] = st.number_input(
                                label,
                                value=float(valor_defecto) if valor_defecto is not None else 0.0,
                                format="%.4f"
                            )

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

                    # FIX #8: se usa un UUID en vez de timestamp truncado a
                    # segundos, para evitar colisiones de ID si dos grupos
                    # guardan datos en el mismo segundo.
                    nueva_fila_dict = {
                        "ID_Medicion": f"MED-{uuid.uuid4().hex[:12]}",
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

        if df_raw.empty or "Equipo" not in df_raw.columns:
            st.info(
                "Aún no hay datos históricos válidos para analizar. "
                "Ingresa al menos una medición en la pestaña 'Módulo de Adquisición' primero."
            )
        else:
            df_raw = df_raw.dropna(subset=['Equipo'])

            # FIX #11: COMPATIBILIDAD CON EL FORMATO ANTERIOR.
            # La versión anterior del código guardaba columnas distintas
            # (Ib_Corriente_Bobinas, Parametro_Geometrico, e_m_Calculado,
            # Error_Porcentual...) y nunca escribía 'ID_Medicion' ni
            # 'Experimento'. Como ambas versiones escriben en la misma hoja
            # ("Sheet1"), el dataframe leído puede traer una mezcla de filas
            # viejas y nuevas.
            #
            # En vez de intentar traducir 'Parametro_Geometrico' al nuevo
            # esquema geométrico (Distancia_EE/AA, Coordenada_x/y, etc.) —
            # lo cual requeriría adivinar qué representaba ese campo en cada
            # fila vieja, arriesgando resultados físicamente incorrectos —
            # se identifican las filas "legado" (sin ID_Medicion) y se
            # muestran usando el e/m que el código anterior YA calculó y
            # guardó en su momento. No se recalcula nada para ellas.
            if "ID_Medicion" in df_raw.columns:
                es_legado = df_raw["ID_Medicion"].isna() | (df_raw["ID_Medicion"].astype(str).str.strip() == "")
            else:
                # Si la columna ni siquiera existe, todo lo que hay es legado.
                es_legado = pd.Series(True, index=df_raw.index)

            df_legado = df_raw[es_legado].copy()
            df_nuevo = df_raw[~es_legado].copy()

            # ---------------------------------------------------------
            # SECCIÓN A: DATOS NUEVOS (formato con geometría registrada)
            # ---------------------------------------------------------
            st.subheader("Mediciones nuevas (con geometría registrada)")
            if not df_nuevo.empty and "Experimento" in df_nuevo.columns:
                df_valido = limpiar_base_datos(df_nuevo)
                st.dataframe(df_valido)

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
                            st.metric(label="Error Porcentual (vs Teórico)", value=f"{error_perc:.2f}%")
                            plt.close(fig)
            else:
                st.info("Aún no hay mediciones en el formato nuevo.")

            # ---------------------------------------------------------
            # SECCIÓN B: DATOS HISTÓRICOS (formato de la versión anterior)
            # ---------------------------------------------------------
            if not df_legado.empty:
                st.markdown("---")
                st.subheader("Mediciones históricas (formato anterior)")
                st.caption(
                    "Estas filas fueron guardadas por una versión anterior de la app, con un "
                    "esquema de columnas distinto. Se muestran con el valor de e/m que esa "
                    "versión ya calculó y guardó — no se recalculan aquí, para no adivinar "
                    "conversiones geométricas que podrían ser incorrectas."
                )
                st.dataframe(df_legado)

                if "e_m_Calculado" in df_legado.columns:
                    df_legado_num = df_legado.copy()
                    df_legado_num["e_m_Calculado"] = pd.to_numeric(df_legado_num["e_m_Calculado"], errors="coerce")
                    if "Error_Porcentual" in df_legado_num.columns:
                        df_legado_num["Error_Porcentual"] = pd.to_numeric(df_legado_num["Error_Porcentual"], errors="coerce")

                    df_legado_num = df_legado_num.dropna(subset=["e_m_Calculado"])
                    df_legado_num = df_legado_num[df_legado_num["e_m_Calculado"] != 0]

                    if not df_legado_num.empty:
                        st.write("**Resumen estadístico por equipo (histórico):**")
                        resumen = df_legado_num.groupby("Equipo").agg(
                            n_mediciones=("e_m_Calculado", "count"),
                            em_promedio=("e_m_Calculado", "mean"),
                            em_std=("e_m_Calculado", "std"),
                        )
                        if "Error_Porcentual" in df_legado_num.columns:
                            resumen["error_pct_promedio"] = df_legado_num.groupby("Equipo")["Error_Porcentual"].mean()
                        st.dataframe(resumen)
                    else:
                        st.info("Las filas históricas no tienen valores de e/m calculados válidos para resumir.")
                else:
                    st.info(
                        "Las filas históricas no tienen la columna 'e_m_Calculado', "
                        "así que solo se muestran como tabla de referencia."
                    )

            if df_nuevo.empty and df_legado.empty:
                st.info("Aún no hay datos históricos para analizar.")
