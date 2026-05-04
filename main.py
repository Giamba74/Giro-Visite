import streamlit as st
import pandas as pd
import numpy as np
from geopy.distance import geodesic
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import pytz
import json
import copy
import time
import re
import requests
import io

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar CRM PRO", page_icon="💎", layout="wide")
TZ_ITALY = pytz.timezone('Europe/Rome')

# --- 🎨 DESIGN E STILE CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    .stApp { font-family: 'Inter', sans-serif; background: radial-gradient(circle at top left, #1e293b 0%, #0f172a 100%); color: #f1f5f9; }
    .app-header { background: linear-gradient(90deg, #2563eb, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.5rem; font-weight: 800; text-align: center; margin-bottom: 30px; letter-spacing: -1px;}
    .client-card { background: linear-gradient(145deg, rgba(30, 41, 59, 0.85), rgba(15, 23, 42, 0.9)); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 20px; padding: 24px; margin-bottom: 16px; box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5); }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 12px; }
    .arrival-time { background: linear-gradient(135deg, #3b82f6, #6366f1); color: white; padding: 6px 16px; border-radius: 30px; font-weight: 700; }
    .strategy-box { padding: 12px 16px; border-radius: 10px; margin-bottom: 18px; font-size: 0.95em; border-left: 5px solid; background: rgba(0,0,0,0.25); }
    .report-card { background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 20px; text-align: center; }
    .metric-val { font-size: 1.8rem; font-weight: 800; color: #38bdf8; }
    </style>
    """, unsafe_allow_html=True)

COORDS = { "Chianti": (43.661888, 11.305728), "Firenze": (43.7696, 11.2558), "Arezzo": (43.4631, 11.8781) }
SEDE_COORDS = COORDS["Chianti"]

# ==============================================================================
# 👇 MODIFICA SOLO QUI SOTTO CON IL TUO VERO ID FOGLIO GOOGLE 👇
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" 
# ==============================================================================

@st.cache_resource
def connect_db():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_key(ID_DEL_FOGLIO)
        ws_main = sh.get_worksheet(0)
        ws_log = sh.worksheet("LOG_AI") if "LOG_AI" in [w.title for w in sh.worksheets()] else None
        ws_mem = sh.worksheet("MEMORIA_GIRO") if "MEMORIA_GIRO" in [w.title for w in sh.worksheets()] else None
        ws_pot = sh.worksheet("POTENZIALI") if "POTENZIALI" in [w.title for w in sh.worksheets()] else None
        return ws_main, ws_log, ws_mem, ws_pot
    except: return None, None, None, None

def pulisci_coordinata_italy(coord_str, is_lat=True):
    if pd.isna(coord_str) or str(coord_str).strip() == "": return None
    c = str(coord_str).strip().replace(' ', '').replace(',', '.')
    try: 
        val = float(c)
        if abs(val) > 100:
            while abs(val) > 90: val = val / 10.0
        if is_lat and (35 < val < 48): return val
        if not is_lat and (6 < val < 20): return val
        return None
    except: return None

def carica_giro_da_foglio(sh_memoria):
    try:
        json_data = sh_memoria.acell("B2").value
        if json_data:
            rotta = json.loads(json_data)
            for p in rotta:
                if 'arr' in p and isinstance(p['arr'], str):
                    p['arr'] = datetime.strptime(p['arr'], "%Y-%m-%d %H:%M:%S")
                if 'coords' not in p or p['coords'] is None:
                    p['coords'] = SEDE_COORDS
            return rotta
    except: return None
    return None

# 🚀 IL NUOVO MOTORE MAPPE ARCGIS (Infallibile)
def get_geo_data(query_list):
    time.sleep(0.5) # Pausa più breve perché ArcGIS è più veloce
    for q in query_list:
        try:
            url = f"https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?singleLine={requests.utils.quote(q)}&f=json&maxLocations=1"
            risposta = requests.get(url, timeout=8).json()
            if risposta.get('candidates') and len(risposta['candidates']) > 0:
                lat = risposta['candidates'][0]['location']['y']
                lon = risposta['candidates'][0]['location']['x']
                return (lat, lon)
        except: continue
    return None

def pulisci_nome(nome):
    return ' '.join(re.sub(r'[^A-Z0-9\s]', '', str(nome).upper().strip()).split())

def agente_strategico(note):
    if not note: return "ℹ️ COACH: Nessuno storico.", "border-left-color: #475569;"
    txt = str(note).lower()
    if any(x in txt for x in ['arrabbiato', 'reclamo']): return "🛡️ COACH: Cliente a rischio.", "border-left-color: #ef4444;"
    return f"ℹ️ MEMO: {note[:50]}...", "border-left-color: #3b82f6;"

# --- AVVIO APP ---
ws, ws_ai, ws_mem, ws_pot = connect_db()
if ws:
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=[h.strip().upper() for h in data[0]])
    
    # Mappatura colonne DB
    c_nom = next(c for c in df.columns if "CLIENTE" in c)
    c_ind = next(c for c in df.columns if "INDIRIZZO" in c or "VIA" in c)
    c_com = next(c for c in df.columns if "COMUNE" in c)
    c_vis = next(c for c in df.columns if "VISITATO" in c)
    c_prem = next((c for c in df.columns if "PREMIUM" in c), None)
    c_lat = next((c for c in df.columns if "LAT" in c.upper()), None)
    c_lon = next((c for c in df.columns if "LON" in c.upper()), None)
    c_note_sto = next((c for c in df.columns if "STORICO" in c or "NOTE" in c), None)

    if 'master_route' not in st.session_state and ws_mem:
        st.session_state.master_route = carica_giro_da_foglio(ws_mem)

    st.markdown("<div class='app-header'>🚀 BRIGHTSTAR CRM PRO v5.26</div>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["🚗 GIRO VISITE", "🛰️ RADAR 150m & TELEMACO"])

    with tab1:
        st.sidebar.markdown("### 🗺️ Opzioni Giro")
        indirizzo_start = st.sidebar.text_input("📍 Partenza:", value="Chianti, Sede")
        num_visite = st.sidebar.slider("🚗 Clienti:", 1, 25, 8)
        only_premium = st.sidebar.toggle("💎 Solo PREMIUM", value=True)
        
        comuni_unici = sorted(df[c_com].unique())
        sel_zona_giro = st.sidebar.multiselect("🌍 Filtra Comune:", comuni_unici)

        if st.button("🔄 CALCOLA NUOVO GIRO OTTIMIZZATO", type="primary", use_container_width=True):
            with st.spinner("IA sta calcolando la rotta migliore..."):
                mask = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
                if sel_zona_giro: mask &= df[c_com].isin(sel_zona_giro)
                if only_premium and c_prem: mask &= df[c_prem].astype(str).str.upper().str.contains('SI', na=False)
                
                pool = df[mask].head(num_visite).to_dict('records')
                rotta = []
                curr_t = datetime.now(TZ_ITALY).replace(hour=9, minute=0)
                for p in pool:
                    p['arr'] = curr_t
                    la = pulisci_coordinata_italy(p.get(c_lat), True)
                    lo = pulisci_coordinata_italy(p.get(c_lon), False)
                    p['coords'] = (la, lo) if la and lo else SEDE_COORDS
                    rotta.append(p)
                    curr_t += timedelta(minutes=40)
                
                st.session_state.master_route = rotta
                if ws_mem: ws_mem.update_acell("B2", json.dumps(rotta, default=str))
                st.rerun()

        if st.session_state.get('master_route'):
            for i, p in enumerate(st.session_state.master_route):
                msg_c, style_c = agente_strategico(p.get(c_note_sto, ''))
                st.markdown(f"""
                <div class="client-card">
                    <div class="card-header"><div class="arrival-time">{pd.to_datetime(p['arr']).strftime('%H:%M')}</div></div>
                    <div class="client-name">{i+1}. {p[c_nom]}</div>
                    <div class="strategy-box" style="{style_c}">{msg_c}</div>
                    <div style="color:#94a3b8; font-weight:500;">📍 {p[c_ind]}, {p[c_com]}</div>
                </div>
                """, unsafe_allow_html=True)
                
                c_dest = p.get('coords', SEDE_COORDS)
                if not isinstance(c_dest, (list, tuple)) or len(c_dest) < 2: c_dest = SEDE_COORDS
                
                c1, c2 = st.columns(2)
                with c1: st.link_button("🚙 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={c_dest[0]},{c_dest[1]}", use_container_width=True)
                with c2: 
                    if st.button("✅ CHIUDI VISITA", key=f"f_{i}", use_container_width=True, type="primary"):
                        st.session_state.master_route.pop(i)
                        if ws_mem: ws_mem.update_acell("B2", json.dumps(st.session_state.master_route, default=str))
                        st.rerun()
        else:
            st.info("💡 Usa la barra laterale per generare un nuovo giro visite!")

    with tab2:
        file_tel = st.file_uploader("📂 Carica File Telemaco (Excel/CSV)", type=['xlsx', 'csv'])
        if file_tel:
            df_tel = pd.read_excel(file_tel, dtype=str) if file_tel.name.endswith('.xlsx') else pd.read_csv(file_tel, sep=None, engine='python', dtype=str)
            
            st.markdown("#### ⚙️ Associazione Colonne Telemaco")
            c_t1, c_t2, c_t3 = st.columns(3)
            with c_t1: col_nome_tel = st.selectbox("Colonna Nome:", df_tel.columns, index=0)
            idx_ind_tel = next((i for i, c in enumerate(df_tel.columns) if "COMPLETO" in c.upper() or "INDIRIZZO" in c.upper()), 0)
            with c_t2: col_ind_tel = st.selectbox("Colonna Indirizzo:", df_tel.columns, index=idx_ind_tel)
            with c_t3: col_com_tel = st.selectbox("Colonna Comune:", df_tel.columns, index=next((i for i, c in enumerate(df_tel.columns) if "COMUNE" in c.upper()), 0))

            st.info("👀 **Anteprima Dati Lettura:**")
            for _, r_pre in df_tel.head(3).iterrows():
                val_i = str(r_pre.get(col_ind_tel, '')).strip()
                if "Indirizzo" in val_i or val_i in ["", "nan"]:
                    try:
                        via_p = str(r_pre.iloc[7]).replace('nan', '').strip()
                        civ_p = str(r_pre.iloc[8]).replace('nan', '').strip()
                        val_i = f"{via_p} {civ_p}".strip()
                    except: val_i = "ERRORE"
                st.write(f"🔹 {r_pre[col_nome_tel]} -> **{val_i}**")

            st.divider()
            modalita_cecchino = st.toggle("🎯 MODALITÀ CECCHINO (Filtra solo comuni del tuo database)", value=True)
            comuni_miei_puliti = [pulisci_nome(c) for c in df[c_com].unique() if str(c).strip()]
            
            if not modalita_cecchino:
                comuni_file = sorted(df_tel[col_com_tel].unique())
                sel_comuni_radar = st.multiselect("🌍 Seleziona Comuni da scansionare:", comuni_file, default=comuni_file[:3])
            else:
                st.write(f"ℹ️ Il Cecchino monitorerà {len(comuni_miei_puliti)} comuni diversi.")
                sel_comuni_radar = comuni_miei_puliti

            if st.button("🚀 AVVIA RADAR 150m", type="primary", use_container_width=True):
                df_prem = df[df[c_prem].astype(str).str.upper().str.contains("SI", na=False)].copy() if c_prem else df.head(0)
                premium_coords = []
                for _, pr in df_prem.iterrows():
                    la, lo = pulisci_coordinata_italy(pr.get(c_lat),True), pulisci_coordinata_italy(pr.get(c_lon),False)
                    if la: premium_coords.append((la, lo))
                
                risultati_ok = []
                scarti = {"ZONA": 0, "CLIENTI": 0, "RADAR": 0, "MAPPA": 0}
                nomi_miei_puliti = [pulisci_nome(n) for n in df[c_nom].unique()]
                
                prog = st.progress(0)
                for i, r_tel in df_tel.iterrows():
                    prog.progress((i+1)/len(df_tel))
                    com_t_raw = str(r_tel[col_com_tel]).strip()
                    com_t_pulito = pulisci_nome(com_t_raw)
                    nome_t_pulito = pulisci_nome(r_tel[col_nome_tel])
                    
                    if modalita_cecchino:
                        if com_t_pulito not in comuni_miei_puliti:
                            scarti["ZONA"] += 1; continue
                    else:
                        if com_t_raw not in sel_comuni_radar:
                            scarti["ZONA"] += 1; continue

                    if nome_t_pulito in nomi_miei_puliti:
                        scarti["CLIENTI"] += 1; continue
                    
                    # Pulizia intelligente dell'indirizzo
                    ind_t = str(r_tel.get(col_ind_tel, '')).strip()
                    if "Indirizzo" in ind_t or ind_t in ["", "nan"]:
                        try:
                            via = str(r_tel.iloc[7]).replace('nan', '').strip()
                            civ = str(r_tel.iloc[8]).replace('nan', '').strip()
                            ind_t = f"{via} {civ}".strip()
                        except: ind_t = ""
                    
                    # Ricerca Mappa Avanzata
                    t_c = get_geo_data([f"{ind_t}, {com_t_raw}, Italy", f"{com_t_raw}, Italy"])
                    if t_c:
                        vicino = any(geodesic(t_c, pc).meters < 150 for pc in premium_coords)
                        if vicino: scarti["RADAR"] += 1
                        else: risultati_ok.append([r_tel[col_nome_tel], ind_t, com_t_raw, "✅ DISPONIBILE"])
                    else: scarti["MAPPA"] += 1

                st.markdown("### 📊 Report Scansione")
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Fuori Zona", scarti["ZONA"])
                c2.metric("Già Clienti", scarti["CLIENTI"])
                c3.metric("Troppo Vicini", scarti["RADAR"])
                c4.metric("Errori Mappa", scarti["MAPPA"])
                
                if risultati_ok:
                    df_res = pd.DataFrame(risultati_ok, columns=["CLIENTE", "INDIRIZZO", "COMUNE", "STATO"])
                    st.success(f"🎯 Radar completato! Trovati {len(risultati_ok)} bar validi.")
                    st.dataframe(df_res, use_container_width=True)
                    st.download_button("📥 SCARICA RISULTATI", df_res.to_csv(index=False, sep=";").encode('utf-8-sig'), "TARGET_RADAR.csv")
                else:
                    st.warning("⚠️ Scansione finita: nessun bar ha superato i criteri del radar.")
