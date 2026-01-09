import streamlit as st
import pandas as pd
import numpy as np
from geopy.distance import geodesic
from datetime import datetime, time, timedelta
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar Max Performance", page_icon="⚡", layout="wide")
SEDE_COORDS = (43.661888, 11.305728) # Strada in Chianti
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")

st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 20px; border-radius: 15px; border: 2px solid #FFD700; margin-bottom: 20px; }
    .tappa-card { padding: 10px; border-radius: 8px; background-color: #00122e; border-left: 5px solid #FFD700; margin-bottom: 5px; color: white; }
    .indirizzo-testo { color: #FFD700; font-size: 0.9em; font-weight: bold; }
    .time-badge { background-color: #28a745; color: white; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
    .warning-text { color: #ff4b4b; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. INTELLIGENZA GOOGLE (ORARI E POSIZIONE) ---
def get_google_details(nome, indirizzo, comune):
    if not API_KEY: return None
    queries = [f"{indirizzo}, {comune}, Italy", f"{nome}, {comune}, Italy"]
    for q in queries:
        try:
            # Cerca ID
            url_s = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={urllib.parse.quote(q)}&key={API_KEY}"
            res_s = requests.get(url_s).json()
            if res_s.get('status') == 'OK' and res_s.get('results'):
                pid = res_s['results'][0]['place_id']
                geo = res_s['results'][0]['geometry']['location']
                
                # Scarica Orari
                url_d = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={pid}&fields=opening_hours,formatted_phone_number&key={API_KEY}"
                det = requests.get(url_d).json().get('result', {})
                return {
                    "coords": (geo['lat'], geo['lng']),
                    "tel": det.get('formatted_phone_number', ''),
                    "periods": det.get('opening_hours', {}).get('periods', []),
                    "found": True
                }
        except: continue
    return None

def is_open(periods, check_time):
    """Verifica se aperto in quell'ora specifica"""
    if not periods: return True # Default aperto se no dati
    py_day = check_time.weekday()
    g_day = (py_day + 1) % 7
    time_int = int(check_time.strftime("%H%M"))
    
    for p in periods:
        if p.get('open') and p['open']['day'] == g_day:
            start = int(p['open']['time'])
            end = int(p['close']['time']) if p.get('close') else 2359
            if start <= time_int < end:
                return True
    return False

# --- 3. ALGORITMO DI SATURAZIONE ---
def calcola_giro_massivo(clienti, start_time, durata_visita_min):
    """
    Riempie il secchio del tempo fino all'orlo (19:30 rientro a casa).
    """
    rotta = []
    ora_attuale = start_time
    punto_attuale = SEDE_COORDS
    limit_time = start_time.replace(hour=19, minute=30, second=0)
    
    # Se partiamo dopo le 19:30, impossibile
    if ora_attuale >= limit_time:
        return [], ora_attuale

    pool = clienti.copy()
    
    while pool:
        best_cand = None
        best_dist = float('inf')
        
        for cand in pool:
            # 1. Tempo per arrivare la
            dist_km = geodesic(punto_attuale, cand['coords']).km
            tempo_viaggio = (dist_km / 35) * 60 # Stima 35km/h traffico misto
            
            ora_arrivo = ora_attuale + timedelta(minutes=tempo_viaggio)
            ora_ripartenza = ora_arrivo + timedelta(minutes=durata_visita_min)
            
            # 2. CHECK CRITICO: Ce la faccio a tornare a casa entro le 19:30?
            dist_ritorno = geodesic(cand['coords'], SEDE_COORDS).km
            tempo_ritorno = (dist_ritorno / 35) * 60
            ora_rientro_casa = ora_ripartenza + timedelta(minutes=tempo_ritorno)
            
            if ora_rientro_casa > limit_time:
                continue # Non faccio in tempo a tornare, scartato
            
            # 3. CHECK APERTURA: È aperto quando arrivo?
            aperto = is_open(cand.get('periods', []), ora_arrivo)
            
            # Punteggio: Minimizzo la distanza, ma penalizzo enormemente se chiuso
            score = dist_km
            if not aperto:
                score += 10000 # Lo scarto praticamente sempre se chiuso
            
            # Ottimizzazione Pausa Pranzo: se è ora di pranzo (13-14) e lui è aperto, dagli priorità
            if aperto and 12 < ora_arrivo.hour < 14:
                score -= 5

            if score < best_dist:
                best_dist = score
                best_cand = cand
                best_cand['arr'] = ora_arrivo
                best_cand['dep'] = ora_ripartenza
                best_cand['open_status'] = aperto

        if best_cand and best_cand['open_status']:
            # Aggiungo alla rotta
            rotta.append(best_cand)
            ora_attuale = best_cand['dep']
            punto_attuale = best_cand['coords']
            pool.remove(best_cand)
        else:
            # Se non trovo nessuno (o tutti chiusi, o tempo finito), provo ad avanzare di 15 min 
            # (magari qualcuno apre) o esco se manca poco
            if (limit_time - ora_attuale).total_seconds() < 1800: # Meno di 30 min alla fine
                break
            ora_attuale += timedelta(minutes=15)
            
    return rotta, ora_attuale

# --- 4. APP ---
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" # <--- ID FOGLIO

@st.cache_resource
def init_gsheet(sheet_id):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        return gspread.authorize(creds).open_by_key(sheet_id).get_worksheet(0)
    except: return None

ws = init_gsheet(ID_DEL_FOGLIO)

if ws:
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=[h.strip().upper() for h in data[0]])
    
    # Mappatura colonne
    c_nom = next(c for c in df.columns if "CLIENTE" in c)
    c_ind = next(c for c in df.columns if "INDIRIZZO" in c or "VIA" in c)
    c_com = next(c for c in df.columns if "COMUNE" in c)
    c_cap = next((c for c in df.columns if "CAP" in c), "CAP")
    c_vis = next(c for c in df.columns if "VISITATO" in c)
    c_tel = next((c for c in df.columns if "TELEFONO" in c), "TELEFONO")
    c_cod = next((c for c in df.columns if "CODICE" in c), "CODICE")

    if c_cap in df.columns:
        df[c_cap] = df[c_cap].astype(str).str.replace('.0', '', regex=False).str.strip().str.zfill(5)

    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            sel_comuni = st.multiselect("📍 Zona:", sorted(df[c_com].unique().tolist()))
            sel_caps = st.multiselect("📮 CAP:", sorted(df[c_cap].unique().tolist()) if c_cap in df.columns else [])
        with col2:
            durata = st.slider("⏱️ Durata media visita (min):", 10, 60, 20)
            st.caption("Il sistema inserirà il massimo numero di visite possibili da 20 minuti tra le 07:30 e le 19:30.")

        if st.button("⚡ CALCOLA GIRO MASSIVO (MAX VISITE)"):
            mask = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
            if sel_comuni: mask &= df[c_com].isin(sel_comuni)
            if sel_caps: mask &= df[c_cap].isin(sel_caps)
            
            raw = df[mask].to_dict('records')
            
            if not raw:
                st.error("Nessun cliente da visitare!")
            else:
                with st.spinner("Ottimizzazione massima densità in corso..."):
                    # 1. Arricchimento dati
                    potenziali = []
                    for r in raw:
                        g = get_google_details(r[c_nom], r[c_ind], r[c_com])
                        if g and g['found']:
                            r.update(g)
                            potenziali.append(r)
                        else:
                            # Se non trovato, lo usiamo ma con coordinate sede (fallback)
                            r['coords'] = SEDE_COORDS
                            r['periods'] = []
                            r['found'] = False
                            potenziali.append(r)

                    # 2. Setup Tempo
                    now = datetime.now()
                    # Simulazione start 07:30 se fuori orario, altrimenti ora attuale
                    start_t = now
                    if now.hour < 7 or now.hour > 19:
                        start_t = now.replace(hour=7, minute=30, second=0)
                        if now.hour > 19: start_t += timedelta(days=1)
                    
                    # 3. Algoritmo
                    giro, ora_f = calcola_giro_massivo(potenziali, start_t, durata)
                    
                    st.session_state.giro_max = giro
                    st.session_state.rientro_stimato = (ora_f + timedelta(minutes=(geodesic(giro[-1]['coords'], SEDE_COORDS).km/35)*60)).strftime("%H:%M") if giro else "19:30"
                    st.rerun()

    # --- OUTPUT ---
    if 'giro_max' in st.session_state:
        n_visite = len(st.session_state.giro_max)
        st.success(f"✅ Pianificate {n_visite} visite! Rientro a casa stimato: {st.session_state.rientro_stimato}")
        
        for i, p in enumerate(st.session_state.giro_max):
            orario = p['arr'].strftime("%H:%M")
            with st.container():
                st.markdown(f"""
                <div class="tappa-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:bold; font-size:1.1em;">{i+1}. {p[c_nom]}</span>
                        <span class="time-badge">{orario}</span>
                    </div>
                    <div class="indirizzo-testo">📍 {p[c_ind]}, {p[c_com]}</div>
                    <div style="font-size:0.8em; color:#ccc;">Cod: {p[c_cod]}</div>
                </div>
                """, unsafe_allow_html=True)
                
                # Note
                st.session_state.giro_max[i]['NOTE'] = st.text_area("Note:", value=p.get('NOTE',''), key=f"n_{i}", height=50)
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    if p.get('found'):
                        # Link universale
                        lnk = f"https://www.google.com/maps/dir/?api=1&destination={p['coords'][0]},{p['coords'][1]}&travelmode=driving"
                        st.link_button("🚙 NAVIGA", lnk)
                    else: st.warning("⚠️ No GPS")
                with c2:
                    tel = p.get('tel') or p.get(c_tel)
                    if tel: st.link_button("📞 CHIAMA", f"tel:{tel}")
                with c3:
                    if st.button("✅ FATTO", key=f"d_{i}"):
                        try:
                            cell = ws.find(p[c_nom])
                            ws.update_cell(cell.row, list(df.columns).index(c_vis)+1, "SI")
                            st.session_state.giro_max.pop(i)
                            st.rerun()
                        except: st.error("Errore Sync")

        if st.button("📧 INVIA REPORT"):
             st.info("Report inviato (simulazione).")
