import streamlit as st
import pandas as pd
import numpy as np
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# Configuración básica de la página
st.set_page_config(page_title="Proyecto Lab VI - Usach", layout="wide")
st.title("Laboratorio: Estimación e/m")

# Establecer conexión segura con Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# INTERFAZ WEB: PESTAÑAS (TABS)
# ==========================================
tab1, tab2 = st.tabs(["Módulo de Adquisición", "Dashboard de Análisis"])

# --- PESTAÑA 1: MÓDULO DE ADQUISICIÓN ---
with tab1:
    st.header("Ingreso de Mediciones")
    
    with st.form("formulario_ingreso"):
        col1, col2 = st.columns(2)
        
        with col1:
            correo = st.text_input("Correo Institucional (@usach.cl)")
            integrantes = st.text_input("Integrantes del grupo")
            equipo = st.selectbox("Seleccione Equipo", ["1 - PASCO SE-9629", "2 - TELTRON Doble Cañón", "3 - TELTRON Thomson"])
        
        with col2:
            va = st.number_input("Voltaje Acelerador (Va) [V]", min_value=0.0, format="%.2f")
            ib = st.number_input("Corriente Bobinas (Ib) [A]", min_value=0.0, format="%.2f")
            radio = st.number_input("Radio del Haz (R) [m]", min_value=0.0, format="%.4f")
        
        submit = st.form_submit_button("Guardar Medición")
        
        if submit:
            if "@usach.cl" not in correo:
                st.error("Alerta: Debe usar correo institucional.")
            elif va == 0 or ib == 0 or radio == 0:
                st.warning("Alerta: Revise los datos, hay valores en cero (físicamente inviables).")
            else:
                # 1. Leer los datos actuales de la hoja en la nube
                df_existente = conn.read()
                
                # 2. Crear la nueva fila de datos
                nueva_fila = pd.DataFrame([{
                    "Fecha_Ingreso": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Correo": correo,
                    "Integrantes": integrantes,
                    "Equipo": equipo.split(" - ")[1],
                    "Voltaje_Acelerador": va,
                    "Corriente_Bobinas": ib,
                    "Radio_Haz": radio,
                    "Observaciones": "Dato válido"
                }])
                
                # 3. Unir los datos antiguos con el nuevo
                df_actualizado = pd.concat([df_existente, nueva_fila], ignore_index=True)
                
                # 4. Sobrescribir la hoja de cálculo con los datos actualizados
                conn.update(worksheet="Sheet1", data=df_actualizado)
                
                st.success("¡Datos guardados correctamente en Google Sheets!")

# --- PESTAÑA 2: DASHBOARD DE ANÁLISIS ---
with tab2:
    st.header("Análisis Histórico y Deriva Temporal")
    
    if st.button("Actualizar Datos desde la Nube"):
        # Leer los datos directamente de Google Sheets
        df = conn.read()
        
        # Limpiar filas vacías que a veces trae Google Sheets por defecto
        df = df.dropna(subset=['Voltaje_Acelerador'])
        
        if not df.empty:
            # Procesamiento matemático
            mu_0 = 4 * np.pi * 1e-7
            N_espiras = 130
            R_bobina = 0.15
            
            # Convertir a formato numérico (Google Sheets a veces envía números como texto)
            df['Corriente_Bobinas'] = pd.to_numeric(df['Corriente_Bobinas'])
            df['Voltaje_Acelerador'] = pd.to_numeric(df['Voltaje_Acelerador'])
            df['Radio_Haz'] = pd.to_numeric(df['Radio_Haz'])
            
            # Cálculo de Campo B y relación e/m
            df['Campo_B'] = (8 * mu_0 * N_espiras * df['Corriente_Bobinas']) / (np.sqrt(125) * R_bobina)
            df['e_m_calculado'] = (2 * df['Voltaje_Acelerador']) / ((df['Campo_B']**2) * (df['Radio_Haz']**2))
            
            valor_teorico = 1.758820e11
            df['Error_Porcentual'] = np.abs((df['e_m_calculado'] - valor_teorico) / valor_teorico) * 100
            
            st.subheader("Datos Procesados")
            st.dataframe(df[['Fecha_Ingreso', 'Equipo', 'e_m_calculado', 'Error_Porcentual']])
            
            st.subheader("Gráfico de Deriva: Evolución del Error %")
            st.line_chart(data=df, x='Fecha_Ingreso', y='Error_Porcentual')
        else:
            st.info("Aún no hay datos históricos para analizar.")