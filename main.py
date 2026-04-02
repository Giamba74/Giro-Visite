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
import json
import copy
import time

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar CRM PRO", page_icon="💎", layout="wide")
TZ_ITALY = pytz.timezone('Europe/Rome')

# --- 🎨 DESIGN E STILE CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    .stApp { 
        font-family: 'Inter', sans-serif; 
        background: radial-gradient(circle at top left, #1e293b 0%, #0f172a 100%); 
        color: #f1f5f9; 
    }
    
    .app-header {
        background: linear-gradient(90deg, #2563eb, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 800;
        text-align: center;
        margin-bottom: 30px;
        letter-spacing: -1px;
        text-shadow: 0px 4px 20px rgba(37, 99, 235, 0.2);
    }

    .client-card { 
        background: linear-gradient(145deg, rgba(30, 41, 59, 0.85), rgba(15, 23, 42, 0.9)); 
        backdrop-filter: blur(12px); 
        border: 1px solid rgba(255, 255, 255, 0.08); 
        border-radius: 20px; 
        padding: 24px; 
        margin-bottom: 16px; 
        box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5); 
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .client-card:hover {
        transform: translateY(-4px) scale(1.01);
        box-shadow: 0 20px 40px -10px rgba(59, 130, 246, 0.25);
        border-color: rgba(59, 130, 246, 0.3);
    }
    
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 12px; }
    .client-name { font-size: 1.45rem; font-weight: 800; color: #ffffff; letter-spacing: -0.5px; }
    .arrival-time { 
        background: linear-gradient(135deg, #3b82f6, #6366f1); 
        color: white; 
        padding: 6px 16px; 
        border-radius: 30px; 
        font-weight: 700; 
        font-size: 1.1rem;
        box-shadow: 0 4px 10px rgba(59, 130, 246, 0.3);
    }
    
    .strategy-box { 
        padding: 12px 16px; 
        border-radius: 10px; 
        margin-bottom: 18px; 
        font-size: 0.95em; 
        color: #e2e8f0; 
        border-left: 5px solid; 
        background: rgba(0,0,0,0.25); 
        font-weight: 500;
    }
    
    .info-row { display: flex; gap: 15px; color: #94a3b8; font-size: 0.95rem; margin-bottom: 8px; font-weight: 500;}
    .highlight { color: #38bdf8; font-weight: 700; }
    .real-traffic { color: #fbbf24; font-size: 0.85rem; font-style: normal; font-weight: 600; background: rgba(251, 191, 36, 0.1); padding: 2px 8px; border-radius: 6px;}
    .ai-badge { font-size: 0.8rem; background-color: rgba(51, 65, 85, 0.8); color: #cbd5e1; padding: 3px 10px; border-radius: 6px; font-weight: 600;}
    
    .badge { padding: 4px 10px; border-radius: 8px; margin-right: 8px; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; display: inline-block; margin-bottom: 5px;}
    .forced-badge { background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.4); }
    .prem-badge { background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); }
    .task-badge { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
    .done-badge { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
    
    div[data-testid="stButton"] button { 
        border-radius: 12px; 
        font-weight: 700; 
        transition: all 0.2s ease; 
        border: none !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding: 10px 0;
    }
    div[data-testid="stButton"] button:hover { transform: scale(1.03) translateY(-2px); box-shadow: 0 8px 15px rgba(0,0,0,0.3); }
    div[data-testid="stButton"] button:active { transform: scale(0.98); }
    
    .stCheckbox label { color: #f8fafc !important; font-weight: 600; }
    .stTextArea textarea { border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); background: rgba(15,23,42,0.6); color: white;}
    .stTextArea textarea:focus { border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59,130,246,0.2);}
    
    .streamlit-expanderHeader { background-color: rgba(255,255,255,0.03) !important; color: #94a3b8 !important; border-radius: 12px; font-weight: 600;}
    .streamlit-expanderHeader:hover { color: white !important; background-color: rgba(255,255,255,0.08) !important;}
    </style>
    """, unsafe_allow_html=True)

COORDS = { "Chianti": (43.661888, 11.305728), "Firenze": (43.7696, 11.2558), "Arezzo": (43.4631, 11.8781) }
SEDE_COORDS = COORDS["Chianti"]
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")

# ==============================================================================
# 👇 MODIFICA SOLO QUI SOTTO CON IL TUO ID FOGLIO GOOGLE 👇
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
        
        ws_mem = None
        if "MEMORIA_GIRO" in [w.title for w in sh.worksheets()]:
             ws_mem = sh.worksheet("MEMORIA_GIRO")
             # Inizializza Headers se vuoto
             if not ws_mem.acell("A1").value:
                 ws_mem.update_acell("A1", "DATA"); ws_mem.update_acell("B1", "JSON_DATA")
                 ws_mem.update_acell("D1", "DB_CLIENTE"); ws_mem.update_acell("E1", "DB_TASKS")
        
        return ws_main, ws_log, ws_mem
    except: return None, None, None

# --- SALVATAGGIO ---
def salva_giro_solo_rotta(sh_memoria, rotta_data):
    try:
        dati_export = copy.deepcopy(rotta_data)
        now_str = datetime.now(TZ_ITALY).strftime("%d-%m-%Y") 
        for p in dati_export:
            if isinstance(p.get('arr'), datetime): p['arr'] = p['arr'].strftime("%Y-%m-%d %H:%M:%S")
        
        json_dump = json.dumps(dati_export)
        sh_memoria.update_acell("A2", now_str)
        time.sleep(0.5)
        sh_memoria.update_acell("B2", json_dump)
        sh_memoria.update_acell("A2", now_str) 
    except: pass 

def carica_giro_da_foglio(sh_memoria):
    try:
        json_data = sh_memoria.acell("B2").value
        if json_data:
            rotta = json.loads(json_data)
            for p in rotta:
                if p.get('arr') and isinstance(p['arr'], str):
                    try: p['arr'] = datetime.strptime(p['arr'], "%Y-%m-%d %H:%M:%S")
                    except: p['arr'] = datetime.now(TZ_ITALY)
                if 'tasks_completed' not in p: p['tasks_completed'] = []
                if 'g_data' not in p: p['g_data'] = {'coords': None, 'found': False, 'tel': ''}
            return rotta
    except: pass
    return None

def resetta_solo_rotta(sh_memoria):
    try: sh_memoria.batch_clear(["A2:B2"])
    except: pass

def carica_storico_attivita(sh_memoria):
    try:
        raw = sh_memoria.get("D:E") 
        db_tasks = {}
        if not raw: return {}
        for row in raw[1:]: 
            if len(row) >= 2: db_tasks[row[0]] = json.loads(row[1])
        return db_tasks
    except: return {}

def aggiorna_attivita_cliente(sh_memoria, cliente, tasks_list):
    try:
        records = sh_memoria.get_all_values()
        row_idx = -1
        for i, row in enumerate(records):
            if len(row) > 3 and row[3] == cliente:
                row_idx = i + 1; break
        
        json_tasks = json.dumps(tasks_list)
        if row_idx != -1: sh_memoria.update_cell(row_idx, 5, json_tasks)
        else:
            col_d = sh_memoria.col_values(4)
            next_row = len(col_d) + 1
            sh_memoria.update_cell(next_row, 4, cliente)
            sh_memoria.update_cell(next_row, 5, json_tasks)
        st.toast(f"Dati Salvati: {cliente}", icon="💾")
    except: st.error("Errore Salvataggio Parziale")

def pulisci_attivita_cliente(sh_memoria, cliente):
    try:
        records = sh_memoria.get_all_values()
        row_idx = -1
        for i, row in enumerate(records):
            if len(row) > 3 and row[3] == cliente:
                row_idx = i + 1; break
        if row_idx != -1:
            sh_memoria.update_cell(row_idx, 4, "")
            sh_memoria.update_cell(row_idx, 5, "")
    except: pass

def get_real_travel_time(origin_coords, dest_coords):
    if not API_KEY or not origin_coords or not dest_coords: return 20 
    try:
        url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin_coords[0]},{origin_coords[1]}&destinations={dest_coords[0]},{dest_coords[1]}&departure_time=now&mode=driving&key={API_KEY}"
        res = requests.get(url, timeout=3).json() 
        if res['status'] == 'OK' and res['rows'][0]['elements'][0]['status'] == 'OK':
            seconds = res['rows'][0]['elements'][0]['duration_in_traffic']['value']
            return int(seconds / 60)
    except: pass
    try:
        dist = geodesic(origin_coords, dest_coords).km
        return int(((dist * 1.5) / 45) * 60)
    except: return 20

def get_google_data(query_list):
    if not API_KEY: return None
    time.sleep(0.1) 
    for q in query_list:
        try:
            res = requests.get(f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={urllib.parse.quote(q)}&key={API_KEY}", timeout=3).json()
            if res.get('results'):
                r = res['results'][0]
                pid = r['place_id']
                det = requests.get(f"https://maps.googleapis.com/maps/api/place/details/json?place_id={pid}&fields=opening_hours,formatted_phone_number&key={API_KEY}", timeout=3).json()
                return {"coords": (r['geometry']['location']['lat'], r['geometry']['location']['lng']), "tel": det.get('result', {}).get('formatted_phone_number', ''), "found": True}
        except: continue
    return None

def get_ai_duration(ws_log, cliente):
    if not ws_log: return 20, False
    try:
        df = pd.DataFrame(ws_log.get_all_records())
        if not df.empty:
            hist = df[df['CLIENTE'] == cliente]
            if not hist.empty: return int(hist['DURATA_MIN'].mean()), True
    except: pass
    return 20, False

def log_visit(ws_log, cliente, durata, note_extra=""):
    if ws_log:
        now = datetime.now(TZ_ITALY)
        ws_log.append_row([cliente, now.strftime("%d-%m-%Y"), now.strftime("%H:%M"), durata, note_extra])

def agente_strategico(note_precedenti):
    if not note_precedenti: return "ℹ️ COACH: Nessuno storico recente.", "border-left-color: #475569;"
    txt = str(note_precedenti).lower()
    if any(x in txt for x in ['arrabbiato', 'reclamo', 'ritardo']):
        return "🛡️ COACH: Cliente a rischio. Focus su ascolto attivo.", "border-left-color: #ef4444; background: rgba(239, 68, 68, 0.15);"
    if any(x in txt for x in ['prezzo', 'costoso', 'sconto']):
        return "💎 COACH: Difendi il valore. Prepara argomenti su ROI.", "border-left-color: #f59e0b; background: rgba(245, 158, 11, 0.15);"
    if any(x in txt for x in ['interessato', 'preventivo']):
        return "🎯 COACH: È caldo! Punta alla chiusura oggi.", "border-left-color: #10b981; background: rgba(16, 185, 129, 0.15);"
    return f"ℹ️ MEMO: {note_precedenti[:60]}...", "border-left-color: #3b82f6;"

# --- APP START ---
try: ws, ws_ai, ws_mem = connect_db()
except: ws, ws_ai, ws_mem = None, None, None

if ws is None: st.error("❌ Errore Connessione al Database di Google Sheets.")
else:
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=[h.strip().upper() for h in data[0]])
    c_nom = next(c for c in df.columns if "CLIENTE" in c)
    c_ind = next(c for c in df.columns if "INDIRIZZO" in c or "VIA" in c)
    c_com = next(c for c in df.columns if "COMUNE" in c)
    c_cap = next((c for c in df.columns if "CAP" in c), "CAP")
    c_vis = next(c for c in df.columns if "VISITATO" in c)
    
    if "TELEFONO" in df.columns: c_tel = "TELEFONO"
    else: c_tel = next((c for c in df.columns if "TELEFONO" in c or "CELL" in c or "TEL" in c), "TELEFONO")
    if c_tel in df.columns: df[c_tel] = df[c_tel].astype(str).replace('nan', '').replace('None', '')
    c_att = next((c for c in df.columns if "ATTIVIT" in c), None)
    c_canv = next((c for c in df.columns if "CANVASS" in c or "PROMO" in c), None)
    c_note_sto = next((c for c in df.columns if "STORICO" in c or "NOTE" in c), None)
    c_prem = next((c for c in df.columns if "PREMIUM" in c), None)
    if "CAP" in df.columns: df[c_cap] = df[c_cap].astype(str).str.replace('.0','').str.zfill(5)

    if 'master_route' not in st.session_state and ws_mem:
        rotta_salvata = carica_giro_da_foglio(ws_mem)
        if rotta_salvata:
            st.session_state.master_route = rotta_salvata
            st.toast("🔄 Giro Ripristinato", icon="💾")
    
    if 'db_tasks' not in st.session_state and ws_mem:
        st.session_state.db_tasks = carica_storico_attivita(ws_mem)

    # --- SIDEBAR DESIGN ---
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; color: #38bdf8; margin-bottom: 20px;'>⚙️ Settings</h2>", unsafe_allow_html=True)
        indirizzo_start = st.text_input("📍 Luogo di Partenza:", value="Chianti, Sede")
        
        # 👇 QUI HO MODIFICATO IL VALORE MASSIMO A 25 👇
        num_visite = st.slider("🚗 Clienti da visitare:", 1, 25, 8)
        
        st.divider()
        only_premium = st.toggle("💎 Mostra solo PREMIUM", value=False)
        sel_zona = st.multiselect("🌍 Filtra per Zona (Comuni)", sorted(df[c_com].unique()))
        sel_cap = st.multiselect("📮 Filtra per CAP", sorted(df[c_cap].unique()) if c_cap in df.columns else [])
        st.divider()
        st.markdown("#### ⭐ Forzature (Clienti VIP)")
        all_clients_list = sorted(df[c_nom].unique().tolist())
        sel_forced = st.multiselect("Seleziona manualmente i clienti:", all_clients_list)
        st.divider()
        if st.button("🗑️ SVUOTA MEMORIA GIRO", type="secondary"):
             if ws_mem: resetta_solo_rotta(ws_mem)
             if 'master_route' in st.session_state: del st.session_state.master_route
             st.rerun()

    # --- TITOLO PRINCIPALE ---
    st.markdown("<div class='app-header'>🚀 BRIGHTSTAR CRM PRO</div>", unsafe_allow_html=True)

    if st.button("🔄 CALCOLA NUOVO GIRO OTTIMIZZATO", type="primary", use_container_width=True):
        if not ws_mem: st.error("Errore: Manca il foglio MEMORIA_GIRO su Google Sheets!")
        else:
            start_coords = SEDE_COORDS
            if indirizzo_start:
                with st.spinner(f"🔍 Geolocalizzazione in corso per: {indirizzo_start}..."):
                    loc_data = get_google_data([indirizzo_start])
                    if loc_data and loc_data['found']: start_coords = loc_data['coords']
            
            # --- 1. FILTRI BASE ---
            mask_standard = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
            if sel_zona: mask_standard &= df[c_com].isin(sel_zona)
            if sel_cap: mask_standard &= df[c_cap].isin(sel_cap)
            if only_premium and c_prem: mask_standard &= df[c_prem].astype(str).str.upper().str.contains('SI', na=False)

            # --- 2. FILTRO ESCLUSIONE CG COMPLETATO ---
            clienti_cg_completato = []
            for nome_cliente, tasks_fatti in st.session_state.db_tasks.items():
                if any("CG" in str(t).upper() for t in tasks_fatti):
                    clienti_cg_completato.append(nome_cliente)
            
            mask_standard &= ~df[c_nom].isin(clienti_cg_completato)

            df_final = pd.concat([df[df[c_nom].isin(sel_forced)], df[mask_standard]]).drop_duplicates(subset=[c_nom])
            raw = df_final.to_dict('records')
            
            if not raw: st.warning("🎯 Nessun cliente trovato (Tutti completati o filtri troppo stringenti).")
            else:
                prog_bar = st.progress(0, text="Ricerca Indirizzi su Google Maps...")
                pool_pronta = []
                total = len(raw)
                
                for i, p in enumerate(raw):
                    prog_bar.progress((i + 1) / total, text=f"🔍 Mappatura: {p[c_nom]}")
                    if 'g_data' not in p:
                        res = get_google_data([f"{p[c_ind]}, {p[c_com]}, Italy", f"{p[c_nom]}, {p[c_com]}"])
                        if res and res['found']: p['g_data'] = res
                        else: p['g_data'] = {'coords': SEDE_COORDS, 'found': False, 'tel': ''}
                    pool_pronta.append(p)
                prog_bar.empty()

                with st.spinner("⏳ Intelligenza Artificiale: Creazione rotta ottimale..."):
                    rotta = []
                    now = datetime.now(TZ_ITALY)
                    curr_t = now.replace(hour=8, minute=0) if now.hour >= 19 else now
                    curr_loc = start_coords
                    pool = pool_pronta.copy()

                    while pool and len(rotta) < num_visite:
                        best = None; best_score = float('inf')
                        for p in pool:
                            c_target = p['g_data']['coords'] if p['g_data']['coords'] else curr_loc
                            try: dist_air = geodesic(curr_loc, c_target).km
                            except: dist_air = 9999 
                            
                            score = dist_air
                            
                            if p[c_nom] in sel_forced: score -= 100000000 
                            if c_prem and p.get(c_prem) == 'SI': score -= 2000 
                            if c_att and p.get(c_att) and str(p[c_att]).strip(): score -= 5000
                            
                            # --- LOGICA ANTI-CD DA MEMORIA GIRO ---
                            storico_tasks = st.session_state.db_tasks.get(p[c_nom], [])
                            if "CD" not in str(storico_tasks).upper():
                                score -= 50000000
                            
                            if score < best_score: best_score, best = score, p
                        
                        if best:
                            c_best = best['g_data']['coords'] if best['g_data']['coords'] else curr_loc
                            real_mins = get_real_travel_time(curr_loc, c_best)
                            arrival_real = curr_t + timedelta(minutes=real_mins)
                            
                            dur_visita, learned = get_ai_duration(ws_ai, best[c_nom])
                            best['arr'], best['travel_time'], best['duration'], best['learned'] = arrival_real, real_mins, dur_visita, learned
                            best['tasks_completed'] = st.session_state.db_tasks.get(best[c_nom], [])
                            
                            rotta.append(best)
                            curr_t = arrival_real + timedelta(minutes=dur_visita)
                            curr_loc = c_best
                            pool.remove(best)
                        else: break
                        
                    st.session_state.master_route = rotta
                    if ws_mem: salva_giro_solo_rotta(ws_mem, rotta)
                    st.rerun()

    if 'master_route' in st.session_state:
        route = st.session_state.master_route
        st.markdown(f"<p style='text-align:center; color:#94a3b8; font-weight:600;'>🏁 Orario Rientro Stimato: <span style='color:#38bdf8'>{route[-1]['arr'].strftime('%H:%M') if route else '--:--'}</span></p>", unsafe_allow_html=True)
        
        # --- GENERATORE TESTO PER OCCHIALI SMART (TELEPROMPTER) ---
        with st.expander("👓 ESPORTA HUD PER OCCHIALI SMART (Scorrimento con Anello)"):
            st.markdown("Copia il testo qui sotto e incollalo nello strumento **Teleprompter / Note** della tua app Even Hub.")
            
            hud_text = "📅 GIRO VISITE BRIGHTSTAR\n"
            hud_text += "-" * 25 + "\n\n"
            
            for idx_hud, p_hud in enumerate(route):
                ora_hud = p_hud['arr'].strftime('%H:%M')
                nome_hud = str(p_hud[c_nom]).upper()
                comune_hud = str(p_hud[c_com])
                
                tasks_hud = [t.strip() for t in str(p_hud.get(c_att, '')).split(',') if t.strip()]
                task_str = f"\n⚠️ {', '.join(tasks_hud)}" if tasks_hud else ""
                
                hud_text += f"[{ora_hud}] {idx_hud+1}. {nome_hud}\n📍 {comune_hud}{task_str}\n\n"
            
            st.code(hud_text, language="markdown")
            
        st.markdown("<br>", unsafe_allow_html=True) 
        
        for i, p in enumerate(route):
            ai_lbl = "AI" if p.get('learned') else "Std"
            tel_excel = str(p.get(c_tel, '')).strip()
            tel_google = p['g_data'].get('tel', '')
            tel_display = tel_excel if tel_excel and len(tel_excel) > 5 else tel_google

            ora_str = p['arr'].strftime('%H:%M')
            note_old = p.get(c_note_sto, '') if c_note_sto else ''
            msg_coach, style_coach = agente_strategico(note_old)
            
            forced_html = "<span class='badge forced-badge'>⭐ VIP</span>" if p[c_nom] in sel_forced else ""
            prem_html = "<span class='badge prem-badge'>💎 PREMIUM</span>" if c_prem and p.get(c_prem) == 'SI' else ""
            
            storico_tasks = st.session_state.db_tasks.get(p[c_nom], [])
            has_cd_fatto = any("CD" in str(t).upper() for t in storico_tasks)
            task_badge_html = "<span class='badge done-badge'>✅ CD COMPLETATO</span>" if has_cd_fatto else ""

            canvass_html = ""
            valore_canvass = p.get(c_canv, '') if c_canv else ''
            if valore_canvass and str(valore_canvass).strip():
                canvass_html = f"<div style='background:linear-gradient(90deg, #059669, #10b981); color:white; padding:10px; border-radius:8px; margin-bottom:15px; font-weight:bold; border:1px solid rgba(52, 211, 153, 0.4); box-shadow: 0 4px 6px rgba(0,0,0,0.2);'>📢 CANVASS: {valore_canvass}</div>"

            map_status = ""
            if not p['g_data']['found']: map_status = "<div style='color: #f87171; font-weight:bold; margin-top:5px; margin-bottom:10px; font-size:0.9rem;'>⚠️ GPS NON TROVATO</div>"

            html_card = f"""
<div class="client-card">
<div class="card-header"><div style="display:flex; align-items:center; flex-wrap: wrap;">{forced_html}{task_badge_html}{prem_html}</div><div class="arrival-time">{ora_str}</div></div>
<div style="margin-bottom: 15px;"><span class="client-name">{i+1}. {p[c_nom]}</span></div>
{canvass_html}
<div class="strategy-box" style="{style_coach}">{msg_coach}</div>
{map_status}
<div class="info-row"><span>📍 {p[c_ind]}, {p[c_com]}</span><span class="real-traffic">🚗 Guida: {p['travel_time']} min</span></div>
<div class="info-row"><span class="ai-badge">⏱️ Visita: {p['duration']} min ({ai_lbl})</span><span class="highlight">📞 {tel_display}</span></div>
</div>"""
            st.markdown(html_card, unsafe_allow_html=True)

            with st.expander("🔄 SOSTITUISCI CLIENTE / DETTAGLI CRM"):
                col_swap_1, col_swap_2 = st.columns([3, 1])
                clienti_nel_giro = [x[c_nom] for x in route]
                candidates_df = df[~df[c_nom].isin(clienti_nel_giro)]
                if sel_zona: candidates_df = candidates_df[candidates_df[c_com].isin(sel_zona)]
                if sel_cap: candidates_df = candidates_df[candidates_df[c_cap].isin(sel_cap)]
                
                clienti_cg_completato = [c for c, tasks in st.session_state.db_tasks.items() if any("CG" in str(t).upper() for t in tasks)]
                candidates_df = candidates_df[~candidates_df[c_nom].isin(clienti_cg_completato)]
                
                candidati_sostituzione = sorted(candidates_df[c_nom].unique().tolist())
                with col_swap_1: nuovo_cliente_nome = st.selectbox(f"Seleziona cliente alternativo:", ["- Scegli -"] + candidati_sostituzione, key=f"sel_swap_{i}")
                with col_swap_2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("🔄 SCAMBIA", key=f"btn_swap_{i}", use_container_width=True):
                        if nuovo_cliente_nome != "- Scegli -":
                            dati_nuovo = df[df[c_nom] == nuovo_cliente_nome].to_dict('records')[0]
                            g_data_nuovo = get_google_data([f"{dati_nuovo[c_ind]}, {dati_nuovo[c_com]}, Italy", f"{dati_nuovo[c_nom]}, {dati_nuovo[c_com]}"])
                            if not g_data_nuovo or not g_data_nuovo['found']: g_data_nuovo = {'coords': SEDE_COORDS, 'found': False, 'tel': ''}
                            dati_nuovo['g_data'] = g_data_nuovo; dati_nuovo['arr'] = p['arr']; dati_nuovo['duration'] = p['duration']; dati_nuovo['travel_time'] = p['travel_time']
                            dati_nuovo['tasks_completed'] = st.session_state.db_tasks.get(dati_nuovo[c_nom], [])
                            st.session_state.master_route[i] = dati_nuovo
                            if ws_mem: salva_giro_solo_rotta(ws_mem, st.session_state.master_route)
                            st.rerun()
                st.dataframe(pd.DataFrame([{k:v for k,v in p.items() if k not in ['g_data', 'arr', 'learned', 'travel_time', 'duration', 'NOTE_SESSION', 'tasks_completed']}]).T, use_container_width=True)

            if 'tasks_completed' not in p: p['tasks_completed'] = []
            if c_att and p.get(c_att):
                task_list = [t.strip() for t in str(p[c_att]).split(',') if t.strip()]
                if task_list:
                    st.markdown("<p style='color:#e2e8f0; font-weight:600; margin-bottom:5px; margin-top:10px;'>📋 Checklist Attività:</p>", unsafe_allow_html=True)
                    for t_idx, task in enumerate(task_list):
                        chk_key = f"chk_{i}_{t_idx}_{p[c_nom]}"
                        is_checked = st.checkbox(task, value=(task in p['tasks_completed']), key=chk_key)
                        if is_checked and task not in p['tasks_completed']: p['tasks_completed'].append(task)
                        elif not is_checked and task in p['tasks_completed']: p['tasks_completed'].remove(task)

            tasks_done = p.get('tasks_completed', [])
            tasks_total = len([t.strip() for t in str(p.get(c_att, '')).split(',') if t.strip()])
            p['NOTE_SESSION'] = st.text_area(f"🎤 Note Visita {p[c_nom]}:", value=p.get('NOTE_SESSION', ''), key=f"note_{i}", height=70, placeholder="Scrivi qui il resoconto della visita...")
            
            c1, c2, c3, c4 = st.columns(4)
            with c1: 
                if p['g_data']['found']: st.link_button("🚙 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={p['g_data']['coords'][0]},{p['g_data']['coords'][1]}&travelmode=driving", use_container_width=True)
                else: st.button("🚫 NO GPS", disabled=True, use_container_width=True)
            with c2: 
                if tel_display: st.link_button("📞 CHIAMA", f"tel:{tel_display}", use_container_width=True)
                else: st.button("🚫 NO TEL", disabled=True, use_container_width=True)
            with c3:
                if st.button("💾 SALVA NOTE", key=f"save_{i}", use_container_width=True):
                    st.session_state.db_tasks[p[c_nom]] = p['tasks_completed']
                    if ws_mem: 
                        aggiorna_attivita_cliente(ws_mem, p[c_nom], p['tasks_completed'])
                        salva_giro_solo_rotta(ws_mem, st.session_state.master_route)
            with c4:
                colore_btn = "primary" if len(tasks_done) >= tasks_total else "secondary"
                label_btn = "✅ CONCLUDI" if len(tasks_done) >= tasks_total else "⚠️ CHIUDI"
                if st.button(label_btn, key=f"d_{i}", type=colore_btn, use_container_width=True):
                    try:
                        riga_cliente = df.index[df[c_nom] == p[c_nom]].tolist()[0] + 2
                        col_visita = list(df.columns).index(c_vis) + 1
                        
                        ws.update_cell(riga_cliente, col_visita, "SI")
                        
                        report_extra = (f"[ATTIVITÀ: {', '.join(tasks_done)}] " if tasks_done else "") + (f"[NOTE: {p.get('NOTE_SESSION', '')}]" if p.get('NOTE_SESSION') else "")
                        log_visit(ws_ai, p[c_nom], p.get('duration', 20), report_extra)
                        
                        if ws_mem: pulisci_attivita_cliente(ws_mem, p[c_nom])
                        if p[c_nom] in st.session_state.db_tasks:
                            del st.session_state.db_tasks[p[c_nom]]
                            
                        st.session_state.master_route.pop(i)
                        if ws_mem: salva_giro_solo_rotta(ws_mem, st.session_state.master_route)
                        st.rerun()
                    except Exception as e: 
                        st.error(f"Errore tecnico nel salvataggio: {e}")
            st.markdown("<hr style='border:1px solid rgba(255,255,255,0.05); margin: 30px 0;'>", unsafe_allow_html=True)
