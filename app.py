import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import linregress
from streamlit_gsheets import GSheetsConnection
from streamlit_oauth import OAuth2Component
from datetime import datetime
import uuid
import requests

# =============================================================================
# CONFIGURACIÓN BÁSICA DE LA PÁGINA
# =============================================================================
st.set_page_config(page_title="Proyecto Lab VI - Usach", layout="wide")

UMBRAL_ERROR_PCT = 15.0
HOJA_DATOS = "Datos_Lab"
HOJA_ANULACIONES = "Anulaciones"

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
EM_TEORICO_UNIDAD = "C/kg"

UNIDADES_COLUMNAS = {
    "Va_Voltaje_Acelerador": "V",
    "Va_Voltaje_Anodo": "V",
    "Ih_Corriente_Bobinas": "A",
    "r_Radio_Haz_mm": "mm",
    "Vp_Voltaje_Placas_Enfoque": "V",
    "Vp_Voltaje_Placas": "V",
    "Distancia_AE_mm": "mm",
    "Diametro_AA_mm": "mm",
    "Diametro_EE_mm": "mm",
    "Distancia_L_Nula": "mm",
    "Coordenada_x": "mm",
    "Coordenada_y": "mm",
    "e_m_Calculado": "C/kg",
    "e_m_Lote": "C/kg",
    "Error_Porcentual": "%",
    "Error_Instrumental": "C/kg",
    "delta_v": "V",
    "delta_i": "A",
    "delta_r": "mm",
}


def etiqueta_con_unidad(nombre):
    unidad = UNIDADES_COLUMNAS.get(nombre)
    if unidad:
        return f"{nombre} [{unidad}]"
    return nombre


def df_con_unidades(df):
    if df is None or df.empty:
        return df
    return df.rename(columns={c: etiqueta_con_unidad(c) for c in df.columns})


