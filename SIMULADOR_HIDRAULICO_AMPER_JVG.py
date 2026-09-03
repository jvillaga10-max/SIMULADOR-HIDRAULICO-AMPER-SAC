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
profundidad_descarga = st.sidebar.number_input("Profundidad de descarga (m)", value=13.0)

st.sidebar.markdown("### 🪈 1.5. Difusor Final (Quena)")
activar_quena = st.sidebar.checkbox("Activar Difusor Multipuerto", value=True)
if activar_quena:
    num_puertos = st.sidebar.number_input("Cantidad de Puertos", value=12, min_value=1, step=1)
    diam_puerto_in = st.sidebar.number_input("Diámetro de Puerto (\")", value=8.0, min_value=1.0, step=0.5)
    espaciamiento = st.sidebar.number_input("Separación entre puertos (m)", value=4.0, min_value=1.0, step=0.5)
else:
    num_puertos = 0
    diam_puerto_in = 0.0
    espaciamiento = 0.0

st.sidebar.markdown("### ⚙️ 2. Escenario de Operación")
q_m3h = st.sidebar.number_input("Caudal Fijo (m³/h)", value=2500.0)
presion_manometro_mca = st.sidebar.number_input("Presión Inicial (mca)", value=25.0)
q_m3s = q_m3h / 3600.0
p_descarga_bar = (profundidad_descarga * rho * 9.81) / 100000
t_cierre = st.sidebar.number_input("Tiempo de Cierre (s)", value=20.0, min_value=0.1) 

# ==========================================
# 3. TABLA DE TRAMOS Y MOTOR HIDRÁULICO
# ==========================================
st.title("🌊 Simulador EPC: Hidráulica y Procura")

if "df_tramos" not in st.session_state:
    st.session_state.df_tramos = pd.DataFrame({
        "Material": ["Acero Carbono"], "NPS / DN": [24.0], "Clase/SDR": ["40"],
        "Longitud(m)": [434.0], "ΔZ (m)": [-13.0], "Ventosa": [False],
        "Codos 90": [0], "Codos 45": [0], "Tees (Dir)": [0], "Yees (Dir)": [0],
        "Yees (Ramal)": [0], "Valv. Compuerta": [0], "Valv. Mariposa": [0]
    })

