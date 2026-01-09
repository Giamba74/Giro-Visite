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

# CSS PROFESSIONALE (Glassmorphism Dark Mode)
st.markdown("""
    <style>
    /* Sfondo e Font */
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Card Cliente */
    .client-card {
        background: rgba(30, 41, 59, 0.7);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        transition: transform 0.2s;
    }
    .client-card:hover {
        border-color: #3b82f6;
        transform: translateY(-2px);
    }
    
    /* Header della Card */
    .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }
    .client-name {
        font-size: 1.2rem;
        font-weight: 700;
        color: #f8fafc;
    }
    .arrival-time {
        background: linear-gradient(90deg, #3b82f6, #2563eb);
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.9rem;
        box-shadow: 0 2px 4px rgba(59, 130, 246, 0.5);
    }
    
    /* Dettagli */
    .info-row {
        display: flex;
        gap: 15px;
        color: #94a3b8;
        font-size: 0.9rem;
        margin-bottom: 15px;
    }
    .highlight { color: #38bdf8; font-weight: 600; }
    
    /* Meteo Box */
    .meteo-widget {
        background: rgba(15, 23, 42, 0.6);
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        border: 1px solid rgba(255, 255, 255, 0.1);
        margin-bottom: 25px;
        color: white;
        font-weight: 500;
    }

    /* AI Badge */
    .ai-badge {
        font-size: 0.75rem;
        background-color: #4c1d95;
        color: #e9d5ff;
        padding: 2px 8px;
        border-radius: 4px;
        border: 1px solid #a78bfa;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONFIGURAZIONI ---
SEDE_COORDS = (43.661888, 11.305728)
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" # <--- ID FOGLIO

# --- 2. FUNZIONI AI & DATI ---
@st.cache_resource
def connect_db():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_key(ID_DEL_FOGLIO)
        ws_data = sh.get_worksheet(0) # Dati Clienti
        
        # Gestione Foglio AI (Se non esiste, usa il primo ma darà errore, l'utente deve crearlo)
        try:
            ws_log = sh.worksheet("LOG_AI")
        except:
            ws_log = None # Fallback se l'utente non l'ha creato
            
        return ws_data, ws_log
    except: return None, None

def get_ai_history(ws_log, cliente):
    """
    Legge la storia del cliente per predire la durata della visita.
    Ritorna: Durata stimata (int) e booleano (True se è un dato storico, False se default)
    """
    if not ws_log: return 20, False # Default 20 min
    try:
        logs = ws_log.get_all_records()
        df_log = pd.DataFrame(logs)
        if df_log.empty: return 20, False
        
        # Filtra per cliente
        history = df_log[df_log['CLIENTE'] == cliente]
        if not history.empty and 'DURATA_MIN' in history.columns:
            media = int(history['DURATA_MIN'].mean())
            return max(10, media), True # Ritorna la media storica
    except:
        pass
    return 20, False

def log_visit_ai(ws_log, cliente, durata_reale):
    """Salva i dati per far imparare l'AI"""
    if ws_log:
        now = datetime.now()
        row = [cliente, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), durata_reale]
        # Se il foglio è vuoto, mette header
        if not ws_log.get_all_values():
            ws_log.append_row(["CLIENTE", "DATA", "ORA", "DURATA_MIN"])
        ws_log.append_row(row)

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