FORMAS_ALTAIR_EQUIPO = {
    "PASCO SE-9629": "circle",
    "TELTRON TEL 2534": "square",
    "TELTRON Tipo S 1000617": "triangle-up",
}
COLORES_ALTAIR_EQUIPO = {
    "PASCO SE-9629": "#1f77b4",
    "TELTRON TEL 2534": "#ff7f0e",
    "TELTRON Tipo S 1000617": "#2ca02c",
}
FORMAS_ALTAIR_EXTRA = ["diamond", "cross", "triangle-down", "triangle-right", "wedge", "arrow"]
COLORES_ALTAIR_EXTRA = ["#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]


def escalas_visuales_equipo(equipos):
    domain, formas, colores = [], [], []
    extra_i = 0
    for eq in equipos:
        domain.append(eq)
        if eq in FORMAS_ALTAIR_EQUIPO:
            formas.append(FORMAS_ALTAIR_EQUIPO[eq])
            colores.append(COLORES_ALTAIR_EQUIPO[eq])
        else:
            formas.append(FORMAS_ALTAIR_EXTRA[extra_i % len(FORMAS_ALTAIR_EXTRA)])
            colores.append(COLORES_ALTAIR_EXTRA[extra_i % len(COLORES_ALTAIR_EXTRA)])
            extra_i += 1
    return domain, formas, colores


def mostrar_grafico_error_interactivo(df, titulo, legend=True, umbral=UMBRAL_ERROR_PCT):
    df_chart = df.copy()
    df_chart["Equipo"] = df_chart["Equipo"].astype(str)
    df_chart["Fecha_Ingreso"] = pd.to_datetime(df_chart["Fecha_Ingreso"], errors="coerce")
    df_chart["Fecha"] = df_chart["Fecha_Ingreso"].dt.normalize()
    df_chart = df_chart.dropna(subset=["Fecha", "Error_Porcentual"])
    if df_chart.empty:
        st.info("No hay puntos válidos para graficar.")
        return

    equipos = list(df_chart["Equipo"].dropna().unique())
    domain, formas, colores = escalas_visuales_equipo(equipos)

    tooltips = [
        {"field": "Fecha", "type": "temporal", "title": "Fecha", "format": "%d/%m/%Y"},
        {"field": "Error_Porcentual", "type": "quantitative", "title": "Error porcentual [%]", "format": ".2f"},
        {"field": "Equipo", "type": "nominal", "title": "Equipo"},
    ]
    if "Experimento" in df_chart.columns:
        tooltips.append({"field": "Experimento", "type": "nominal", "title": "Experimento"})
    if "e_m_Calculado" in df_chart.columns:
        tooltips.append({"field": "e_m_Calculado", "type": "quantitative", "title": "e/m [C/kg]", "format": ".3e"})
    if "ID_Lote" in df_chart.columns:
        tooltips.append({"field": "ID_Lote", "type": "nominal", "title": "Lote"})
    if "n_mediciones" in df_chart.columns:
        tooltips.append({"field": "n_mediciones", "type": "quantitative", "title": "Mediciones del lote"})

    spec = {
        "title": titulo,
        "height": 360,
        "layer": [
            {
                "mark": {"type": "rule", "strokeDash": [6, 4], "color": "#c0392b", "size": 2},
                "encoding": {
                    "y": {"datum": umbral, "type": "quantitative"},
                    "tooltip": {"value": f"Umbral de tolerancia ({umbral:.0f} %)"},
                },
            },
            {
                "mark": {"type": "point", "filled": True, "size": 90},
                "encoding": {
                    "x": {
                        "field": "Fecha",
                        "type": "temporal",
                        "timeUnit": "yearmonthdate",
                        "title": "Fecha",
                        "axis": {"format": "%d/%m/%Y", "labelAngle": -35},
                    },
                    "y": {"field": "Error_Porcentual", "type": "quantitative", "title": "Error porcentual [%]"},
                    "color": {
                        "field": "Equipo",
                        "type": "nominal",
                        "scale": {"domain": domain, "range": colores},
                        "legend": {"title": "Equipo"} if legend else None,
                    },
                    "shape": {
                        "field": "Equipo",
                        "type": "nominal",
                        "scale": {"domain": domain, "range": formas},
                        "legend": {"title": "Símbolo"} if legend else None,
                    },
                    "tooltip": tooltips,
                },
            },
        ],
    }
    st.vega_lite_chart(df_chart, spec, use_container_width=True)


def column_config_con_unidades(campos):
    config = {}
    for campo in campos:
        nombre = campo["nombre"]
        unidad = campo.get("unidad", UNIDADES_COLUMNAS.get(nombre, ""))
        label = f"{nombre} [{unidad}]" if unidad else nombre
        help_txt = campo.get("descripcion", "")
        if unidad:
            help_txt = (help_txt + " | " if help_txt else "") + f"Unidad: {unidad}"
        rango = campo.get("rango_valido")
        kwargs = {
            "label": label,
            "help": help_txt or None,
            "format": "%.4f",
        }
        if rango:
            kwargs["min_value"] = float(rango[0])
            kwargs["max_value"] = float(rango[1])
            help_extra = f"Rango válido: {rango[0]} – {rango[1]} {unidad}".strip()
            kwargs["help"] = (help_txt + " | " if help_txt else "") + help_extra
        config[nombre] = st.column_config.NumberColumn(**kwargs)
    return config


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
                    {"nombre": "r_Radio_Haz_mm", "unidad": "mm", "tipo": "float", "rango_valido": (0, 80),
                     "descripcion": "Promedio de ambos lados"}
                ]
            }
        }
    },
    "TELTRON TEL 2534": {
        "experimentos": {
            "Punto A - Cañon Axial (anillo lejano AA')": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 500)},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 5)},
                    {"nombre": "Vp_Voltaje_Placas_Enfoque", "unidad": "V", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 500)},
                    {"nombre": "Distancia_AE_mm", "unidad": "mm", "tipo": "float", "valor_defecto": 80.0, "rango_valido": (0, 200)},
                    {"nombre": "Diametro_AA_mm", "unidad": "mm", "tipo": "float", "valor_defecto": 102.0, "rango_valido": (0, 200)}
                ]
            },
            "Punto E - Cañon Axial (anillo cercano EE')": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 500)},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 5)},
                    {"nombre": "Vp_Voltaje_Placas_Enfoque", "unidad": "V", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 500)},
                    {"nombre": "Diametro_EE_mm", "unidad": "mm", "tipo": "float", "valor_defecto": 102.0, "rango_valido": (0, 200)}
                ]
            },
            "Perpendicular - anillo AA'": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Acelerador", "unidad": "V", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 500)},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 5)},
                    {"nombre": "Vp_Voltaje_Placas_Enfoque", "unidad": "V", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 500)},
                    {"nombre": "Distancia_AE_mm", "unidad": "mm", "tipo": "float", "valor_defecto": 80.0, "rango_valido": (0, 200)}
                ]
            }
        }
    },
    "TELTRON Tipo S 1000617": {
        "experimentos": {
            "Exp 1: Balance de Campos (Fuerza Nula)": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Anodo", "unidad": "V", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 500)},
                    {"nombre": "Vp_Voltaje_Placas", "unidad": "V", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 500)},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 5)},
                    {"nombre": "Distancia_L_Nula", "unidad": "mm", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 80)}
                ]
            },
            "Exp 2: Deflexion Magnetica Pura": {
                "campos_requeridos": [
                    {"nombre": "Va_Voltaje_Anodo", "unidad": "V", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 500)},
                    {"nombre": "Ih_Corriente_Bobinas", "unidad": "A", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 5)},
                    {"nombre": "Coordenada_x", "unidad": "mm", "tipo": "float", "valor_defecto": 47.0, "rango_valido": (0, 150)},
                    {"nombre": "Coordenada_y", "unidad": "mm", "tipo": "float", "valor_defecto": 0.0, "rango_valido": (0, 80)}
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