acc_config = {acc: st.column_config.NumberColumn(acc, min_value=0, step=1, format="%d") for acc in LE_D_CRANE.keys()}
column_config = {
    "Material": st.column_config.SelectboxColumn("Material", options=["Acero Carbono", "HDPE PE100", "PVC Rígido"], required=True),
    "Clase/SDR": st.column_config.SelectboxColumn("Clase/SDR", options=["11", "13.6", "17", "20", "21", "30", "40", "80"], required=True),
    "Ventosa": st.column_config.CheckboxColumn("Ventosa"),
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
        
        L_recta = float(row.get("Longitud(m)", 0.0)) if pd.notna(row.get("Longitud(m)")) else 0.0
        dz = float(row.get("ΔZ (m)", 0.0)) if pd.notna(row.get("ΔZ (m)")) else 0.0
        
        hf = f_real * (L_recta / id_m) * (vel**2 / (2*9.81)) if L_recta > 0 else 0.0
        
        suma_k = 0.0
        for acc, le_d in LE_D_CRANE.items():
            valor_acc = row.get(acc, 0)
            if pd.notna(valor_acc) and str(valor_acc).strip() != "":
                try: suma_k += float(valor_acc) * le_d * f_real
                except: pass
                
        hm_total = suma_k * (vel**2 / (2*9.81))
        
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
            
        res.append({"Fila": idx + 1, "Mat": mat, "ID(mm)": round(id_mm, 1), "Vel.(m/s)": round(vel, 2), "Pérdida (mca)": round(hf + hm_total, 2), "ΔZ(m)": round(dz, 2), "Ventosa": bool(row.get("Ventosa", False)), "Ariete(mca)": round(delta_h, 1), "L": L_recta})
    return res, hf_acum, hm_acum, z_acum

res_tramos, hf_tot, hm_tot, z_tot = calcular_hidraulica(q_m3s, df_input, t_cierre)

# ==========================================
# 3.5. INTEGRACIÓN QUENA + CÁLCULO DE PERFIL
# ==========================================
perfil_quena_vels = []
if activar_quena and num_puertos > 0 and diam_puerto_in > 0:
    diam_puerto_m = diam_puerto_in * 0.0254
    area_puerto = math.pi * (diam_puerto_m / 2)**2
    area_total_quena = num_puertos * area_puerto
    v_salida_avg = q_m3s / area_total_quena if area_total_quena > 0 else 0.0
    h_difusor = ((v_salida_avg / 0.62)**2) / (2 * 9.81) if v_salida_avg > 0 else 0.0
    
    hm_tot += h_difusor
    z_tot += 1.5 
    L_quena = num_puertos * espaciamiento
    
    res_tramos.append({"Fila": "DIFUSOR", "Mat": "Acero (Quena)", "ID(mm)": round(math.sqrt((4*area_total_quena)/math.pi)*1000, 1), "Vel.(m/s)": round(v_salida_avg, 2), "Pérdida (mca)": round(h_difusor, 2), "ΔZ(m)": 1.5, "Ventosa": False, "Ariete(mca)": 0.0, "L": L_quena})

    # Simulación iterativa del perfil de velocidades (Bernoulli)
    try:
        last_pipe_row = df_input.iloc[-1]
        id_main_m = obtener_diametro_interno(last_pipe_row["Material"], last_pipe_row["NPS / DN"], last_pipe_row["Clase/SDR"]) / 1000.0
    except:
        id_main_m = (609.6 - 2*17.48)/1000.0 # Fallback 24" sch40
    
    a_main = math.pi * (id_main_m/2)**2
    
    def simular_bernoulli(H_end):
        Q_pipe, H_curr = 0.0, H_end
        ports_q = []
        for i in range(int(num_puertos)):
            q_out = 0.62 * area_puerto * math.sqrt(2 * 9.81 * max(0, H_curr))
            ports_q.append(q_out)
            Q_next = Q_pipe + q_out
            V_pipe = Q_pipe / a_main if a_main > 0 else 0
            V_next = Q_next / a_main if a_main > 0 else 0
            hf = 0.015 * (espaciamiento / id_main_m) * (V_next**2 / (2 * 9.81)) if i < num_puertos - 1 else 0
            h_rec = (V_next**2 - V_pipe**2) / (2 * 9.81)
            H_curr = H_curr + hf + h_rec
            Q_pipe = Q_next
        return Q_pipe, ports_q[::-1]

    H_low, H_high = 0.001, 20.0
    for _ in range(50):
        H_mid = (H_low + H_high) / 2
        Q_calc, qs = simular_bernoulli(H_mid)
        if Q_calc > q_m3s: H_high = H_mid
        else: H_low = H_mid
    
    _, qs = simular_bernoulli(H_mid)
    perfil_quena_vels = [{"Puerto": f"Puerto {i+1} (Cerca a Planta)", "Caudal (m3/h)": round(q*3600,1), "Velocidad (m/s)": round(q/area_puerto, 2)} for i, q in enumerate(qs)]

# ==========================================
# 4. DIAGNÓSTICO Y RESULTADOS
# ==========================================
presion_final_mca = (p_descarga_bar * 100000) / (rho * 9.81)
adt_req = z_tot + hf_tot + hm_tot + presion_final_mca
presion_actual_mca = max(adt_req, presion_manometro_mca)

v_min, v_max = 99.0, 0.0
for tramo in res_tramos:
    presion_actual_mca -= (tramo["Pérdida (mca)"] + tramo["ΔZ(m)"])
    if tramo["Ventosa"] and presion_actual_mca < 0: presion_actual_mca = 0.0 
    tramo["P. Residual(bar)"] = round((presion_actual_mca * rho * 9.81) / 100000, 2)
    tramo["P. Estallido(bar)"] = round(tramo["P. Residual(bar)"] + (tramo["Ariete(mca)"] * rho * 9.81 / 100000), 2)
    v = tramo["Vel.(m/s)"]
    if v > 0 and v < v_min: v_min = v
    if v > v_max: v_max = v

st.markdown("### 📊 Panel de Control y Alertas")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fricción + Accesorios (mca)", f"{(hf_tot + hm_tot):.2f}")
c2.metric("Desnivel + Océano (mca)", f"{(z_tot + presion_final_mca):.2f}")
c3.metric("Energía Req vs Disponible", f"{adt_req:.1f} / {presion_manometro_mca:.1f}")
c4.metric("Rango Velocidades", f"{v_min if v_min != 99.0 else 0.0:.1f} - {v_max:.1f} m/s")

if len(res_tramos) > 0:
    df_res = pd.DataFrame(res_tramos).drop(columns=["L"], errors='ignore')
    st.dataframe(df_res.style.apply(lambda x: ['background: #ffe6e6' if v < 0 else '' for v in x], subset=['P. Residual(bar)']), use_container_width=True)

if activar_quena and len(perfil_quena_vels) > 0:
    with st.expander("🔍 Ver Perfil Hidráulico de los Agujeros (Quena)"):
        st.write("Demostración física del Efecto Bernoulli: La velocidad y presión aumentan hacia el final de la brida ciega.")
        st.table(pd.DataFrame(perfil_quena_vels))

# ==========================================
# 5. GENERACIÓN DEL BOM (LISTA DE MATERIALES)
# ==========================================
st.markdown("---")
st.header("📝 Lista de Materiales (BOM - MTO Automático)")

bom_data = []
for (mat, nps, clase), group in df_input.groupby(['Material', 'NPS / DN', 'Clase/SDR']):
    if pd.isna(mat) or pd.isna(nps) or nps <= 0: continue
    L_total = pd.to_numeric(group['Longitud(m)'], errors='coerce').sum()
    
    # Normativas automáticas
    norma_tubo = "ISO 4427 / ASTM F714" if mat == "HDPE PE100" else "ASME B36.10 / API 5L" if mat == "Acero Carbono" else "ISO 1452"
    norma_acc = "ISO 4427 (Termofusión)" if mat == "HDPE PE100" else "ASME B16.9 (Buttweld)" if mat == "Acero Carbono" else "Inyectado"
    brida_norm = "Stub End + Brida Respaldo (ASME B16.5 / ISO 4427)" if mat == "HDPE PE100" else "Brida WN/SO (ASME B16.5)" if mat == "Acero Carbono" else "Brida (ISO 1452)"
    
    if L_total > 0:
        bom_data.append({"Sistema": "Línea Matriz", "Material": mat, "Ítem": f"Tubería {nps}\" SDR/Clase {clase}", "Cantidad": f"{L_total:.1f}", "Und": "m", "Norma/Estándar": norma_tubo})
    
    for acc in LE_D_CRANE.keys():
        sum_acc = pd.to_numeric(group[acc], errors='coerce').fillna(0).sum()
        if sum_acc > 0:
            bom_data.append({"Sistema": "Accesorios", "Material": mat, "Ítem": f"{acc} de {nps}\" (SDR/Clase {clase})", "Cantidad": f"{int(sum_acc)}", "Und": "und", "Norma/Estándar": norma_acc})
            # Estimación automática de Stub Ends y Bridas (Se asume 2 bridas/stub ends por accesorio instalado)
            bom_data.append({"Sistema": "Juntas/Conexión", "Material": mat, "Ítem": f"Set de Conexión Bridada para Accesorio {nps}\"", "Cantidad": f"{int(sum_acc * 2)}", "Und": "sets", "Norma/Estándar": brida_norm})

if activar_quena and num_puertos > 0:
    bom_data.append({"Sistema": "Cabezal Quena", "Material": "Acero Carbono", "Ítem": f"Niples/Puertos Difusor Biselados {diam_puerto_in}\"", "Cantidad": f"{int(num_puertos)}", "Und": "und", "Norma/Estándar": "ASME B36.10"})
    bom_data.append({"Sistema": "Cabezal Quena", "Material": "Elastomérico", "Ítem": f"Válvulas Pico de Pato (Check) {diam_puerto_in}\"", "Cantidad": f"{int(num_puertos)}", "Und": "und", "Norma/Estándar": "AWWA / Tideflex"})
    bom_data.append({"Sistema": "Cabezal Quena", "Material": "Acero Carbono", "Ítem": f"Brida Ciega Terminal (Blind Flange) para Matriz", "Cantidad": "1", "Und": "und", "Norma/Estándar": "ASME B16.5"})
    bom_data.append({"Sistema": "Anclaje", "Material": "Concreto Armado", "Ítem": "Dados de Lastre / Anclaje para Quena", "Cantidad": "Lote", "Und": "glb", "Norma/Estándar": "Diseño Estructural"})

df_bom = pd.DataFrame(bom_data)
st.dataframe(df_bom, use_container_width=True)

# ==========================================
# 6. EXPORTACIÓN A EXCEL (REPORTE COMPLETO)
# ==========================================
st.markdown("---")
if len(res_tramos) > 0:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_resumen = pd.DataFrame({"Parámetro": ["Caudal (m³/h)", "ADT Requerido (mca)"], "Valor": [q_m3h, round(adt_req, 2)]})
        df_resumen.to_excel(writer, index=False, sheet_name='Resumen Ejecutivo')
        df_res.to_excel(writer, index=False, sheet_name='Resultados Hidráulicos')
        df_input.to_excel(writer, index=False, sheet_name='Datos de Entrada')
        df_bom.to_excel(writer, index=False, sheet_name='Lista de Materiales BOM')
        
        if activar_quena and len(perfil_quena_vels) > 0:
            pd.DataFrame(perfil_quena_vels).to_excel(writer, index=False, sheet_name='Perfil de Quena')
            
        workbook = writer.book
        fmt_head = workbook.add_format({'bold': True, 'bg_color': '#004C99', 'font_color': 'white', 'border': 1})
        fmt_cell = workbook.add_format({'border': 1, 'align': 'center'})
        
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            # Autofit rudimentario y estilos
            worksheet.set_column(0, 10, 20, fmt_cell)
            worksheet.set_row(0, None, fmt_head)

    c_empty, c_btn, c_empty2 = st.columns([1, 2, 1])
    c_btn.download_button(
        label="📥 Descargar Memoria de Cálculo y Lista de Materiales (Excel)",
        data=output.getvalue(),
        file_name="Memoria_y_BOM_AMPER.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )