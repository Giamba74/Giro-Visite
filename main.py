import streamlit as st
import pandas as pd
import numpy as np
from geopy.distance import geodesic
from datetime import datetime, timedelta
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. DESIGN SYSTEM & CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar AI PRO", page_icon="🧠", layout="wide")

st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        color: #e2e8f0;
    }
    .meteo-card {
        padding: 15px; border-radius: 12px; color: white; margin-bottom: 25px;
        text-align: center; font-weight: bold; box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        border: 1px solid rgba(255,255,255,0.2);
    }
    .client-card {
        background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px;
        padding: 20px; margin-bottom: 15px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .client-name { font-size: 1.2rem; font-weight: 700; color: #f8fafc; }
    .arrival-time { background: linear-gradient(90deg, #3b82f6, #2563eb); color: white; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; }
    .info-row { display: flex; gap: 15px; color: #94a3b8; font-size: 0.9rem; margin-bottom: 15px; }
    .highlight { color: #38bdf8; font-weight: 600; }
    .ai-badge { font-size: 0.75rem; background-color: #4c1d95; color: #e9d5ff; padding: 2px 8px; border-radius: 4px; border: 1px solid #a78bfa; }
    </style>
    """, unsafe_allow_html=True)

# --- COORDINATE STRATEGICHE (Triangolazione) ---
COORDS = {
    "Chianti": (43.661888, 11.305728),
    "Firenze": (43.7696, 11.2558),
    "Arezzo": (43.4631, 11.8781)
}
SEDE_COORDS = COORDS["Chianti"]
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" # <--- RIMETTI IL TUO ID

# --- 2. AGENTE METEO TERRITORIALE ---
def agente_meteo_territoriale():
    try:
        # Richiesta Multipla: Chianti, Firenze, Arezzo
        lats = f"{COORDS['Chianti'][0]},{COORDS['Firenze'][0]},{COORDS['Arezzo'][0]}"
        lons = f"{COORDS['Chianti'][1]},{COORDS['Firenze'][1]},{COORDS['Arezzo'][1]}"
        
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1"
        res = requests.get(url).json()
        
        # Open-Meteo ritorna una lista di risultati se chiediamo più coordinate
        zone_results = res if isinstance(res, list) else [res]
        
        report_zone = []
        rischio_pioggia = False
        freddo_intenso = False
        
        nomi_zone = ["Chianti", "Firenze", "Arezzo"]
        
        for i, zona in enumerate(zone_results):
            # Analisi ore centrali (10:00 - 17:00)
            temp_h = zona['hourly']['temperature_2m'][10:17]
            rain_h = zona['hourly']['precipitation_probability'][10:17]
            
            avg_t = sum(temp_h) / len(temp_h)
            max_r = max(rain_h)
            
            report_zone.append(f"{nomi_zone[i]}: {int(avg_t)}°C (Pioggia {max_r}%)")
            
            if max_r > 30: rischio_pioggia = True # Se piove >30% in una zona, è rischio
            if avg_t < 10: freddo_intenso = True # Se fa <10°C in una zona, è rischio
            
        dettagli = " | ".join(report_zone)
        
        if rischio_pioggia or freddo_intenso:
            motivo = "Pioggia" if rischio_pioggia else "Freddo"
            msg = f"AUTO 🚗 (Allerta {motivo} su percorso) <br><span style='font-size:0.8em; font-weight:normal'>{dettagli}</span>"
            style = "background: linear-gradient(90deg, #b91c1c, #ef4444);" # Rosso scuro
        else:
            msg = f"ZONTES 350 🛵 (Via Libera su tutto il territorio) <br><span style='font-size:0.8em; font-weight:normal'>{dettagli}</span>"
            style = "background: linear-gradient(90deg, #15803d, #22c55e);" # Verde scuro
            
        return msg, style
    except:
        return "METEO OFF ☁️ (Radar non disponibile)", "background: #64748b;"

# --- 3. DATI & AI ---
@st.cache_resource
def connect_db():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_key(ID_DEL_FOGLIO)
        ws_data = sh.get_worksheet(0)
        try: ws_log = sh.worksheet("LOG_AI")
        except: ws_log = None 
        return ws_data, ws_log
    except: return None, None

def get_ai_history(ws_log, cliente):
    if not ws_log: return 20, False
    try:
        logs = ws_log.get_all_records()
        df_log = pd.DataFrame(logs)
        if df_log.empty: return 20, False
        history = df_log[df_log['CLIENTE'] == cliente]
        if not history.empty and 'DURATA_MIN' in history.columns:
            media = int(history['DURATA_MIN'].mean())
            return max(10, media), True
    except: pass
    return 20, False

def log_visit_ai(ws_log, cliente, durata_reale):
    if ws_log:
        now = datetime.now()
        if not ws_log.get_all_values(): ws_log.append_row(["CLIENTE", "DATA", "ORA", "DURATA_MIN"])
        ws_log.append_row([cliente, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), durata_reale])

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

def is_open_now(periods, time_obj):
    if not periods: return True
    g_day = (time_obj.weekday() + 1) % 7
    curr = int(time_obj.strftime("%H%M"))
    for p in periods:
        if p.get('open') and p['open']['day'] == g_day:
            cl = int(p['close']['time']) if p.get('close') else 2359
            if int(p['open']['time']) <= curr < cl: return True
    return False

# --- 4. APP DASHBOARD ---
ws, ws_ai = connect_db()

if ws:
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=[h.strip().upper() for h in data[0]])
    
    # Mapping Colonne
    c_nom = next(c for c in df.columns if "CLIENTE" in c)
    c_ind = next(c for c in df.columns if "INDIRIZZO" in c or "VIA" in c)
    c_com = next(c for c in df.columns if "COMUNE" in c)
    c_cap = next((c for c in df.columns if "CAP" in c), "CAP")
    c_vis = next(c for c in df.columns if "VISITATO" in c)
    c_tel = next((c for c in df.columns if "TELEFONO" in c), "TELEFONO")
    if c_cap in df.columns: df[c_cap] = df[c_cap].astype(str).str.replace('.0','').str.zfill(5)

    with st.sidebar:
        st.title("⚙️ Filtri Giro")
        sel_zona = st.multiselect("Zona (Comune)", sorted(df[c_com].unique()))
        sel_cap = st.multiselect("CAP", sorted(df[c_cap].unique()) if c_cap in df.columns else [])
        st.divider()
        if ws_ai: st.success(f"🧠 AI: {len(ws_ai.get_all_values())-1} dati storici.")
        else: st.warning("Foglio LOG_AI mancante.")

    st.markdown("### 🚀 Brightstar AI Navigator")

    # --- 1. RADAR METEO (FIRENZE-AREZZO-CHIANTI) ---
    meteo_msg, meteo_style = agente_meteo_territoriale()
    st.markdown(f"<div class='meteo-card' style='{meteo_style}'>{meteo_msg}</div>", unsafe_allow_html=True)
    
    # --- 2. GENERATORE GIRO ---
    if st.button("GENERAZIONE GIRO INTELLIGENTE", type="primary", use_container_width=True):
        mask = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
        if sel_zona: mask &= df[c_com].isin(sel_zona)
        if sel_cap: mask &= df[c_cap].isin(sel_cap)
        
        raw = df[mask].to_dict('records')
        
        if not raw:
            st.info("Nessun cliente da visitare.")
        else:
            with st.spinner("🤖 Scansione territorio, orari e meteo..."):
                rotta = []
                now = datetime.now()
                start_t = now if (7 <= now.hour < 19) else now.replace(hour=7, minute=30) + timedelta(days=(1 if now.hour>=19 else 0))
                curr_t = start_t
                curr_loc = SEDE_COORDS
                pool = raw.copy()
                limit = start_t.replace(hour=19, minute=30)

                while pool and curr_t < limit:
                    best = None
                    best_score = float('inf')
                    for p in pool:
                        if 'g_data' not in p:
                            q = [f"{p[c_ind]}, {p[c_com]}, Italy", f"{p[c_nom]}, {p[c_com]}"]
                            p['g_data'] = get_google_data(q) or {'coords': SEDE_COORDS, 'found': False, 'periods': []}
                        
                        dist = geodesic(curr_loc, p['g_data']['coords']).km
                        arr_time = curr_t + timedelta(minutes=(dist/35)*60)
                        if arr_time > limit: continue
                        
                        open_now = is_open_now(p['g_data']['periods'], arr_time)
                        score = dist
                        if not open_now: score += 1000
                        if open_now and 12 < arr_time.hour < 14: score -= 5
                        
                        if score < best_score:
                            best_score = score
                            best = p
                            best['arr'] = arr_time
                            best['is_open'] = open_now
                    
                    if best:
                        ai_dur, is_learned = get_ai_history(ws_ai, best[c_nom])
                        best['duration'] = ai_dur
                        best['learned'] = is_learned
                        rotta.append(best)
                        curr_t = best['arr'] + timedelta(minutes=ai_dur)
                        curr_loc = best['g_data']['coords']
                        pool.remove(best)
                    else:
                        if (limit - curr_t).seconds < 1800: break
                        curr_t += timedelta(minutes=15)
                
                st.session_state.master_route = rotta
                st.rerun()

    # --- 3. DASHBOARD CARDS ---
    if 'master_route' in st.session_state:
        route = st.session_state.master_route
        end = route[-1]['arr'].strftime("%H:%M") if route else "--:--"
        st.caption(f"🏁 Rientro stimato a Strada in Chianti: {end}")
        
        for i, p in enumerate(route):
            status = "🟢 APERTO" if p['is_open'] else "🔴 CHIUSO"
            ai_txt = f"AI: {p['duration']}min" if p.get('learned') else f"Std: {p['duration']}min"
            tel = p.get('g_data', {}).get('tel') or p.get(c_tel) or ''
            
            st.markdown(f"""
            <div class="client-card">
                <div class="card-header">
                    <span class="client-name">{i+1}. {p[c_nom]}</span>
                    <div class="arrival-time">{p['arr'].strftime('%H:%M')}</div>
                </div>
                <div class="info-row">
                    <span>📍 {p[c_ind]}, {p[c_com]}</span>
                    <span>{status}</span>
                </div>
                <div class="info-row">
                    <span class="ai-badge">{ai_txt}</span>
                    <span class="highlight">{tel if tel else 'No Tel'}</span>
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
                        log_visit_ai(ws_ai, p[c_nom], p['duration']) 
                        st.session_state.master_route.pop(i)
                        st.rerun()
                    except: st.error("Errore salvataggio")
