import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import linregress

# =============================================================================
# MÓDULO 1: CONSTANTES, PARAMETRIZACIÓN Y FUNCIONES MATEMÁTICAS
# =============================================================================

# Constantes físicas universales
MU_0 = 4 * np.pi * 10**-7  # Permeabilidad magnética (T*m/A)
EM_TEORICO = 1.758820e11   # Valor aceptado C/kg

# Diccionario de parámetros instrumentales extraídos de manuales de fabricante
equipos_parametros = {
    "PASCO SE-9629": {
        "R": 0.158, # m
        "N": 130    # espiras
    },
    "TELTRON TEL 2534": {
        "D": 0.138, # m
        "k_B": 4.17e-3 # T/A
    },
    "TELTRON Tipo S 1000617": {
        "R": 0.068, # m
        "N": 320,   # espiras
        "k_B": 4.2e-3  # T/A
    }
}

def calcular_campo_pasco(I, R, N):
    """Calcula la magnitud del campo B para el equipo PASCO."""
    return (4/5)**(1.5) * (MU_0 * N * I) / R

def calcular_r_geom_thomson(c_mm, a_mm):
    """Convierte las coordenadas en pantalla a radio de curvatura (Tubo Thomson)."""
    c = c_mm / 1000
    a = a_mm / 1000
    return (c**2 + a**2) / (2 * a)

def calcular_r_geom_doble_canon(x_mm, y_mm):
    """Convierte distancias de la cuadrícula a radio de curvatura (Doble Cañón)."""
    x = x_mm / 1000
    y = y_mm / 1000
    return (x**2 + y**2) / (2 * y)


# =============================================================================
# MÓDULO 2: SISTEMA DE ALERTAS Y LIMPIEZA LÓGICA (SOFT DELETION)
# =============================================================================

def limpiar_base_datos(df, df_anulaciones=None):
    """
    Identificación de datos erróneos.
    Implementa validación física y borrado lógico basado en tickets de corrección.
    """
    print("--- Iniciando Validación de Datos ---")
    
    # 1. Borrado lógico manual (Si existe un registro de anulaciones)
    if df_anulaciones is not None and not df_anulaciones.empty:
        df = df[~df['ID_Medicion'].isin(df_anulaciones['ID_Medicion_Anular'])]
        
    # 2. Alertas del sistema: Filtro de imposibilidades físicas
    # Verificamos que los parámetros esenciales sean positivos
    mask_invalida = (df['Va_Voltaje_Acelerador'] <= 0) | (df['Ih_Corriente_Bobinas'] <= 0)
    
    if mask_invalida.any():
        datos_malos = df[mask_invalida]
        for index, row in datos_malos.iterrows():
            print(f"ALERTA: Fila {index} ({row.get('Equipo', 'Desconocido')}) descartada - V o I <= 0.")
            
    # Retornar DF limpio (soft deletion)
    df_limpio = df[~mask_invalida].copy()
    return df_limpio


# =============================================================================
# MÓDULO 3: ANÁLISIS DE REGRESIÓN Y EXTRACCIÓN DE e/m
# =============================================================================

def analisis_regresion_equipo(df_limpio, equipo_nombre, experimento=None):
    """
    Estructura los datos X e Y según el modelo teórico del equipo y experimento,
    realiza regresión lineal y grafica los resultados con incertezas.
    """
    # Filtro específico por equipo y experimento
    if experimento:
        datos = df_limpio[(df_limpio['Equipo'] == equipo_nombre) & (df_limpio['Experimento'] == experimento)].copy()
    else:
        datos = df_limpio[df_limpio['Equipo'] == equipo_nombre].copy()
        
    if len(datos) < 3:
        print(f"Datos insuficientes para análisis de regresión en {equipo_nombre}.")
        return None, None
        
    x_vals = []
    y_vals = []
    
    # --- Ramificación por Equipo ---
    
    if equipo_nombre == "PASCO SE-9629":
        # Y = 2U, X = (B*r)^2 -> Pendiente = e/m
        R = equipos_parametros[equipo_nombre]["R"]
        N = equipos_parametros[equipo_nombre]["N"]
        
        for _, row in datos.iterrows():
            U = row['Va_Voltaje_Acelerador']
            I_H = row['Ih_Corriente_Bobinas']
            r = row['r_Radio_Haz_mm'] / 1000 
            B = calcular_campo_pasco(I_H, R, N)
            
            y_vals.append(2 * U)
            x_vals.append((B * r)**2)
            
    elif equipo_nombre == "TELTRON TEL 2534":
        # Y = Va, X = I_H^2 -> Pendiente = Va / I_H^2
        for _, row in datos.iterrows():
            U = row['Va_Voltaje_Acelerador']
            I_H = row['Ih_Corriente_Bobinas']
            
            y_vals.append(U)
            x_vals.append(I_H**2)
            
    elif equipo_nombre == "TELTRON Tipo S 1000617":
        if experimento == "Deflexion Magnetica Pura":
            # Y = 2U_A, X = (B*r)^2 -> Pendiente = e/m
            k_B = equipos_parametros[equipo_nombre]["k_B"]
            for _, row in datos.iterrows():
                U = row['Va_Voltaje_Anodo']
                I_H = row['Ih_Corriente_Bobinas']
                c = row['Coordenada_x']
                a = row['Coordenada_y']
                
                r = calcular_r_geom_thomson(c, a)
                B = k_B * I_H
                
                y_vals.append(2 * U)
                x_vals.append((B * r)**2)
                
    # --- Ejecución de Regresión Lineal ---
    x_array = np.array(x_vals)
    y_array = np.array(y_vals)
    
    res = linregress(x_array, y_array)
    pendiente = res.slope
    incerteza_ajuste = res.stderr
    
    # Ajustes finales dependiendo del modelo de regresión
    if equipo_nombre == "TELTRON TEL 2534":
        # Asumiendo que el radio 'R_Calculado_m' ya fue procesado en el DataFrame
        if 'R_Calculado_m' in datos.columns:
            R_medio = datos['R_Calculado_m'].mean()
        else:
            R_medio = 0.05 # Valor por defecto seguro si no se proveyó la columna
            
        em_experimental = pendiente * (1.15e5 / (R_medio**2))
        incerteza_final = incerteza_ajuste * (1.15e5 / (R_medio**2))
    else:
        em_experimental = pendiente
        incerteza_final = incerteza_ajuste
        
    generar_grafico_regresion(x_array, y_array, res, equipo_nombre, em_experimental, incerteza_final)
    
    return em_experimental, incerteza_final


def generar_grafico_regresion(x, y, res, titulo, em_val, error):
    """Subrutina para generar la visualización del análisis histórico."""
    plt.figure(figsize=(9, 6))
    plt.scatter(x, y, color='darkblue', alpha=0.7, label='Datos Filtrados')
    
    # Línea de tendencia
    plt.plot(x, res.intercept + res.slope * x, 'r--', label=f'Ajuste Lineal (R²={res.rvalue**2:.3f})')
    
    plt.title(f'Estimación e/m: {titulo}')
    plt.xlabel('Variable Independiente (Teórica)')
    plt.ylabel('Variable Dependiente (Teórica)')
    
    # Cuadro de texto con resultados
    texto_res = f"e/m exp: {em_val:.3e} C/kg\nError Std: ±{error:.3e} C/kg"
    plt.text(0.05, 0.95, texto_res, transform=plt.gca().transAxes, fontsize=11,
             verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))
             
    plt.legend()
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.tight_layout()
    plt.show()
