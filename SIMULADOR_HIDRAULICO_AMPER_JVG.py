import streamlit as st
import pandas as pd
import numpy as np
import math
import plotly.graph_objects as go
import io

st.set_page_config(page_title="AMPER - Simulador Hidráulico", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# 0. LOGOTIPO CORPORATIVO (AMPER)
# ==========================================
try:
    st.sidebar.image("Gemini_Generated_Image_p5z53fp5z53fp5z5.jpg", use_container_width=True)
except:
    st.sidebar.markdown("## AMPER INGENIERÍA Y CONSTRUCCIONES")
st.sidebar.markdown("---")

# ==========================================
# 1. BASE DE DATOS FÍSICA Y MATERIALES
# ==========================================
OD_NPS_MAP = {
    0.5: 21.3, 0.75: 26.7, 1.0: 33.4, 1.5: 48.3, 2.0: 60.3, 3.0: 88.9,
    4.0: 114.3, 6.0: 168.3, 8.0: 219.1, 10.0: 273.0, 12.0: 323.8, 14.0: 355.6,
    16.0: 406.4, 18.0: 457.2, 20.0: 508.0, 24.0: 609.6, 30.0: 762.0, 36.0: 914.4, 48.0: 1219.2
}

RUGOSIDAD = {"Acero Carbono": 0.045, "HDPE PE100": 0.0015, "PVC Rígido": 0.0015}
E_MODULI = {"Acero Carbono": 2.07e11, "HDPE PE100": 1.0e9, "PVC Rígido": 3.2e9}
K_FLUIDO = 2.19e9 

LE_D_CRANE = {
    "Codos 90": 30.0, "Codos 45": 16.0, "Yees (Dir)": 20.0, "Yees (Ramal)": 50.0, 
    "Tees (Dir)": 20.0, "Valv. Mariposa": 45.0, "Valv. Compuerta": 8.0
}

def obtener_diametro_interno(material, size_val, clase):
    if pd.isna(size_val) or str(size_val).strip() == "": return 0.0
    try: val = float(size_val)
    except: return 0.0
    
    if material in ["HDPE PE100", "PVC Rígido"]:
        try: return val - 2*(val / float(clase))
        except: return val - 2*(val / 11.0)
    elif material == "Acero Carbono":
        od = OD_NPS_MAP.get(val, 0.0)
        if od == 0.0: od = val * 25.4 
        sch_ratios = {"5": 0.015, "10": 0.02, "20": 0.025, "40": 0.035, "80": 0.05}
        return od - 2*(od * sch_ratios.get(str(clase).replace("S", "").strip(), 0.035))
    return 0.0

def factor_friccion(reynolds, rugosidad_relativa):
    if reynolds < 1e-3: return 0.0
    if reynolds < 2300: return 64.0 / max(reynolds, 1)
    term = (rugosidad_relativa / 3.7) + (5.74 / (reynolds ** 0.9))
    return 0.25 / (math.log10(term) ** 2) if term > 0 else 0.02

# ==========================================
# 2. INTERFAZ DE USUARIO - SIDEBAR
# ==========================================
st.sidebar.markdown("### 💧 1. Entorno de Descarga")
rho = st.sidebar.number_input("Densidad Agua Mar (kg/m³)", value=1025.0)
mu_cp = st.sidebar.number_input("Viscosidad (cP)", value=1.200)
nu_m2s = (mu_cp * 1e-3) / rho if rho > 0 else 1e-6
profundidad_descarga = st.sidebar.number_input("Profundidad de descarga bajo el mar (m)", value=13.0)

st.sidebar.markdown("### 🪈 1.5. Difusor Final (Quena)")
activar_quena = st.sidebar.checkbox("Activar Difusor Multipuerto (Quena)", value=True)
if activar_quena:
    num_puertos = st.sidebar.number_input("Cantidad de Puertos", value=12, min_value=1, step=1)
    diam_puerto_in = st.sidebar.number_input("Diámetro de cada Puerto (Pulgadas)", value=8.0, min_value=1.0, step=0.5)
else:
    num_puertos = 0
    diam_puerto_in = 0.0

st.sidebar.markdown("### ⚙️ 2. Estrategia de Cálculo")
modo_operacion = st.sidebar.radio("Selecciona el Escenario:", 
    ["Modo A: Diseño de Línea (Lectura Manómetro)", "Modo B: Forense (Curva de Bomba)"])

coefs_bomba = [0, 0, 0]
if modo_operacion == "Modo B: Forense (Curva de Bomba)":
    st.sidebar.info("Ingresa los 3 puntos del fabricante.")
    c1, c2 = st.sidebar.columns(2)
    q0 = 0.0; h0 = c2.number_input("H Válvula Cerrada", value=75.0)
    q1 = c1.number_input("Q Nominal", value=800.0); h1 = c2.number_input("H Nominal", value=45.0)
    q2 = c1.number_input("Q Máximo", value=1100.0); h2 = c2.number_input("H Final", value=20.0)
    
    try: coefs_bomba = np.polyfit([q0, q1, q2], [h0, h1, h2], 2)
    except: coefs_bomba = [0, 0, h0]
        
    p_descarga_bar = (profundidad_descarga * rho * 9.81) / 100000 
    q_m3h = q1
    q_m3s = q_m3h / 3600.0 
    presion_manometro_mca = 0.0
else:
    st.sidebar.info("Usa el caudal real y la presión del manómetro inicial.")
    q_m3h = st.sidebar.number_input("Caudal Fijo (m³/h)", value=2500.0)
    presion_manometro_mca = st.sidebar.number_input("Presión Disponible en Manómetro (mca)", value=25.0)
    q_m3s = q_m3h / 3600.0
    p_descarga_bar = (profundidad_descarga * rho * 9.81) / 100000

st.sidebar.markdown("### 🛡️ 3. Transitorios")
tiene_hidroforo = st.sidebar.checkbox("Activar Hidróforo (Cierre Lento)")
t_cierre = st.sidebar.number_input("Tiempo Amortiguado (s)", value=20.0, min_value=0.1) if tiene_hidroforo else 0.0

# ==========================================
# 3. TABLA DE TRAMOS Y MOTOR HIDRÁULICO
# ==========================================
st.title("🌊 Simulador EPC: Emisarios y Auditoría Forense")

if "df_tramos" not in st.session_state:
    st.session_state.df_tramos = pd.DataFrame({
        "Material": ["Acero Carbono"],
        "NPS / DN": [24.0],
        "Clase/SDR": ["40"],
        "Longitud(m)": [434.0],
        "ΔZ (m)": [-13.0], 
        "Ventosa": [False],
        "Codos 90": [0],
        "Codos 45": [0],
        "Tees (Dir)": [0],
        "Yees (Dir)": [0],
        "Yees (Ramal)": [0],
        "Valv. Compuerta": [0],
        "Valv. Mariposa": [0]
    })

acc_config = {acc: st.column_config.NumberColumn(acc, min_value=0, step=1, format="%d") for acc in LE_D_CRANE.keys()}

column_config = {
    "Material": st.column_config.SelectboxColumn("Material", options=["Acero Carbono", "HDPE PE100", "PVC Rígido"], required=True),
    "Clase/SDR": st.column_config.SelectboxColumn("Clase/SDR", options=["11", "13.6", "17", "20", "21", "30", "40", "80"], required=True),
    "Ventosa": st.column_config.CheckboxColumn("Ventosa (Rompe Vacío)"),
    "ΔZ (m)": st.column_config.NumberColumn("ΔZ (m)", format="%.2f")
}
column_config.update(acc_config)

df_input = st.data_editor(st.session_state.df_tramos, column_config=column_config, num_rows="dynamic", use_container_width=True)

def calcular_hidraulica(q_s, df_config, tc_amortiguado):
    res = []
    hf_acum, hm_acum, z_acum = 0.0, 0.0, 0.0
    id_prev = None
    
    l_total = pd.to_numeric(df_config["Longitud(m)"], errors='coerce').fillna(0).sum()
    
    for idx, row in df_config.iterrows():
        try: val_size = float(row.get("NPS / DN", 0.0))
        except: continue
        
        mat = row.get("Material", "")
        if pd.isna(mat) or val_size <= 0: continue
            
        id_mm = obtener_diametro_interno(mat, val_size, row.get("Clase/SDR"))
        if id_mm <= 0: continue
        id_m = id_mm / 1000.0
        
        area = math.pi * (id_m / 2)**2
        vel = q_s / area if area > 0 else 0.0
        re = (vel * id_m) / nu_m2s
        f_real = factor_friccion(re, (RUGOSIDAD.get(mat, 0.045)/1000.0) / id_m)
        
        try: L_recta = float(row.get("Longitud(m)", 0.0))
        except: L_recta = 0.0
        
        try: dz = float(row.get("ΔZ (m)", 0.0))
        except: dz = 0.0
        
        tiene_ventosa = bool(row.get("Ventosa", False))
        
        hf = f_real * (L_recta / id_m) * (vel**2 / (2*9.81)) if L_recta > 0 else 0.0
        
        suma_k = 0.0
        for acc, le_d in LE_D_CRANE.items():
            valor_acc = row.get(acc, 0)
            if pd.notna(valor_acc) and str(valor_acc).strip() != "":
                try: suma_k += float(valor_acc) * le_d * f_real
                except: pass
                
        hm_total = suma_k * (vel**2 / (2*9.81))
        
        if id_prev is not None and abs(id_prev - id_mm) > 1.0: 
            k_trans = (1.0 - (id_prev/id_mm)**2)**2 if id_prev < id_mm else 0.5 * (1.0 - (id_mm/id_prev)**2)
            v_ref = (q_s / (math.pi * (id_prev/2000.0)**2)) if id_prev < id_mm else vel 
            hm_total += k_trans * (v_ref**2 / (2*9.81))
            
        hf_acum += hf
        hm_acum += hm_total
        z_acum += dz
        
        E_mod = E_MODULI.get(mat, 2.07e11)
        e_m = ((val_size if mat == "HDPE PE100" else OD_NPS_MAP.get(val_size, val_size*25.4))/1000.0 - id_m) / 2.0
        termino_flex = (K_FLUIDO / E_mod) * (id_m / e_m) if e_m > 0 else 0
        a_cel = math.sqrt((K_FLUIDO / rho) / (1.0 + termino_flex)) if termino_flex > 0 else 0
        
        delta_h = (a_cel * vel) / 9.81
        if tc_amortiguado > 0 and a_cel > 0 and tc_amortiguado > (2.0 * l_total / a_cel):
            delta_h = (2.0 * l_total * vel) / (9.81 * tc_amortiguado)
            
        res.append({
            "Fila": idx + 1, "Mat": mat, "ID(mm)": round(id_mm, 1),
            "Vel.(m/s)": round(vel, 2), "Pérdida (mca)": round(hf + hm_total, 2), 
            "ΔZ(m)": round(dz, 2), "Ventosa": tiene_ventosa, "Ariete(mca)": round(delta_h, 1), "L": L_recta
        })
        id_prev = id_mm
        
    return res, hf_acum, hm_acum, z_acum

res_tramos, hf_tot, hm_tot, z_tot = calcular_hidraulica(q_m3s, df_input, t_cierre)

# ==========================================
# 3.5. INTEGRACIÓN DE LA QUENA MULTIPUERTO
# ==========================================
if activar_quena and num_puertos > 0 and diam_puerto_in > 0:
    diam_puerto_m = diam_puerto_in * 0.0254
    area_puerto = math.pi * (diam_puerto_m / 2)**2
    area_total_quena = num_puertos * area_puerto
    
    v_salida_quena = q_m3s / area_total_quena if area_total_quena > 0 else 0.0
    
    # Pérdida de carga de la quena asumiendo flujo por orificio (Cd = 0.62)
    cd = 0.62
    h_difusor = ((v_salida_quena / cd)**2) / (2 * 9.81) if v_salida_quena > 0 else 0.0
    
    id_eq_mm = math.sqrt((4 * area_total_quena) / math.pi) * 1000
    
    hm_tot += h_difusor
    z_tot += 1.5 
    
    res_tramos.append({
        "Fila": "DIFUSOR", 
        "Mat": "Acero (Quena multipuerto)", 
        "ID(mm)": round(id_eq_mm, 1),
        "Vel.(m/s)": round(v_salida_quena, 2), 
        "Pérdida (mca)": round(h_difusor, 2), 
        "ΔZ(m)": 1.5, 
        "Ventosa": False, 
        "Ariete(mca)": 0.0, 
        "L": 40.0
    })

# ==========================================
# 4. DIAGNÓSTICO EJECUTIVO Y HGL
# ==========================================
presion_final_mca = (p_descarga_bar * 100000) / (rho * 9.81)
adt_req = z_tot + hf_tot + hm_tot + presion_final_mca

presion_actual_mca = adt_req if modo_operacion == "Modo B: Forense (Curva de Bomba)" else max(adt_req, presion_manometro_mca)

cum_L, cum_Z = 0.0, 0.0
x_plot, z_plot, hgl_plot = [0.0], [0.0], [presion_actual_mca]
v_min, v_max = 99.0, 0.0
alerta_vacio, alerta_presion, alerta_sedi = False, False, False

for tramo in res_tramos:
    presion_actual_mca -= (tramo["Pérdida (mca)"] + tramo["ΔZ(m)"])
    if tramo["Ventosa"] and presion_actual_mca < 0:
        presion_actual_mca = 0.0 
        
    p_bar = (presion_actual_mca * rho * 9.81) / 100000
    p_max_bar = p_bar + (tramo["Ariete(mca)"] * rho * 9.81 / 100000)
    
    tramo["P. Residual(bar)"] = round(p_bar, 2)
    tramo["P. Estallido(bar)"] = round(p_max_bar, 2)
    
    v = tramo["Vel.(m/s)"]
    if v > 0 and v < v_min: v_min = v
    if v > v_max: v_max = v
    if v < 0.6 and v > 0: alerta_sedi = True
    
    cum_L += tramo.get("L", 0.0)
    cum_Z += tramo.get("ΔZ(m)", 0.0)
    x_plot.append(cum_L)
    z_plot.append(cum_Z)
    hgl_plot.append(cum_Z + presion_actual_mca)

st.markdown("### 📊 Panel de Control y Alertas")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fricción + Accesorios (mca)", f"{(hf_tot + hm_tot):.2f}")
c2.metric("Desnivel + Océano", f"{(z_tot + presion_final_mca):.2f} mca")

if modo_operacion == "Modo A: Diseño de Línea (Lectura Manómetro)":
    margen = presion_manometro_mca - adt_req
    color = "normal" if margen >= 0 else "inverse"
    c3.metric("Energía Req vs Disponible", f"{adt_req:.1f} / {presion_manometro_mca:.1f}", delta=f"{margen:.1f} mca libres", delta_color=color)
else:
    c3.metric("ADT Requerido (mca)", f"{adt_req:.2f}")

c4.metric("Rango Velocidades", f"{v_min if v_min != 99.0 else 0.0:.1f} - {v_max:.1f} m/s")

if alerta_vacio: st.error("🚨 **COLAPSO POR VACÍO:** Presión negativa detectada. Revisa desniveles o añade ventosas.")
if alerta_presion: st.error("🚨 **RIESGO ESTALLIDO:** Golpe de ariete peligroso. Aumenta el tiempo de cierre amortiguado.")
if alerta_sedi: st.warning("⚠️ **SEDIMENTACIÓN:** Velocidad menor a 0.6 m/s en algún tramo.")

if len(res_tramos) > 0:
    df_res = pd.DataFrame(res_tramos).drop(columns=["L"], errors='ignore')
    st.dataframe(df_res.style.apply(lambda x: ['background: #ffe6e6' if v < 0 else '' for v in x], subset=['P. Residual(bar)']), use_container_width=True)

# ==========================================
# 5. GRÁFICOS INTERACTIVOS
# ==========================================
st.markdown("---")
col_graf1, col_graf2 = st.columns([1, 1.2])

with col_graf1:
    st.header("Intersección Sistema vs Energía")
    q_arr = np.linspace(0.001, (q1 if "Forense" in modo_operacion else q_m3h) * 1.5, 50) 
    adt_arr = []
    
    for q_i in q_arr:
        _, hf_i, hm_i, z_i = calcular_hidraulica(q_i / 3600.0, df_input, 0)
        
        if activar_quena and num_puertos > 0 and diam_puerto_in > 0:
            diam_puerto_m = diam_puerto_in * 0.0254
            area_tot = num_puertos * (math.pi * (diam_puerto_m / 2)**2)
            v_sal_i = (q_i / 3600.0) / area_tot
            h_dif_i = ((v_sal_i / 0.62)**2) / (2 * 9.81)
            hm_i += h_dif_i
            z_i += 1.5
            
        adt_arr.append(z_i + hf_i + hm_i + presion_final_mca)
        
    fig_sys = go.Figure()
    fig_sys.add_trace(go.Scatter(x=q_arr, y=adt_arr, mode='lines', name='Curva Sistema (Tubería)', line=dict(color='#1f77b4', width=3)))
    
    if modo_operacion == "Modo B: Forense (Curva de Bomba)":
        h_bomba = coefs_bomba[0]*(q_arr**2) + coefs_bomba[1]*q_arr + coefs_bomba[2]
        h_bomba = np.where(h_bomba < 0, 0, h_bomba) 
        fig_sys.add_trace(go.Scatter(x=q_arr, y=h_bomba, mode='lines', name='Fuerza Bomba', line=dict(color='#2ca02c', dash='dash', width=3)))
        
        diff = h_bomba - adt_arr
        idx = np.where(np.diff(np.sign(diff)))[0]
        if len(idx) > 0 and diff[0] > 0:
            i = idx[0]
            q_real = q_arr[i] + (q_arr[i+1] - q_arr[i]) * (diff[i] / (diff[i] - diff[i+1]))
            h_real = adt_arr[i] + (adt_arr[i+1] - adt_arr[i]) * (diff[i] / (diff[i] - diff[i+1]))
            fig_sys.add_trace(go.Scatter(x=[q_real], y=[h_real], mode='markers+text', marker=dict(color='red', size=14, symbol='x'), text=[f" Q: {q_real:.1f} m³/h"], textposition="top right", name="Equilibrio"))
            st.success(f"🎯 **El sistema fluirá a {q_real:.1f} m³/h.**")
        else:
            st.error("🔴 La fuerza no es suficiente para vencer el sistema.")
    else:
        fig_sys.add_trace(go.Scatter(x=[0, q_m3h * 1.5], y=[presion_manometro_mca, presion_manometro_mca], mode='lines', name='Manómetro (Energía Disponible)', line=dict(color='#2ca02c', dash='dot', width=2)))
        fig_sys.add_trace(go.Scatter(x=[q_m3h], y=[adt_req], mode='markers+text', marker=dict(color='#ff7f0e', size=12), text=[f" Req: {adt_req:.1f} mca"], textposition="top left", name="Demanda Sistema"))
        
    fig_sys.update_layout(xaxis_title="Caudal (m³/h)", yaxis_title="Altura Dinámica (mca)", template="plotly_white", margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=1.02))
    st.plotly_chart(fig_sys, use_container_width=True)

