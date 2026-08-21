import streamlit as st
import pandas as pd
import numpy as np
import requests
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
from streamlit_oauth import OAuth2Component


# CONFIGURACIÓN BÁSICA
st.set_page_config(page_title="Proyecto Lab VI - Usach", layout="wide")
st.title("Laboratorio: Estimación e/m")

conn = st.connection("gsheets", type=GSheetsConnection)


# --- FUNCIÓN MAESTRA DE CÁLCULO (Declarada de forma global para evitar errores) ---
def calcular_em(row, eq, exp):
    try:
        # Extrae el voltaje disponible dinámicamente según el experimento
        V_medido = float(row.get('Va_Voltaje_Acelerador') or row.get('Vp_Voltaje_Potenciador') or row.get('Va_Voltaje_Anodo') or 0)
        Ih = float(row.get('Ib_Corriente_Bobinas', 0) or 0)
        # Extrae el parámetro geométrico (radio o distancia) si existe
        R = float(row.get('Parametro_Geometrico') or row.get('R_Radio_Curvatura') or row.get('R_Radio_Circunferencia') or 0)
        
        if V_medido <= 0:
            return 0.0

        if "PASCO" in eq:
            B = Ih * 0.000739
            if B == 0 or R == 0: return 0.0
            return (2 * V_medido) / ((B**2) * (R**2))
            
        elif "Doble Cañón" in eq:
            if (Ih * R) == 0: return 0.0
            return (V_medido / ((Ih * R)**2)) * 1.15e5
            
        elif "1000617" in eq:
            if exp == "Balance de Campos":
                if Ih == 0: return 0.0
                return (V_medido / (Ih**2)) * 2.6e7
            elif exp == "Deflexión de Campos":
                if (Ih * R) == 0: return 0.0
                return (V_medido / ((Ih**2) * (R**2))) * 1.15e5
            elif exp == "Fuente para mínimo balance de campos":
                if (Ih**2 * R) == 0: return 0.0
                return (V_medido / ((Ih**2) * R)) * 7.19e6
            
    except Exception:
        return 0.0
    return 0.0




tab1, tab2 = st.tabs(["Módulo de Adquisición", "Dashboard de Análisis"])

# --- PESTAÑA 1: MÓDULO DE ADQUISICIÓN ---
with tab1:
    st.header("Ingreso de Mediciones")
    
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        integrantes = st.text_input("Nombres y apellidos de los integrantes")
    with col_info2:
        equipo = st.selectbox("Seleccione Equipo Utilizado", [
            "1 - PASCO SE-9629", 
            "2 - TELTRON Doble Cañón TEL 2534", 
            "3 - Thomson Tube S 1000617"
        ])
        
        experimento = "Único"
        if "1000617" in equipo:
            experimento = st.selectbox("Seleccione el Experimento Específico", [
                "Balance de Campos",
                "Deflexión de Campos",
                "Fuente para mínimo balance de campos"
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
    delta_r = col_err3.number_input("Incertidumbre Radio/Distancia (Δr) [m]", value=0.001, format="%.4f", step=0.001)
    
    st.markdown("**2. Tabla de Datos Experimentales:**")
    
    # --- LÓGICA DINÁMICA DE COLUMNAS SEGÚN EXPERIMENTO Y EQUIPO ---
    col_param = None
    if "1000617" in equipo:
        if experimento == "Balance de Campos":
            col_voltaje = "Vp_Voltaje_Potenciador"
            df_vacio = pd.DataFrame({
                col_voltaje: [0.0] * 5,
                "Ib_Corriente_Bobinas": [0.0] * 5
            })
        elif experimento == "Deflexión de Campos":
            col_voltaje = "Va_Voltaje_Anodo"
            col_param = "R_Radio_Curvatura"
            df_vacio = pd.DataFrame({
                col_voltaje: [0.0] * 5,
                "Ib_Corriente_Bobinas": [0.0] * 5,
                col_param: [0.0] * 5
            })
        else: # Fuente para mínimo balance de campos
            col_voltaje = "Vp_Voltaje_Potenciador"
            col_param = "R_Radio_Curvatura"
            df_vacio = pd.DataFrame({
                col_voltaje: [0.0] * 5,
                "Ib_Corriente_Bobinas": [0.0] * 5,
                col_param: [0.0] * 5
            })
    elif "PASCO" in equipo:
        col_voltaje = "Va_Voltaje_Acelerador"
        col_param = "R_Radio_Circunferencia"
        df_vacio = pd.DataFrame({
            col_voltaje: [0.0] * 5,
            "Ib_Corriente_Bobinas": [0.0] * 5,
            col_param: [0.0] * 5
        })
    else: # Doble Cañón y cualquier otro futuro
        col_voltaje = "Va_Voltaje_Acelerador"
        col_param = "Parametro_Geometrico"
        df_vacio = pd.DataFrame({
            col_voltaje: [0.0] * 5,
            "Ib_Corriente_Bobinas": [0.0] * 5,
            col_param: [0.0] * 5
        })
        
    df_vacio.index = range(1, len(df_vacio) + 1)
    df_vacio.index.name = "Dato N°"
    
    df_editado = st.data_editor(df_vacio, num_rows="dynamic", use_container_width=True)
    
    if st.button("Procesar Lote y Guardar", type="primary"):
        df_validos = df_editado[df_editado[col_voltaje] > 0].copy()
        
        if df_validos.empty:
            st.warning(f"Debe ingresar al menos una medición válida (con {col_voltaje} > 0) para procesar.")
        else:
            valor_teorico = 1.758820e11 # C/kg
            
            # Aplicar la función global limpia y sin errores de alcance
            df_validos['e_m_Calculado'] = df_validos.apply(
                lambda row: calcular_em(row, equipo, experimento), axis=1
            )
            
            # --- PROPAGACIÓN DE ERROR DINÁMICA ---
            termino_v = (delta_v / df_validos[col_voltaje])**2
            termino_i = (2 * delta_i / df_validos['Ib_Corriente_Bobinas'])**2
            
            if col_param and col_param in df_validos.columns:
                termino_r = (2 * delta_r / df_validos[col_param])**2
                df_validos['Error_Instrumental'] = df_validos['e_m_Calculado'] * np.sqrt(termino_v + termino_i + termino_r)
            else:
                df_validos['Error_Instrumental'] = df_validos['e_m_Calculado'] * np.sqrt(termino_v + termino_i)
            
            # 4. Cálculos Estadísticos del Lote
            em_promedio = df_validos['e_m_Calculado'].mean()
            em_std = df_validos['e_m_Calculado'].std() if len(df_validos) > 1 else 0
            error_porcentual_promedio = abs((em_promedio - valor_teorico) / valor_teorico) * 100
            
            # INTERFAZ DE RESULTADOS ESTADÍSTICOS
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
            columnas_mostrar = [col for col in [col_voltaje, 'Ib_Corriente_Bobinas', col_param, 'e_m_Calculado', 'Error_Instrumental'] if col and col in df_validos.columns]
            st.dataframe(df_validos[columnas_mostrar], use_container_width=True)
            
            # GUARDADO EN GOOGLE SHEETS
            df_existente = conn.read()
            
            filas_para_guardar = []
            for index, row in df_validos.iterrows():
                # Emparejamiento seguro para guardar en la base de datos general
                guardar_voltaje_acelerador = row.get('Va_Voltaje_Acelerador') or row.get('Va_Voltaje_Anodo', np.nan)
                guardar_parametro = row.get('Parametro_Geometrico') or row.get('R_Radio_Curvatura') or row.get('R_Radio_Circunferencia', np.nan)
                
                filas_para_guardar.append({
                    "Fecha_Ingreso": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Correo": st.session_state.correo,
                    "Integrantes": integrantes,
                    "Equipo": equipo.split(" - ")[1],
                    "Vf_Voltaje_Filamento": np.nan,
                    "Va_Voltaje_Acelerador": guardar_voltaje_acelerador,
                    "Vp_Voltaje_Placas": row.get('Vp_Voltaje_Potenciador', np.nan),
                    "Vb_Voltaje_Bobinas": np.nan,
                    "Ib_Corriente_Bobinas": row['Ib_Corriente_Bobinas'],
                    "Parametro_Geometrico": guardar_parametro,
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
        df = conn.read()
        
        # Filtro robusto para verificar si existen columnas de voltaje guardadas
        cols_voltaje = [c for c in ['Va_Voltaje_Acelerador', 'Voltaje_Acelerador', 'Vp_Voltaje_Placas', 'Va_Voltaje_Anodo'] if c in df.columns]
        if cols_voltaje:
            df = df.dropna(subset=cols_voltaje, how='all')
            
        if not df.empty and len(df) > 0:
            st.success(f"Conexión exitosa: Se cargaron {len(df)} mediciones históricas.")
            
            st.subheader("Base de Datos Experimental")
            st.dataframe(df, use_container_width=True)
            
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
