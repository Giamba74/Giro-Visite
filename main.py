import streamlit as st
import pandas as pd
import numpy as np
from geopy.distance import geodesic
from datetime import datetime, timedelta
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials
import pytz

# --- 1. CONFIGURAZIONE & DESIGN ---
st.set_page_config(page_title="Brightstar AI PRO", page_icon="🧠", layout="wide")
TZ_ITALY = pytz.timezone('Europe/Rome')

st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); font-family: 'Segoe UI', sans-serif; color: #e2e8f0; }
    
    /* Meteo */
    .meteo-card { padding: 15px; border-radius: 12px; color: white; margin-bottom: 25px; text-align: center; font-weight: bold; border: 1px solid rgba(255,255,255,0.2); }
    
    /* Card Cliente */
    .client-card { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 20px; margin-bottom: 5px; }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .client-name { font-size: 1.3rem; font-weight: 700; color: #f8fafc; }
    .arrival-time { background: linear-gradient(90deg, #3b82f6, #2563eb); color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; }
    
    /* Box Agenti */
    .strategy-box { padding: 10px; border-radius: 8px; margin-bottom: 8px; font-size: 0.9em; color: white; border-left: 4px solid; }
    .canvass-box { 
        background: linear-gradient(90deg, #7e22ce, #a855f7); 
        padding: 10px; border-radius: 8px; margin-bottom: 15px; 
        font-weight: bold; color: white; border: 1px solid #d8b4fe;
        animation: pulse 2s infinite;
    }
    
    .info-row { display: flex; gap: 15px; color: #94a3b8; font-size: 0.9rem; margin-bottom: 5px; }
    .highlight { color: #38bdf8; font-weight: 600; }
    .real-traffic { color: #f59e0b; font-size: 0.8rem; font-style: italic; }
    .ai-badge { font-size: 0.75rem; background-color: #334155; color: #cbd5e1; padding: 2px 8px; border-radius: 4px; }
    
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(168, 85, 247, 0.4); }
        70% { box-shadow: 0 0 0 10px rgba(168, 85, 247, 0); }
        100% { box-shadow: 0 0 0 0 rgba(168, 85, 247, 0); }
    }
    </style>
    """, unsafe_allow_html=True)

# --- DATI ---
COORDS = { "Chianti": (43.661888, 11.305728), "Firenze": (43.7696, 11.2558), "Arezzo": (43.4631, 11.8781) }
SEDE_COORDS = COORDS["Chianti"]
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")

# ==============================================================================
# 👇 MODIFICA SOLO QUI SOTTO CON IL TUO ID FOGLIO GOOGLE 👇
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" 
# ==============================================================================

# --- AGENTI INTELLIGENTI ---
def agente_strategico(note_precedenti):
    """Analizza lo storico e dà consigli comportamentali"""
    if not note_precedenti: 
        return "ℹ️ COACH: Nessuno storico recente. Raccogli info.", "background: rgba(51, 65, 85, 0.5); border: 1px solid #64748b;"
    
    txt = str(note_precedenti).lower()
    
    if any(x in txt for x in ['arrabbiato', 'reclamo', 'ritardo', 'problema', 'rotto']):
        return "🛡️ COACH: Cliente a rischio. Empatia massima. Risolvi prima di vendere.", "background: rgba(153, 27, 27, 0.6); border: 1px solid #f87171;"
    if any(x in txt for x in ['prezzo', 'costoso', 'sconto', 'caro']):
        return "💎 COACH: Difendi il valore. Non svendere. Parla di qualità e servizio.", "background: rgba(146, 64, 14, 0.6); border: 1px solid #fb923c;"
    if any(x in txt for x in ['interessato', 'preventivo', 'forse']):
        return "🎯 COACH: È caldo! Oggi devi chiudere. Porta il contratto.", "background: rgba(22, 101, 52, 0.6); border: 1px solid #4ade80;"
    
    return f"ℹ️ MEMO: {note_precedenti[:50]}...", "background: rgba(51, 65, 85, 0.6); border: 1px solid #94a3b8;"

def agente_meteo_territoriale():
    try:
        lats, lons = f"{COORDS['Chianti'][0]},{COORDS['Firenze'][0]},{COORDS['Arezzo'][0]}", f"{COORDS['Chianti'][1]},{COORDS['Firenze'][1]},{COORDS['Arezzo'][1]}"
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1"
        res = requests.get(url).json()
        res = res if isinstance(res, list) else [res]
        
        bad_weather = False
        details = []
        for i, z in enumerate(res):
            nome = ["Chianti", "Firenze", "Arezzo"][i]
            # Ore lavorative 09-18
            rain = max(z['hourly']['precipitation_probability'][9:18])
            temp = sum(z['hourly']['temperature_2m'][9:18]) / 9
            details.append(f"{nome}: {int(temp)}°C/Pioggia {rain}%")
            if rain > 30 or temp < 8: bad_weather = True
            
        msg = f"AUTO 🚗 (Meteo Incerto: {', '.join(details)})" if bad_weather else "ZONTES 350 🛵 (Via Libera!)"
        style = "background: linear-gradient(90deg, #b91c1c, #ef4444);" if bad_weather else "background: linear-gradient(90deg, #15803d, #22c55e);"
        return msg, style
    except: return "METEO N/D", "background: #64748b;"

# --- FUNZIONI CORE ---
def get_real_travel_time(origin_coords, dest_coords):
    if not API_KEY: 
        dist = geodesic(origin_coords, dest_coords).km
        return int(((dist * 1.5) / 40) * 60)
    try:
        url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin_coords[0]},{origin_coords[1]}&destinations={dest_coords[0]},{dest_coords[1]}&departure_time=now&mode=driving&key={API_KEY}"
        res = requests.get(url).json()
        if res['status'] == 'OK' and res['rows'][0]['elements'][0]['status'] == 'OK':
            seconds = res['rows'][0]['elements'][0]['duration_in_traffic']['value']
            return int(seconds / 60)
    except: pass
    dist = geodesic(origin_coords, dest_coords).km
    return int(((dist * 1.5) / 45) * 60)

def get_google_data(query_list):
    if not API_KEY: return None
    for q in query_list:
        try:
            res = requests.get(f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={urllib.parse.quote(q)}&key={API_KEY}").json()
            if res.get('results'):
                r = res['results'][0]
                pid = r['place_id']
                det = requests.get(f"https://maps.googleapis.com/maps/api/place/details/json?place_id={pid}&fields=opening_hours,formatted_phone_number&key={API_KEY}").json()
                return {
                    "coords": (r['geometry']['location']['lat'], r['geometry']['location']['lng']),
                    "tel": det.get('result', {}).get('formatted_phone_number', ''),
                    "periods": det.get('result', {}).get('opening_hours', {}).get('periods', []),
                    "found": True
                }
        except: continue
    return None

@st.cache_resource
def connect_db():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_key(ID_DEL_FOGLIO)
        return sh.get_worksheet(0), sh.worksheet("LOG_AI") if "LOG_AI" in [w.title for w in sh.worksheets()] else None
    except: return None, None

def get_ai_duration(ws_log, cliente):
    if not ws_log: return 20, False
    try:
        df = pd.DataFrame(ws_log.get_all_records())
        if not df.empty:
            hist = df[df['CLIENTE'] == cliente]
            if not hist.empty: return int(hist['DURATA_MIN'].mean()), True
    except: pass
    return 20, False

def log_visit(ws_log, cliente, durata):
    if ws_log:
        if not ws_log.get_all_values(): ws_log.append_row(["CLIENTE", "DATA", "ORA", "DURATA_MIN"])
        now = datetime.now(TZ_ITALY)
        ws_log.append_row([cliente, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), durata])

# --- INTERFACCIA ---
ws, ws_ai = connect_db()

if ws:
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=[h.strip().upper() for h in data[0]])
    
    # Rilevamento Colonne
    c_nom = next(c for c in df.columns if "CLIENTE" in c)
    c_ind = next(c for c in df.columns if "INDIRIZZO" in c or "VIA" in c)
    c_com = next(c for c in df.columns if "COMUNE" in c)
    c_cap = next((c for c in df.columns if "CAP" in c), "CAP")
    c_vis = next(c for c in df.columns if "VISITATO" in c)
    c_tel = next((c for c in df.columns if "TELEFONO" in c), "TELEFONO")
    c_canv = next((c for c in df.columns if "CANVASS" in c or "PROMO" in c), None)
    
    if c_cap in df.columns: df[c_cap] = df[c_cap].astype(str).str.replace('.0','').str.zfill(5)

    with st.sidebar:
        st.title("⚙️ Filtri")
        sel_zona = st.multiselect("Zona", sorted(df[c_com].unique()))
        sel_cap = st.multiselect("CAP", sorted(df[c_cap].unique()) if c_cap in df.columns else [])
        st.divider()

    st.markdown("### 🚀 Brightstar AI Real-Time")
    
    msg, style = agente_meteo_territoriale()
    st.markdown(f"<div class='meteo-card' style='{style}'>{msg}</div>", unsafe_allow_html=True)

    if st.button("CALCOLA GIRO (ORARIO ITALIA)", type="primary", use_container_width=True):
        mask = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
        if sel_zona: mask &= df[c_com].isin(sel_zona)

# --- DIAGNOSTICA AVANZATA ---
    if st.button("CALCOLA GIRO (MODALITÀ DIAGNOSI)", type="primary", use_container_width=True):
        st.write("--- INIZIO DIAGNOSI ---")
        
        # 1. CONTROLLO COLONNE RILEVATE
        st.write(f"🧐 **Colonne Rilevate:** Cliente='{c_nom}', Indirizzo='{c_ind}', Comune='{c_com}', Visitato='{c_vis}'")
        
        # 2. CONTROLLO FILTRI
        mask = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
        righe_non_visitate = len(df[mask])
        st.write(f"📊 Clienti totali nel foglio: {len(df)}")
        st.write(f"❌ Clienti NON visitati: {righe_non_visitate} (Se è 0, controlla la colonna VISITATO)")

        if sel_zona: 
            mask &= df[c_com].isin(sel_zona)
            st.write(f"📍 Dopo filtro Zona ({sel_zona}): rimasti {len(df[mask])} clienti")
        
        if sel_cap: 
            mask &= df[c_cap].isin(sel_cap)
            st.write(f"📮 Dopo filtro CAP: rimasti {len(df[mask])} clienti")
            
        raw = df[mask].to_dict('records')
        
        if not raw:
            st.error("⛔ STOP: Nessun cliente rimasto dopo i filtri! Controlla i nomi dei Comuni nel foglio.")
        else:
            st.success(f"✅ Trovati {len(raw)} clienti potenziali. Inizio interrogazione Google Maps...")
            
            with st.spinner("⏳ Analisi Traffico, Strategia e Canvass..."):
                rotta = []
                now = datetime.now(TZ_ITALY)
                if now.hour >= 19 or now.hour < 6:
                    start_t = now.replace(hour=7, minute=30, second=0)
                    if now.hour >= 19: start_t += timedelta(days=1)
                    st.info(f"🌙 Orario serale/notturno. Pianifico per domani mattina: {start_t.strftime('%H:%M')}")
                else: 
                    start_t = now
                    st.info(f"☀️ Pianifico partendo da ADESSO: {start_t.strftime('%H:%M')}")
                    
                limit = start_t.replace(hour=19, minute=30)
                curr_t = start_t
                curr_loc = SEDE_COORDS
                pool = raw.copy()

                clienti_processati = 0
                clienti_con_gps = 0

                while pool and curr_t < limit:
                    best = None
                    best_score = float('inf')
                    
                    for p in pool:
                        if 'g_data' not in p:
                            clienti_processati += 1
                            # Debug specifico Google
                            q_list = [f"{p[c_ind]}, {p[c_com]}, Italy", f"{p[c_nom]}, {p[c_com]}"]
                            p['g_data'] = get_google_data(q_list)
                            
                            if not p['g_data']: 
                                st.warning(f"⚠️ Google non trova: {p[c_nom]} ({p[c_ind]})")
                                p['g_data'] = {'coords': None, 'found': False, 'periods': []}
                            else:
                                if not p.get('gps_logged'): # Evita spam
                                    clienti_con_gps += 1
                                    p['gps_logged'] = True

                        if not p['g_data']['found']: continue

                        dist_air = geodesic(curr_loc, p['g_data']['coords']).km
                        est_min = (dist_air * 1.5 / 40) * 60 
                        est_arr = curr_t + timedelta(minutes=est_min)
                        
                        if est_arr > limit: continue
                        
                        score = dist_air
                        if c_canv and p.get(c_canv) and str(p[c_canv]).strip():
                            score -= 3 
                        if score < best_score:
                            best_score = score
                            best = p
                    
                    if best:
                        real_mins = get_real_travel_time(curr_loc, best['g_data']['coords'])
                        arrival_real = curr_t + timedelta(minutes=real_mins)
                        
                        if arrival_real > limit:
                            st.write(f"⏰ {best[c_nom]} scartato: arrivo previsto {arrival_real.strftime('%H:%M')} (oltre 19:30)")
                            pool.remove(best)
                            continue

                        dur_visita, learned = get_ai_duration(ws_ai, best[c_nom])
                        best['arr'] = arrival_real
                        best['travel_time'] = real_mins
                        best['duration'] = dur_visita
                        best['learned'] = learned
                        
                        rotta.append(best)
                        curr_t = arrival_real + timedelta(minutes=dur_visita)
                        curr_loc = best['g_data']['coords']
                        pool.remove(best)
                    else: 
                        break
                
                st.write(f"🏁 Elaborazione finita. GPS Trovati: {clienti_con_gps}/{len(raw)}")
                
                if not rotta:
                    st.error("⛔ Nessuna rotta calcolata. Possibili cause: Indirizzi sbagliati o Orario > 19:30.")
                
                st.session_state.master_route = rotta
                st.rerun()

    # --- (Il resto del codice per visualizzare le carte rimane uguale) ---
    if 'master_route' in st.session_state and st.session_state.master_route:
        # ... (Qui c'è il codice che mostra le schede clienti che hai già) ...
        # Assicurati di non cancellare la parte che disegna le carte!
        # Se l'hai cancellata per sbaglio, rimettila dal codice precedente.