with col_graf2:
    st.header("Perfil Topográfico HGL")
    fig_perfil = go.Figure()
    fig_perfil.add_trace(go.Scatter(x=x_plot, y=z_plot, mode='lines+markers', name='Terreno/Tubo', fill='tozeroy', fillcolor='rgba(139, 69, 19, 0.2)', line=dict(color='#8B4513', width=3), marker=dict(size=8)))
    fig_perfil.add_trace(go.Scatter(x=x_plot, y=hgl_plot, mode='lines+markers', name='Presión (HGL)', line=dict(color='blue', dash='dot', width=3), marker=dict(size=6, color='red')))
    fig_perfil.update_layout(xaxis_title="Distancia (m)", yaxis_title="Elevación / Presión (m)", template="plotly_white", margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified", legend=dict(orientation="h", y=1.02))
    st.plotly_chart(fig_perfil, use_container_width=True)

# ==========================================
# 6. EXPORTACIÓN A EXCEL (REPORTE EJECUTIVO)
# ==========================================
st.markdown("---")
if len(res_tramos) > 0:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_resumen = pd.DataFrame({
            "Parámetro": [
                "Caudal de Diseño (m³/h)", 
                "Velocidad Mínima (m/s)",
                "Velocidad Máxima (m/s)",
                "Fricción Tubería y Accesorios (mca)", 
                "Desnivel + Contrapresión Océano (mca)", 
                "ADT Requerido (mca)"
            ],
            "Valor": [q_m3h, v_min if v_min != 99.0 else 0.0, v_max, round(hf_tot + hm_tot, 2), round(z_tot + presion_final_mca, 2), round(adt_req, 2)]
        })
        df_resumen.to_excel(writer, index=False, sheet_name='Resumen Ejecutivo')
        
        df_export_res = pd.DataFrame(res_tramos).drop(columns=["L"], errors='ignore')
        df_export_res.to_excel(writer, index=False, sheet_name='Resultados Hidráulicos')
        
        df_input.to_excel(writer, index=False, sheet_name='Datos de Entrada')
        
        workbook = writer.book
        formato_cabecera = workbook.add_format({'bold': True, 'bg_color': '#004C99', 'font_color': 'white', 'border': 1})
        formato_celda = workbook.add_format({'border': 1, 'align': 'center'})
        
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            df_sheet = df_resumen if sheet_name == 'Resumen Ejecutivo' else (df_export_res if sheet_name == 'Resultados Hidráulicos' else df_input)
            
            for col_num, value in enumerate(df_sheet.columns.values):
                worksheet.write(0, col_num, value, formato_cabecera)
                worksheet.set_column(col_num, col_num, 18, formato_celda)

    c_empty, c_btn, c_empty2 = st.columns([1, 2, 1])
    c_btn.download_button(
        label="📥 Descargar Memoria de Cálculo Excel (Formato AMPER)",
        data=output.getvalue(),
        file_name="Memoria_Calculo_AMPER_Quena.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )