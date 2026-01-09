import streamlit as st
import pandas as pd
import numpy as np
from geopy.distance import geodesic
from datetime import datetime, timedelta
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar AI PRO", page_icon="🧠", layout="wide")

st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); font-family: 'Segoe UI', sans-serif; color: #e2e8f0; }
    .meteo-card { padding: 15px; border-radius: 12px; color: white; margin-bottom: 25px; text-align: center; font-weight: bold; border: 1px solid rgba(255,255,255,0.2); }
    .client-card { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 20px; margin-bottom: 15px; }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .client-name { font-size: 1.2rem; font-weight: 700; color: #f8fafc; }
    .arrival-time { background: linear-gradient(90deg, #3b82f6, #2563eb); color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; }
    .info-row { display: flex; gap: 15px; color: #94a3b8; font-size: 0.9rem; margin-bottom: 5px; }
    .highlight { color: #38bdf8; font-weight: 600; }
    .real-traffic { color: #f59e0b; font-size: 0.8rem; font-style: italic; }
    </style>
    """, unsafe_allow_html=True)

# --- DATI ---
COORDS = { "Chianti": (43.661888, 11.305728), "Firenze": (43.7696, 11.2558), "Arezzo": (43.4631, 11.8781) }
SEDE_COORDS = COORDS["Chianti"]
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" # <--- RIMETTI IL TUO ID

# --- 2. FUNZIONI CRITICHE (TRAFFICO REALE) ---
def get_real_travel_time(origin_coords, dest_coords):
    """
    Chiede a Google Maps il tempo di guida REALE in questo momento.
    Ritorna: minuti (int)
    """
    if not API_KEY: 
        # Fallback matematico migliorato per la montagna (Fattore 1.5x)
        dist = geodesic(origin_coords, dest_coords).km
        return int(((dist * 1.5) / 40) * 60) # Stima 40km/h su strade curve
        
    try:
        url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin_coords[0]},{origin_coords[1]}&destinations={dest_coords[0]},{dest_coords[1]}&departure_time=now&mode=driving&key={API_KEY}"
        res = requests.get(url).json()
        if res['status'] == 'OK':
            elem = res['rows'][0]['elements'][0]
            if elem['status'] == 'OK':
                # duration_in_traffic è il tempo con il traffico attuale
                seconds = elem.get('duration_in_traffic', elem.get('duration'))['value']
                return int(seconds / 60) # Ritorna minuti
    except:
        pass
    
    # Se fallisce API, fallback matematico
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
            rain = max(z['hourly']['precipitation_probability'][9:18])
            temp = sum(z['hourly']['temperature_2m'][9:18]) / 9
            details.append(f"{nome}: {int(temp)}°C/Pioggia {rain}%")
            if rain > 30 or temp < 10: bad_weather = True
            
        msg = f"AUTO 🚗 (Meteo Incerto: {', '.join(details)})" if bad_weather else "ZONTES 350 🛵 (Via Libera!)"
        style = "background: linear-gradient(90deg, #b91c1c, #ef4444);" if bad_weather else "background: linear-gradient(90deg, #15803d, #22c55e);"
        return msg, style
    except: return "METEO N/D", "background: #64748b;"

# --- 3. CONNESSIONE DB ---
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
        if df.empty: return 20, False
        hist = df[df['CLIENTE'] == cliente]
        if not hist.empty: return int(hist['DURATA_MIN'].mean()), True
    except: pass
    return 20, False

def log_visit(ws_log, cliente, durata):
    if ws_log:
        if not ws_log.get_all_values(): ws_log.append_row(["CLIENTE", "DATA", "ORA", "DURATA_MIN"])
        now = datetime.now()
        ws_log.append_row([cliente, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), durata])

# --- 4. INTERFACCIA ---
ws, ws_ai = connect_db()

if ws:
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=[h.strip().upper() for h in data[0]])
    c_nom = next(c for c in df.columns if "CLIENTE" in c)
    c_ind = next(c for c in df.columns if "INDIRIZZO" in c or "VIA" in c)
    c_com = next(c for c in df.columns if "COMUNE" in c)
    c_cap = next((c for c in df.columns if "CAP" in c), "CAP")
    c_vis = next(c for c in df.columns if "VISITATO" in c)
    c_tel = next((c for c in df.columns if "TELEFONO" in c), "TELEFONO")
    if c_cap in df.columns: df[c_cap] = df[c_cap].astype(str).str.replace('.0','').str.zfill(5)

    with st.sidebar:
        st.title("⚙️ Filtri")
        sel_zona = st.multiselect("Zona", sorted(df[c_com].unique()))
        sel_cap = st.multiselect("CAP", sorted(df[c_cap].unique()) if c_cap in df.columns else [])

    st.markdown("### 🚀 Brightstar AI Real-Time")
    
    msg, style = agente_meteo_territoriale()
    st.markdown(f"<div class='meteo-card' style='{style}'>{msg}</div>", unsafe_allow_html=True)

    if st.button("CALCOLA GIRO (TEMPI REALI)", type="primary", use_container_width=True):
        mask = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
        if sel_zona: mask &= df[c_com].isin(sel_zona)
        if sel_cap: mask &= df[c_cap].isin(sel_cap)
        
        raw = df[mask].to_dict('records')
        
        if not raw: st.warning("Nessun cliente.")
        else:
            with st.spinner("⏳ Calcolo traffico reale con Google Matrix..."):
                rotta = []
                now = datetime.now()
                # Se è sera o mattina presto, simula partenza 07:30 domani
                start_t = now if (7 <= now.hour < 19) else now.replace(hour=7, minute=30) + timedelta(days=(1 if now.hour>=19 else 0))
                limit = start_t.replace(hour=19, minute=30)
                
                curr_t = start_t
                curr_loc = SEDE_COORDS
                pool = raw.copy()

                while pool and curr_t < limit:
                    best = None
                    best_score = float('inf')
                    
                    for p in pool:
                        # Recupero dati GPS
                        if 'g_data' not in p:
                            p['g_data'] = get_google_data([f"{p[c_ind]}, {p[c_com]}, Italy", f"{p[c_nom]}, {p[c_com]}"])
                            if not p['g_data']: 
                                p['g_data'] = {'coords': None, 'found': False, 'periods': []}

                        # SE NON TROVA COORDINATE, SALTA IL CLIENTE (Così non mette 0 min)
                        if not p['g_data']['found']:
                            continue

                        # 1. Stima veloce per ordinamento (Matematica con fattore montagna)
                        dist_air = geodesic(curr_loc, p['g_data']['coords']).km
                        est_min = (dist_air * 1.5 / 40) * 60 
                        est_arr = curr_t + timedelta(minutes=est_min)
                        
                        if est_arr > limit: continue
                        
                        # Score: Priorità vicinanza geografica
                        score = dist_air
                        if score < best_score:
                            best_score = score
                            best = p
                    
                    if best:
                        # 2. CALCOLO REALE SOLO SUL VINCITORE (Per risparmiare API e tempo)
                        # Qui chiediamo a Google: "Quanto ci vuole davvero ORA?"
                        real_mins = get_real_travel_time(curr_loc, best['g_data']['coords'])
                        
                        arrival_real = curr_t + timedelta(minutes=real_mins)
                        
                        # Se anche col tempo reale sforiamo le 19:30, scartiamo e riproviamo
                        if arrival_real > limit:
                            pool.remove(best)
                            continue

                        # Recupero durata visita AI
                        dur_visita, learned = get_ai_duration(ws_ai, best[c_nom])
                        
                        best['arr'] = arrival_real
                        best['travel_time'] = real_mins
                        best['duration'] = dur_visita
                        best['learned'] = learned
                        best['is_open'] = True # Semplificato per focus su tempi guida
                        
                        rotta.append(best)
                        curr_t = arrival_real + timedelta(minutes=dur_visita)
                        curr_loc = best['g_data']['coords']
                        pool.remove(best)
                    else:
                        break # Nessun altro cliente raggiungibile
                
                st.session_state.master_route = rotta
                st.rerun()

    if 'master_route' in st.session_state:
        route = st.session_state.master_route
        end = route[-1]['arr'].strftime("%H:%M") if route else "--:--"
        st.caption(f"🏁 Rientro previsto: {end}")
        
        for i, p in enumerate(route):
            ai_lbl = "AI" if p.get('learned') else "Std"
            tel = p.get('g_data', {}).get('tel') or p.get(c_tel) or ''
            
            st.markdown(f"""
            <div class="client-card">
                <div class="card-header">
                    <span class="client-name">{i+1}. {p[c_nom]}</span>
                    <div class="arrival-time">{p['arr'].strftime('%H:%M')}</div>
                </div>
                <div class="info-row">
                    <span>📍 {p[c_ind]}, {p[c_com]}</span>
                    <span class="real-traffic">🚗 Guida reale: {p['travel_time']} min</span>
                </div>
                <div class="info-row">
                    <span class="ai-badge">Visita {ai_lbl}: {p['duration']} min</span>
                    <span class="highlight">{tel}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                coords = p['g_data']['coords']
                lnk = f"https://www.google.com/maps/dir/?api=1&destination={coords[0]},{coords[1]}&travelmode=driving"
                st.link_button("🚙 NAVIGA", lnk, use_container_width=True)
            with c2:
                if tel: st.link_button("📞 CHIAMA", f"tel:{tel}", use_container_width=True)
            with c3:
                if st.button("✅ FATTO", key=f"d_{i}", use_container_width=True):
                    try:
                        cell = ws.find(p[c_nom])
                        ws.update_cell(cell.row, list(df.columns).index(c_vis)+1, "SI")
                        log_visit(ws_ai, p[c_nom], p['duration'])
                        st.session_state.master_route.pop(i)
                        st.rerun()
                    except: st.error("Errore DB")