def derivada_r_thomson(c_mm, a_mm, dc_mm, da_mm):
    """Incerteza absoluta de r = (c² + a²)/(2a) en metros."""
    c = c_mm / 1000.0
    a = a_mm / 1000.0
    dc = dc_mm / 1000.0
    da = da_mm / 1000.0
    if a == 0:
        return np.nan
    dr_dc = c / a
    dr_da = 0.5 - (c ** 2) / (2 * a ** 2)
    return abs(dr_dc) * dc + abs(dr_da) * da


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
    try:
        if equipo == "PASCO SE-9629":
            U = float(row.get('Va_Voltaje_Acelerador', 0))
            I = float(row.get('Ih_Corriente_Bobinas', 0))
            r = float(row.get('r_Radio_Haz_mm', 0)) / 1000.0
            if U <= 0 or I <= 0 or r <= 0:
                return np.nan
            B = calcular_campo_pasco(I, equipos_parametros[equipo]["R"], equipos_parametros[equipo]["N"])
            return (2 * U) / ((B * r) ** 2)

        elif equipo == "TELTRON TEL 2534":
            U = float(row.get('Va_Voltaje_Acelerador', 0))
            I = float(row.get('Ih_Corriente_Bobinas', 0))
            if U <= 0 or I <= 0:
                return np.nan

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
            else:
                return np.nan

            if R <= 0:
                return np.nan
            k_B = equipos_parametros[equipo]["k_B"]
            factor = 2 / (k_B ** 2)
            return (U / (I ** 2)) * (factor / (R ** 2))

        elif equipo == "TELTRON Tipo S 1000617":
            if experimento == "Exp 2: Deflexion Magnetica Pura":
                U = float(row.get('Va_Voltaje_Anodo', 0))
                I = float(row.get('Ih_Corriente_Bobinas', 0))
                c = float(row.get('Coordenada_x', 0))
                a = float(row.get('Coordenada_y', 0))
                if U <= 0 or I <= 0 or a <= 0:
                    return np.nan
                r = calcular_r_geom_thomson(c, a)
                B = equipos_parametros[equipo]["k_B"] * I
                return (2 * U) / ((B * r) ** 2)

            elif experimento == "Exp 1: Balance de Campos (Fuerza Nula)":
                U = float(row.get('Va_Voltaje_Anodo', 0))
                Vp = float(row.get('Vp_Voltaje_Placas', 0))
                I = float(row.get('Ih_Corriente_Bobinas', 0))
                d_mm = float(row.get('Distancia_L_Nula', 0))
                if U <= 0 or I <= 0 or Vp <= 0 or d_mm <= 0:
                    return np.nan
                d = d_mm / 1000.0
                B = equipos_parametros[equipo]["k_B"] * I
                E = Vp / d
                return ((E / B) ** 2) / (2 * U)
    except Exception:
        return np.nan
    return np.nan


def calcular_error_instrumental(row, equipo, experimento, delta_v, delta_i, delta_r):
    """Propagación relativa según e/m ∝ U / (I² R²) o la variante de fuerza nula."""
    em = pd.to_numeric(row.get("e_m_Calculado"), errors="coerce")
    if pd.isna(em) or em <= 0:
        return np.nan

    terminos = []

    def _term(coef, valor, delta):
        valor = pd.to_numeric(valor, errors="coerce")
        if pd.isna(valor) or valor == 0 or delta is None:
            return
        terminos.append((coef * float(delta) / float(valor)) ** 2)

    if equipo == "PASCO SE-9629":
        _term(1.0, row.get("Va_Voltaje_Acelerador"), delta_v)
        _term(2.0, row.get("Ih_Corriente_Bobinas"), delta_i)
        _term(2.0, row.get("r_Radio_Haz_mm"), delta_r)

    elif equipo == "TELTRON TEL 2534":
        _term(1.0, row.get("Va_Voltaje_Acelerador"), delta_v)
        _term(2.0, row.get("Ih_Corriente_Bobinas"), delta_i)
        if "Punto A" in experimento:
            ae = pd.to_numeric(row.get("Distancia_AE_mm"), errors="coerce")
            d_aa = pd.to_numeric(row.get("Diametro_AA_mm"), errors="coerce")
            R = calcular_R_tel2534_punto_axial(ae, d_aa) if pd.notna(ae) and pd.notna(d_aa) else np.nan
            dR = derivada_r_thomson(ae + 2.0, d_aa / 2.0, delta_r, delta_r / 2.0) if pd.notna(ae) and pd.notna(d_aa) else np.nan
        elif "Punto E" in experimento:
            d_ee = pd.to_numeric(row.get("Diametro_EE_mm"), errors="coerce")
            R = calcular_R_tel2534_punto_E(d_ee) if pd.notna(d_ee) else np.nan
            dR = derivada_r_thomson(2.0, d_ee / 2.0, 0.0, delta_r / 2.0) if pd.notna(d_ee) else np.nan
        elif "Perpendicular" in experimento:
            ae = pd.to_numeric(row.get("Distancia_AE_mm"), errors="coerce")
            R = calcular_R_tel2534_perpendicular(ae) if pd.notna(ae) else np.nan
            dR = (delta_r / 1000.0) / 2.0 if pd.notna(ae) else np.nan
        else:
            R, dR = np.nan, np.nan
        if pd.notna(R) and R > 0 and pd.notna(dR):
            terminos.append((2.0 * dR / R) ** 2)

    elif equipo == "TELTRON Tipo S 1000617":
        if experimento == "Exp 2: Deflexion Magnetica Pura":
            _term(1.0, row.get("Va_Voltaje_Anodo"), delta_v)
            _term(2.0, row.get("Ih_Corriente_Bobinas"), delta_i)
            c = pd.to_numeric(row.get("Coordenada_x"), errors="coerce")
            a = pd.to_numeric(row.get("Coordenada_y"), errors="coerce")
            if pd.notna(c) and pd.notna(a) and a > 0:
                r = calcular_r_geom_thomson(c, a)
                dr = derivada_r_thomson(c, a, delta_r, delta_r)
                if r > 0 and pd.notna(dr):
                    terminos.append((2.0 * dr / r) ** 2)
        elif experimento == "Exp 1: Balance de Campos (Fuerza Nula)":
            _term(1.0, row.get("Va_Voltaje_Anodo"), delta_v)
            _term(2.0, row.get("Vp_Voltaje_Placas"), delta_v)
            _term(2.0, row.get("Ih_Corriente_Bobinas"), delta_i)
            _term(2.0, row.get("Distancia_L_Nula"), delta_r)
    else:
        col_v = next((c for c in row.index if "Voltaje" in str(c) and "Placas_Enfoque" not in str(c)), None)
        if col_v:
            _term(1.0, row.get(col_v), delta_v)
        _term(2.0, row.get("Ih_Corriente_Bobinas"), delta_i)

    if not terminos:
        return np.nan
    return float(em) * float(np.sqrt(np.sum(terminos)))