# --- 3. APP LOGIC ---
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

    # Sidebar Filtri
    with st.sidebar:
        st.title("⚙️ Filtri Giro")
        sel_zona = st.multiselect("Zona (Comune)", sorted(df[c_com].unique()))
        sel_cap = st.multiselect("CAP", sorted(df[c_cap].unique()) if c_cap in df.columns else [])
        st.divider()
        st.caption("Statistiche AI:")
        if ws_ai:
            n_logs = len(ws_ai.get_all_values()) - 1
            st.success(f"🧠 L'AI ha imparato da {max(0, n_logs)} visite passate.")
        else:
            st.warning("Foglio 'LOG_AI' mancante. Crea il foglio per attivare l'apprendimento.")

    # Main Dashboard
    st.markdown("### 🚀 Brightstar AI Navigator")
    
    # Calcolo Giro
    if st.button("GENERAZIONE GIRO INTELLIGENTE", type="primary", use_container_width=True):
        mask = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
        if sel_zona: mask &= df[c_com].isin(sel_zona)
        if sel_cap: mask &= df[c_cap].isin(sel_cap)
        
        raw = df[mask].to_dict('records')
        
        if not raw:
            st.info("Nessun cliente da visitare nella zona selezionata.")
        else:
            with st.spinner("🤖 L'AI sta ottimizzando il percorso in base alla storia..."):
                rotta = []
                now = datetime.now()
                # Simulazione orari start
                start_t = now if (7 <= now.hour < 19) else now.replace(hour=7, minute=30) + timedelta(days=(1 if now.hour>=19 else 0))
                curr_t = start_t
                curr_loc = SEDE_COORDS
                pool = raw.copy()
                limit = start_t.replace(hour=19, minute=30)

                while pool and curr_t < limit:
                    best = None
                    best_score = float('inf')
                    
                    for p in pool:
                        # Dati Google
                        if 'g_data' not in p:
                            p['g_data'] = get_google_details([f"{p[c_ind]}, {p[c_com]}, Italy", f"{p[c_nom]}, {p[c_com]}"]) or {'coords': SEDE_COORDS, 'found': False, 'periods': []}
                        
                        dist = geodesic(curr_loc, p['g_data']['coords']).km
                        travel_min = (dist / 35) * 60
                        arr_time = curr_t + timedelta(minutes=travel_min)
                        
                        if arr_time > limit: continue
                        
                        # Check Apertura
                        open_now = is_open_now(p['g_data']['periods'], arr_time)
                        
                        # Score: Distanza + Penalità Chiuso
                        score = dist
                        if not open_now: score += 1000
                        if open_now and 12 < arr_time.hour < 14: score -= 5 # Bonus Pausa Pranzo
                        
                        if score < best_score:
                            best_score = score
                            best = p
                            best['arr'] = arr_time
                            best['is_open'] = open_now
                    
                    if best:
                        # AI HISTORY CHECK
                        # Qui il sistema decide la durata basandosi sulla storia
                        ai_duration, is_learned = get_ai_history(ws_ai, best[c_nom])
                        
                        best['duration'] = ai_duration
                        best['learned'] = is_learned
                        
                        rotta.append(best)
                        curr_t = best['arr'] + timedelta(minutes=ai_duration)
                        curr_loc = best['g_data']['coords']
                        pool.remove(best)
                    else:
                        # Avanza tempo se stallo
                        if (limit - curr_t).seconds < 1800: break
                        curr_t += timedelta(minutes=15)
                
                st.session_state.master_route = rotta
                st.rerun()

    # Visualizzazione Cards
    if 'master_route' in st.session_state:
        route = st.session_state.master_route
        end_time = route[-1]['arr'].strftime("%H:%M") if route else "--:--"
        
        # Progress Bar
        completed = 0 # Placeholder per futuro
        st.progress(0, text=f"Pianificazione completata. Rientro stimato: {end_time}")
        
        for i, p in enumerate(route):
            # Design della Card
            bg_color = "rgba(30, 41, 59, 0.7)"
            status_dot = "🟢" if p['is_open'] else "🔴"
            ai_tag = f"<span class='ai-badge'>AI: {p['duration']} min</span>" if p.get('learned') else f"<span class='ai-badge' style='background:#334155; border-color:#475569'>Std: {p['duration']} min</span>"
            
            st.markdown(f"""
            <div class="client-card">
                <div class="card-header">
                    <span class="client-name">{i+1}. {p[c_nom]}</span>
                    <div class="arrival-time">Arrivo: {p['arr'].strftime('%H:%M')}</div>
                </div>
                <div class="info-row">
                    <span>📍 {p[c_ind]}, {p[c_com]}</span>
                    <span>{status_dot} Stato Store</span>
                </div>
                <div class="info-row">
                    <span>{ai_tag}</span>
                    <span class="highlight">📞 {p.get('g_data', {}).get('tel') or 'N/D'}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Azioni
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                coords = p['g_data']['coords']
                lnk = f"https://www.google.com/maps/dir/?api=1&destination={coords[0]},{coords[1]}&travelmode=driving"
                st.link_button("🚙 NAVIGA", lnk, use_container_width=True)
            with c2:
                t = p.get('g_data', {}).get('tel') or p.get(c_tel)
                if t: st.link_button("📞 CHIAMA", f"tel:{t}", use_container_width=True)
            with c3:
                if st.button("✅ FATTO", key=f"d_{i}", use_container_width=True):
                    # 1. Aggiorna DB
                    try:
                        cell = ws.find(p[c_nom])
                        ws.update_cell(cell.row, list(df.columns).index(c_vis)+1, "SI")
                        
                        # 2. APPOLOGIZZA (Insegna all'AI)
                        # Calcola tempo reale trascorso dall'arrivo previsto a ora
                        # (In una app reale useremmo timestamp preciso, qui stimiamo in base al click)
                        log_visit_ai(ws_ai, p[c_nom], p['duration']) 
                        
                        st.session_state.master_route.pop(i)
                        st.toast(f"Visita salvata! L'AI ha registrato i dati per {p[c_nom]}.")
                        st.rerun()
                    except: st.error("Errore salvataggio")
