import streamlit as st
import pandas as pd
import numpy as np
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import pytz
import json
import copy
import time
import re
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
    .report-card { background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 15px; padding: 20px; text-align: center; }
    .metric-val { font-size: 2rem; font-weight: 800; color: #38bdf8; }
    .metric-lbl { font-size: 0.8rem; color: #94a3b8; text-transform: uppercase; }
    </style>
    """, unsafe_allow_html=True)

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

def get_geo_data(query_list):
    geolocator = Nominatim(user_agent=f"brightstar_v522_{int(time.time())}")
    time.sleep(1.2)
    for q in query_list:
        try:
            location = geolocator.geocode(q, timeout=8)
            if location: return (location.latitude, location.longitude)
        except: continue
    return None

def pulisci_nome(nome):
    return ' '.join(re.sub(r'[^A-Z0-9\s]', '', str(nome).upper()).split())

def pulisci_coordinata_italy(coord_str, is_lat=True):
    if pd.isna(coord_str) or str(coord_str).strip() == "": return None
    c = str(coord_str).strip().replace(' ', '').replace(',', '.')
    try: 
        val = float(c)
        if abs(val) > 100:
            while abs(val) > 90: val = val / 10.0
        return val if (35 < val < 48 if is_lat else 6 < val < 20) else None
    except: return None

# --- CARICAMENTO DATI ---
ws, ws_ai, ws_mem, ws_pot = connect_db()
if ws:
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=[h.strip().upper() for h in data[0]])
    c_nom = next(c for c in df.columns if "CLIENTE" in c)
    c_ind = next(c for c in df.columns if "INDIRIZZO" in c or "VIA" in c)
    c_com = next(c for c in df.columns if "COMUNE" in c)
    c_prem = next((c for c in df.columns if "PREMIUM" in c), None)
    c_lat = next((c for c in df.columns if "LAT" in c.upper()), None)
    c_lon = next((c for c in df.columns if "LON" in c.upper()), None)

    st.markdown("<div class='app-header'>🚀 BRIGHTSTAR CRM PRO v5.22</div>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🚗 GIRO VISITE", "🛰️ RADAR 150m & TELEMACO"])

    with tab2:
        st.markdown("### 📂 Carica Lista Telemaco")
        file_tel = st.file_uploader("Trascina il file Excel/CSV", type=['xlsx', 'xls', 'csv'])
        
        if file_tel:
            if file_tel.name.endswith('.csv'): df_tel = pd.read_csv(file_tel, sep=None, engine='python', dtype=str)
            else: df_tel = pd.read_excel(file_tel, dtype=str)
            
            st.success(f"File caricato: {len(df_tel)} righe.")
            
            c_t1, c_t2, c_t3 = st.columns(3)
            idx_nome = next((i for i, c in enumerate(df_tel.columns) if "DENOMINAZIONE" in c.upper()), 0)
            with c_t1: col_nome_tel = st.selectbox("Colonna NOME:", df_tel.columns, index=idx_nome)
            idx_ind = next((i for i, c in enumerate(df_tel.columns) if "COMPLETO" in c.upper() or "INDIRIZZO" in c.upper()), 0)
            with c_t2: col_ind_tel = st.selectbox("Colonna INDIRIZZO:", df_tel.columns, index=idx_ind)
            idx_com = next((i for i, c in enumerate(df_tel.columns) if "COMUNE" in c.upper()), 0)
            with c_t3: col_com_tel = st.selectbox("Colonna COMUNE:", df_tel.columns, index=idx_com)

            st.info("👀 **ANTEPRIMA RICOSTRUZIONE INDIRIZZI:**")
            for idx_p, r_p in df_tel.head(3).iterrows():
                ind_v = str(r_p.get(col_ind_tel, '')).strip()
                if "Indirizzo" in ind_v or ind_v in ["","nan"]:
                    try: ind_v = f"{r_p.iloc[7]} {r_p.iloc[8]}, {r_p.iloc[13]}"
                    except: ind_v = "NON RILEVATO"
                st.write(f"🔹 {r_p[col_nome_tel]} -> **{ind_v}**")

            st.divider()
            modalita_cecchino = st.toggle("🎯 MODALITÀ CECCHINO (Filtra solo i tuoi Comuni)", value=True)
            
            if st.button("🚀 AVVIA SCANSIONE COMPLETA", type="primary", use_container_width=True):
                # 1. Cache Premium
                df_prem = df[df[c_prem].str.upper().str.contains("SI", na=False)].copy()
                st.info(f"⚡ FASE 1: Mappatura {len(df_prem)} Premium...")
                premium_coords = []
                for _, pr in df_prem.iterrows():
                    la = pulisci_coordinata_italy(pr.get(c_lat), True)
                    lo = pulisci_coordinata_italy(pr.get(c_lon), False)
                    if la and lo: premium_coords.append((la, lo))
                
                # 2. Scansione
                st.info("🛰️ FASE 2: Scansione Telemaco...")
                risultati_ok = []
                scarti = {"ZONA": 0, "CLIENTI": 0, "RADAR": 0, "MAPPA": 0}
                
                comuni_miei = [pulisci_nome(c) for c in df[c_com].unique()]
                nomi_miei = [pulisci_nome(n) for n in df[c_nom].unique()]
                
                prog = st.progress(0)
                for i, r_tel in df_tel.iterrows():
                    prog.progress((i+1)/len(df_tel))
                    nome_t = pulisci_nome(r_tel[col_nome_tel])
                    com_t = str(r_tel[col_com_tel]).upper().strip()
                    
                    # Filtro Zona
                    if modalita_cecchino and pulisci_nome(com_t) not in comuni_miei:
                        scarti["ZONA"] += 1; continue
                    
                    # Filtro Già Cliente
                    if nome_t in nomi_miei:
                        scarti["CLIENTI"] += 1; continue
                    
                    # Indirizzo
                    ind_t = str(r_tel.get(col_ind_tel, '')).strip()
                    if "Indirizzo" in ind_t or ind_t in ["","nan"]:
                        try: ind_t = f"{r_tel.iloc[7]} {r_tel.iloc[8]}"
                        except: ind_t = "Sconosciuto"
                    
                    # Radar
                    t_c = get_geo_data([f"{ind_t}, {com_t}, Italy"])
                    if t_c:
                        vicino = any(geodesic(t_c, pc).meters < 150 for pc in premium_coords)
                        if vicino: scarti["RADAR"] += 1
                        else: risultati_ok.append([nome_t, ind_t, com_t, "✅ DISPONIBILE"])
                    else: scarti["MAPPA"] += 1

                # 3. REPORT FINALE
                st.markdown("### 📊 Risultato Scansione")
                c1, c2, c3, c4 = st.columns(4)
                c1.markdown(f"<div class='report-card'><div class='metric-val'>{scarti['ZONA']}</div><div class='metric-lbl'>Fuori Zona</div></div>", unsafe_allow_html=True)
                c2.markdown(f"<div class='report-card'><div class='metric-val'>{scarti['CLIENTI']}</div><div class='metric-lbl'>Già Clienti</div></div>", unsafe_allow_html=True)
                c3.markdown(f"<div class='report-card'><div class='metric-val'>{scarti['RADAR']}</div><div class='metric-lbl'>Troppo Vicini</div></div>", unsafe_allow_html=True)
                c4.markdown(f"<div class='report-card'><div class='metric-val'>{scarti['MAPPA']}</div><div class='metric-lbl'>Mappa Fallita</div></div>", unsafe_allow_html=True)
                
                if risultati_ok:
                    st.success(f"🎯 Trovati {len(risultati_ok)} nuovi potenziali bar!")
                    df_ok = pd.DataFrame(risultati_ok, columns=["NOME", "INDIRIZZO", "COMUNE", "STATO"])
                    st.dataframe(df_ok, use_container_width=True)
                    if st.button("💾 SALVA TUTTI IN POTENZIALI"):
                        for row in risultati_ok: ws_pot.append_row([datetime.now().strftime("%d/%m/%Y"), "", row[0], row[1], row[2], "OK", ""])
                        st.success("Salvato!")
                else:
                    st.error("🚫 La scansione è finita, ma nessun bar ha superato i controlli. Controlla i contatori sopra per capire perché.")