def fila_en_rango(row, campos):
    motivos = []
    for campo in campos:
        nombre = campo["nombre"]
        if nombre not in row.index:
            continue
        valor = pd.to_numeric(row[nombre], errors="coerce")
        if pd.isna(valor):
            motivos.append(f"{nombre} no numérico")
            continue
        rango = campo.get("rango_valido")
        if rango:
            lo, hi = rango
            if valor < lo or valor > hi:
                motivos.append(f"{nombre}={valor} fuera de [{lo}, {hi}]")
    return (len(motivos) == 0), "; ".join(motivos)


# =============================================================================
# MÓDULO 2: SISTEMA DE ALERTAS Y LIMPIEZA LÓGICA (SOFT DELETION)
# =============================================================================

def _pandas_nativo(df):
    """Quita dtypes Arrow de Streamlit/Sheets, que rompen al mezclar NaN con texto."""
    if df is None or (hasattr(df, "empty") and df.empty):
        return pd.DataFrame()
    datos = {}
    for col in df.columns:
        datos[str(col)] = list(df[col].tolist())
    return pd.DataFrame(datos)


def leer_hoja(conn, worksheet):
    try:
        df = conn.read(worksheet=worksheet, ttl=0)
        return _pandas_nativo(df)
    except Exception:
        return pd.DataFrame()


def limpiar_base_datos(df, df_anulaciones=None):
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    df = df.copy()
    if "ID_Medicion" in df.columns:
        df["ID_Medicion"] = df["ID_Medicion"].astype(str)

    if df_anulaciones is not None and not df_anulaciones.empty and "ID_Medicion" in df.columns:
        col_id = "ID_Medicion_Anular" if "ID_Medicion_Anular" in df_anulaciones.columns else None
        if col_id:
            ids_anular = set(df_anulaciones[col_id].dropna().astype(str))
            df = df[~df["ID_Medicion"].isin(ids_anular)]

    invalida = pd.Series(False, index=df.index)
    for col_voltaje in ["Va_Voltaje_Acelerador", "Va_Voltaje_Anodo"]:
        if col_voltaje in df.columns:
            invalida = invalida | (pd.to_numeric(df[col_voltaje], errors="coerce") <= 0)

    if "Ih_Corriente_Bobinas" in df.columns:
        invalida = invalida | (pd.to_numeric(df["Ih_Corriente_Bobinas"], errors="coerce") <= 0)

    return df[~invalida].copy()


def _texto_limpio(serie):
    def _uno(valor):
        if valor is None or (isinstance(valor, float) and np.isnan(valor)):
            return ""
        texto = str(valor).strip()
        if texto.lower() in {"", "nan", "none", "<na>"}:
            return ""
        return texto
    return serie.map(_uno)


def asegurar_id_lote(df):
    df = df.copy()
    n = len(df)

    def col_txt(nombre):
        if nombre not in df.columns:
            return pd.Series([""] * n, index=df.index)
        return _texto_limpio(df[nombre])

    if "ID_Lote" in df.columns:
        existentes = col_txt("ID_Lote")
    else:
        existentes = pd.Series([""] * n, index=df.index)

    legado = (
        "LEG-"
        + col_txt("Fecha_Ingreso")
        + "|"
        + col_txt("Correo")
        + "|"
        + col_txt("Equipo")
        + "|"
        + col_txt("Experimento")
    )
    df["ID_Lote"] = [ex if ex else lg for ex, lg in zip(existentes.tolist(), legado.tolist())]
    return df


def agregar_por_lote(df):
    if df is None or df.empty:
        return pd.DataFrame()
    df = asegurar_id_lote(df)
    if "Error_Porcentual" in df.columns:
        df["Error_Porcentual"] = pd.to_numeric(df["Error_Porcentual"], errors="coerce")
    else:
        df["Error_Porcentual"] = np.nan
    if "e_m_Calculado" in df.columns:
        df["e_m_Calculado"] = pd.to_numeric(df["e_m_Calculado"], errors="coerce")
    else:
        df["e_m_Calculado"] = np.nan

    usados = ["Fecha_Ingreso", "Equipo", "Error_Porcentual", "e_m_Calculado"]
    opcionales = ["Experimento", "Correo", "e_m_Lote"]
    agg = {}
    for col in usados + opcionales:
        if col not in df.columns:
            continue
        agg[col] = "mean" if col == "e_m_Calculado" else "first"

    agrupado = df.groupby(df["ID_Lote"].astype(str), dropna=False).agg(agg).reset_index()
    if "index" in agrupado.columns and "ID_Lote" not in agrupado.columns:
        agrupado = agrupado.rename(columns={"index": "ID_Lote"})
    conteo = df.groupby(df["ID_Lote"].astype(str), dropna=False).size().reset_index(name="n_mediciones")
    conteo = conteo.rename(columns={conteo.columns[0]: "ID_Lote"})
    agrupado = agrupado.merge(conteo, on="ID_Lote", how="left")
    if "e_m_Lote" in agrupado.columns:
        lote_num = pd.to_numeric(agrupado["e_m_Lote"], errors="coerce")
        agrupado["e_m_Calculado"] = lote_num.fillna(pd.to_numeric(agrupado["e_m_Calculado"], errors="coerce"))
    return agrupado


# =============================================================================
# MÓDULO 3: ANÁLISIS DE REGRESIÓN Y EXTRACCIÓN DE e/m
# =============================================================================

def analisis_regresion_equipo(df_limpio, equipo_nombre, experimento=None):
    if df_limpio is None or df_limpio.empty:
        return None, None, None

    if experimento:
        datos = df_limpio[(df_limpio["Equipo"] == equipo_nombre) & (df_limpio["Experimento"] == experimento)].copy()
    else:
        datos = df_limpio[df_limpio["Equipo"] == equipo_nombre].copy()

    if len(datos) < 3:
        return None, None, None

    x_vals = []
    y_vals = []

    if equipo_nombre == "PASCO SE-9629":
        R = equipos_parametros[equipo_nombre]["R"]
        N = equipos_parametros[equipo_nombre]["N"]
        for _, row in datos.iterrows():
            U = pd.to_numeric(row.get("Va_Voltaje_Acelerador"), errors="coerce")
            I_H = pd.to_numeric(row.get("Ih_Corriente_Bobinas"), errors="coerce")
            r_mm = pd.to_numeric(row.get("r_Radio_Haz_mm"), errors="coerce")
            if pd.isna(U) or pd.isna(I_H) or pd.isna(r_mm):
                continue
            r = r_mm / 1000
            B = calcular_campo_pasco(I_H, R, N)
            y_vals.append(2 * U)
            x_vals.append((B * r) ** 2)

    elif equipo_nombre == "TELTRON TEL 2534":
        for _, row in datos.iterrows():
            U = pd.to_numeric(row.get("Va_Voltaje_Acelerador"), errors="coerce")
            I_H = pd.to_numeric(row.get("Ih_Corriente_Bobinas"), errors="coerce")
            if pd.isna(U) or pd.isna(I_H):
                continue
            y_vals.append(U)
            x_vals.append(I_H ** 2)

    elif equipo_nombre == "TELTRON Tipo S 1000617":
        if experimento == "Exp 2: Deflexion Magnetica Pura":
            k_B = equipos_parametros[equipo_nombre]["k_B"]
            for _, row in datos.iterrows():
                U = pd.to_numeric(row.get("Va_Voltaje_Anodo"), errors="coerce")
                I_H = pd.to_numeric(row.get("Ih_Corriente_Bobinas"), errors="coerce")
                c = pd.to_numeric(row.get("Coordenada_x"), errors="coerce")
                a = pd.to_numeric(row.get("Coordenada_y"), errors="coerce")
                if pd.isna(U) or pd.isna(I_H) or pd.isna(c) or pd.isna(a) or a <= 0:
                    continue
                r = calcular_r_geom_thomson(c, a)
                B = k_B * I_H
                y_vals.append(2 * U)
                x_vals.append((B * r) ** 2)

        elif experimento == "Exp 1: Balance de Campos (Fuerza Nula)":
            k_B = equipos_parametros[equipo_nombre]["k_B"]
            for _, row in datos.iterrows():
                U = pd.to_numeric(row.get("Va_Voltaje_Anodo"), errors="coerce")
                Vp = pd.to_numeric(row.get("Vp_Voltaje_Placas"), errors="coerce")
                I_H = pd.to_numeric(row.get("Ih_Corriente_Bobinas"), errors="coerce")
                d_mm = pd.to_numeric(row.get("Distancia_L_Nula"), errors="coerce")
                if pd.isna(U) or pd.isna(Vp) or pd.isna(I_H) or pd.isna(d_mm) or d_mm == 0:
                    continue
                d = d_mm / 1000
                B = k_B * I_H
                E = Vp / d
                y_vals.append(2 * U)
                x_vals.append((E / B) ** 2)

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
                ae = pd.to_numeric(row.get("Distancia_AE_mm"), errors="coerce")
                d_aa = pd.to_numeric(row.get("Diametro_AA_mm"), errors="coerce")
                if pd.isna(ae) or pd.isna(d_aa) or d_aa == 0:
                    continue
                radios.append(calcular_R_tel2534_punto_axial(ae, d_aa))
            elif experimento == "Punto E - Cañon Axial (anillo cercano EE')":
                d_ee = pd.to_numeric(row.get("Diametro_EE_mm"), errors="coerce")
                if pd.isna(d_ee) or d_ee == 0:
                    continue
                radios.append(calcular_R_tel2534_punto_E(d_ee))
            elif experimento == "Perpendicular - anillo AA'":
                ae = pd.to_numeric(row.get("Distancia_AE_mm"), errors="coerce")
                if pd.isna(ae):
                    continue
                radios.append(calcular_R_tel2534_perpendicular(ae))

        if not radios:
            return None, None, None

        R_medio = np.mean(radios)
        k_B = equipos_parametros[equipo_nombre]["k_B"]
        factor = 2 / (k_B ** 2)
        em_experimental = pendiente * (factor / (R_medio ** 2))
        incerteza_final = incerteza_ajuste * (factor / (R_medio ** 2))
    elif equipo_nombre == "TELTRON Tipo S 1000617" and experimento == "Exp 1: Balance de Campos (Fuerza Nula)":
        if pendiente == 0:
            return None, None, None
        em_experimental = 1.0 / pendiente
        incerteza_final = incerteza_ajuste / (pendiente ** 2)
    else:
        em_experimental = pendiente
        incerteza_final = incerteza_ajuste

    fig = generar_grafico_regresion(x_array, y_array, res, equipo_nombre, em_experimental, incerteza_final)
    return em_experimental, incerteza_final, fig


def generar_grafico_regresion(x, y, res, titulo, em_val, error):
    df_pts = pd.DataFrame({
        "x": list(x),
        "y": list(y),
    })
    x_line = np.linspace(np.min(x), np.max(x), 80) if len(x) else np.array([])
    df_line = pd.DataFrame({
        "x": list(x_line),
        "y": list(res.intercept + res.slope * x_line),
    })
    spec = {
        "title": f"Estimación e/m: {titulo} | e/m exp: {em_val:.3e} ± {error:.3e} {EM_TEORICO_UNIDAD}",
        "height": 360,
        "layer": [
            {
                "data": {"values": df_pts.to_dict("records")},
                "mark": {"type": "point", "filled": True, "size": 80, "color": "#1f4e79"},
                "encoding": {
                    "x": {"field": "x", "type": "quantitative", "title": "Variable Independiente (Teórica)"},
                    "y": {"field": "y", "type": "quantitative", "title": "Variable Dependiente (Teórica)"},
                    "tooltip": [
                        {"field": "x", "type": "quantitative", "title": "x", "format": ".4g"},
                        {"field": "y", "type": "quantitative", "title": "y", "format": ".4g"},
                    ],
                },
            },
            {
                "data": {"values": df_line.to_dict("records")},
                "mark": {"type": "line", "color": "red", "strokeDash": [6, 4]},
                "encoding": {
                    "x": {"field": "x", "type": "quantitative"},
                    "y": {"field": "y", "type": "quantitative"},
                },
            },
        ],
    }
    return {"spec": spec, "r2": res.rvalue ** 2}


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
    "TELTRON TEL 2534": "teltron_2534.png",
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
            correo = st.text_input("Correo Institucional", value=st.session_state["correo"], disabled=True)
            integrantes = st.text_input("Integrantes del grupo")
        with col_gen2:
            delta_v = st.number_input("Incertidumbre Voltaje (ΔV) [V]", value=1.0, format="%.2f", step=0.1, min_value=0.0)
            delta_i = st.number_input("Incertidumbre Corriente (ΔI) [A]", value=0.01, format="%.3f", step=0.01, min_value=0.0)
            delta_r = st.number_input("Incertidumbre Radio/Dist. (Δr) [mm]", value=1.0, format="%.2f", step=0.1, min_value=0.0)

        st.markdown("---")
        st.subheader("Tabla de Datos Experimentales")

        campos = protocolo_adquisicion[equipo_seleccionado]["experimentos"][experimento_seleccionado]["campos_requeridos"]
        columnas_dinamicas = {campo["nombre"]: [float(campo.get("valor_defecto", 0.0))] * 5 for campo in campos}
        df_vacio = pd.DataFrame(columnas_dinamicas)
        df_vacio.index = range(1, len(df_vacio) + 1)

        df_editado = st.data_editor(
            df_vacio,
            num_rows="dynamic",
            use_container_width=True,
            column_config=column_config_con_unidades(campos),
        )

        if st.button("Procesar Lote y Guardar", type="primary"):
            col_voltaje = [c for c in df_editado.columns if "Voltaje" in c][0]

            df_validos = df_editado[pd.to_numeric(df_editado[col_voltaje], errors="coerce") > 0].copy()

            if df_validos.empty:
                st.warning("Debe ingresar al menos una medición válida para procesar.")
            else:
                mask_ok = []
                rechazos = []
                for idx, row in df_validos.iterrows():
                    ok, motivo = fila_en_rango(row, campos)
                    mask_ok.append(ok)
                    if not ok:
                        rechazos.append(f"Fila {idx}: {motivo}")
                df_fuera = df_validos[[not x for x in mask_ok]]
                df_validos = df_validos[mask_ok]
                if rechazos:
                    st.warning("Se descartaron filas fuera de rango:\n- " + "\n- ".join(rechazos))

                if df_validos.empty:
                    st.warning("Ninguna fila quedó dentro de los rangos físicos del equipo.")
                else:
                    df_validos["e_m_Calculado"] = df_validos.apply(
                        lambda row: calcular_em_fila(row, equipo_seleccionado, experimento_seleccionado), axis=1
                    )
                    df_validos = df_validos.dropna(subset=["e_m_Calculado"])
                    df_validos = df_validos[df_validos["e_m_Calculado"] > 0]

                    if df_validos.empty:
                        st.warning("Las mediciones ingresadas no son suficientes o viables para calcular e/m.")
                    else:
                        df_validos["Error_Instrumental"] = df_validos.apply(
                            lambda row: calcular_error_instrumental(
                                row, equipo_seleccionado, experimento_seleccionado, delta_v, delta_i, delta_r
                            ),
                            axis=1,
                        )

                        em_lote = df_validos["e_m_Calculado"].mean()
                        em_std = df_validos["e_m_Calculado"].std() if len(df_validos) > 1 else 0.0
                        err_lote = np.abs((em_lote - EM_TEORICO) / EM_TEORICO) * 100
                        metodo = "Promedio Estadístico"
                        id_lote = f"LOT-{uuid.uuid4().hex[:12]}"

                        st.success(f"Se procesaron {len(df_validos)} mediciones exitosamente mediante {metodo}.")
                        col_res1, col_res2, col_res3 = st.columns(3)
                        col_res1.metric(
                            label=f"e/m Lote (Promedio) [{EM_TEORICO_UNIDAD}]",
                            value=f"{em_lote:.4e} {EM_TEORICO_UNIDAD}",
                        )
                        col_res2.metric(
                            label=f"Desviación Std (σ) [{EM_TEORICO_UNIDAD}]",
                            value=f"± {em_std:.4e} {EM_TEORICO_UNIDAD}",
                        )
                        if err_lote <= UMBRAL_ERROR_PCT:
                            col_res3.metric(label="Error % Lote [%]", value=f"{err_lote:.2f} %", delta="Aceptable", delta_color="normal")
                        else:
                            col_res3.metric(label="Error % Lote [%]", value=f"{err_lote:.2f} %", delta="Desviación Alta", delta_color="inverse")

                        st.markdown("**Mediciones del lote**")
                        st.dataframe(df_con_unidades(df_validos), use_container_width=True)

                        df_existente = leer_hoja(conn, HOJA_DATOS)

                        filas_para_guardar = []
                        for _, row in df_validos.iterrows():
                            nueva_fila_dict = {
                                "ID_Medicion": f"MED-{uuid.uuid4().hex[:12]}",
                                "ID_Lote": id_lote,
                                "Fecha_Ingreso": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "Correo": correo,
                                "Integrantes": integrantes,
                                "Equipo": equipo_seleccionado,
                                "Experimento": experimento_seleccionado,
                                "e_m_Calculado": row["e_m_Calculado"],
                                "e_m_Lote": em_lote,
                                "Error_Porcentual": err_lote,
                                "Error_Instrumental": row["Error_Instrumental"],
                                "delta_v": delta_v,
                                "delta_i": delta_i,
                                "delta_r": delta_r,
                                "Observaciones": f"Lote ({metodo}). e/m: {em_lote:.2e} ± {em_std:.2e} {EM_TEORICO_UNIDAD}",
                            }
                            for campo in df_editado.columns:
                                nueva_fila_dict[campo] = row[campo]
                            filas_para_guardar.append(nueva_fila_dict)

                        df_nuevas_filas = pd.DataFrame(filas_para_guardar)
                        if not df_existente.empty:
                            df_actualizado = pd.concat([df_existente, df_nuevas_filas], ignore_index=True)
                        else:
                            df_actualizado = df_nuevas_filas

                        conn.update(worksheet=HOJA_DATOS, data=df_actualizado)
                        st.cache_data.clear()
                        st.caption(f"Lote guardado con ID_Lote = {id_lote}")

# --- PESTAÑA 2: DASHBOARD DE ANÁLISIS ---
with tab2:
    st.header("Análisis Histórico General")

    col_a, col_b = st.columns([1, 3])
    with col_a:
        refrescar = st.button("Actualizar y Analizar Datos", type="primary")
    with col_b:
        st.caption("La vista usa la hoja Datos_Lab y omite mediciones anuladas o físicamente inviables.")

    if refrescar or st.session_state.get("dashboard_cargado"):
        st.session_state["dashboard_cargado"] = True
        try:
            df_raw = leer_hoja(conn, HOJA_DATOS)
            df_anul = leer_hoja(conn, HOJA_ANULACIONES)

            if df_raw.empty or "Equipo" not in df_raw.columns:
                st.info("Aún no hay datos históricos válidos en 'Datos_Lab'. Ingresa al menos una medición primero.")
            else:
                df_raw = df_raw.dropna(subset=["Equipo"])
                n_bruto = len(df_raw)
                df_limpio = limpiar_base_datos(df_raw, df_anul)
                n_limpio = 0 if df_limpio is None or df_limpio.empty else len(df_limpio)
                st.caption(f"Registros leídos: {n_bruto}. Tras limpieza y anulaciones: {n_limpio}.")

                if df_limpio is None or df_limpio.empty:
                    st.warning("No quedan mediciones válidas después de filtrar.")
                else:
                    df_limpio = asegurar_id_lote(df_limpio)

                    st.subheader("Base de Datos Experimental")
                    st.markdown("Registro histórico de mediciones vigentes.")
                    st.dataframe(df_con_unidades(df_limpio), use_container_width=True)

                    st.markdown("---")
                    st.subheader("Evolución Temporal: Error Porcentual por lote")
                    st.caption(f"La línea roja discontinua marca el umbral de {UMBRAL_ERROR_PCT:.0f} %.")

                    if "Error_Porcentual" not in df_limpio.columns:
                        st.info("No hay datos con error porcentual calculado para graficar la deriva.")
                    else:
                        df_lotes = agregar_por_lote(df_limpio)
                        if df_lotes.empty:
                            st.info("No se pudieron agrupar lotes.")
                        else:
                            mostrar_grafico_error_interactivo(
                                df_lotes,
                                "Error porcentual vs tiempo (un punto por lote)",
                                legend=True,
                            )

                            st.markdown("---")
                            st.subheader("Error porcentual en el tiempo por equipo")
                            equipos_unicos = list(df_lotes["Equipo"].dropna().astype(str).unique())
                            for eq in equipos_unicos:
                                df_eq = df_lotes[df_lotes["Equipo"].astype(str) == eq].sort_values("Fecha_Ingreso")
                                if df_eq.empty:
                                    continue
                                mostrar_grafico_error_interactivo(
                                    df_eq,
                                    f"{eq}: Error porcentual vs tiempo",
                                    legend=False,
                                )

                    st.markdown("---")
                    st.subheader("Ajuste lineal histórico")
                    st.caption("Requiere al menos 3 mediciones válidas del mismo equipo (y del mismo experimento, cuando aplica).")

                    equipos_reg = list(df_limpio["Equipo"].dropna().astype(str).unique())
                    hubo_ajuste = False
                    for eq in equipos_reg:
                        if eq == "PASCO SE-9629":
                            pares = [(eq, None)]
                        else:
                            if "Experimento" not in df_limpio.columns:
                                pares = [(eq, None)]
                            else:
                                exps = list(df_limpio.loc[df_limpio["Equipo"].astype(str) == eq, "Experimento"].dropna().unique())
                                pares = [(eq, exp) for exp in exps] if exps else [(eq, None)]

                        for equipo_nombre, experimento in pares:
                            em_exp, inc_exp, fig = analisis_regresion_equipo(df_limpio, equipo_nombre, experimento)
                            etiqueta = equipo_nombre if not experimento else f"{equipo_nombre} — {experimento}"
                            if em_exp is None:
                                st.info(f"{etiqueta}: datos insuficientes para el ajuste (mínimo 3 puntos útiles).")
                                continue
                            hubo_ajuste = True
                            err_pct = abs((em_exp - EM_TEORICO) / EM_TEORICO) * 100
                            c1, c2, c3 = st.columns(3)
                            c1.metric(f"e/m ajuste [{EM_TEORICO_UNIDAD}]", f"{em_exp:.4e}")
                            c2.metric(f"σ pendiente [{EM_TEORICO_UNIDAD}]", f"± {inc_exp:.4e}")
                            c3.metric("Error % vs teórico", f"{err_pct:.2f} %")
                            if fig and "spec" in fig:
                                st.vega_lite_chart(fig["spec"], use_container_width=True)
                                if "r2" in fig:
                                    st.caption(f"{etiqueta}  ·  R² = {fig['r2']:.3f}")

                    if not hubo_ajuste:
                        st.info("Todavía no hay suficientes puntos para extraer e/m por regresión.")

                    st.markdown("---")
                    st.subheader("Anular una medición")
                    st.caption("La fila no se borra de Sheets: queda listada en la hoja Anulaciones y desaparece del análisis.")

                    ids_disponibles = df_limpio["ID_Medicion"].dropna().astype(str).tolist() if "ID_Medicion" in df_limpio.columns else []
                    if not ids_disponibles:
                        st.info("No hay IDs de medición para anular.")
                    else:
                        id_anular = st.selectbox("ID_Medicion a anular", ids_disponibles)
                        motivo = st.text_input("Motivo de la anulación", placeholder="Error de digitación, ensayo de interfaz, etc.")
                        if st.button("Anular medición"):
                            if not id_anular:
                                st.warning("Selecciona un ID.")
                            else:
                                nueva = pd.DataFrame([{
                                    "ID_Medicion_Anular": id_anular,
                                    "Fecha_Anulacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "Correo": st.session_state.get("correo"),
                                    "Motivo": motivo,
                                }])
                                if df_anul is None or df_anul.empty:
                                    df_anul_nuevo = nueva
                                else:
                                    df_anul_nuevo = pd.concat([df_anul, nueva], ignore_index=True)
                                conn.update(worksheet=HOJA_ANULACIONES, data=df_anul_nuevo)
                                st.cache_data.clear()
                                st.success(f"Medición {id_anular} anulada. Vuelve a pulsar Actualizar para refrescar el análisis.")

        except Exception as e:
            st.error(f"No se pudo acceder a los datos. Detalle técnico: {e}")
    else:
        st.info("Pulsa «Actualizar y Analizar Datos» para cargar el historial.")
