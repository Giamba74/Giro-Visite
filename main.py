import streamlit as st
import pandas as pd
import numpy as np
from geopy.distance import geodesic
import math
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import pytz
import json
import copy
import time
import re
import requests

# --- CONFIGURAZIONE E SICUREZZA ---
st.set_page_config(page_title="Brightstar CRM PRO", page_icon="🔒", layout="wide")
TZ_ITALY = pytz.timezone('Europe/Rome')

# ==============================================================================
# 🔒 SCHERMATA DI SICUREZZA E ID FOGLIO
# ==============================================================================
PIN_SEGRETO = "Takira74,1974"  # <--- CAMBIA QUESTO NUMERO O PAROLA COME PREFERISCI!
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" # <--- INSERISCI IL TUO ID GOOGLE SHEETS
# ==============================================================================

# --- SISTEMA DI BLOCCO ACCESSI ---
if "autenticato" not in st.session_state:
    st.session_state.autenticato = False

if not st.session_state.autenticato:
    st.markdown("""
        <style>
        .stApp { background: radial-gradient(circle at center, #0f172a 0%, #000000 100%); color: #f1f5f9; font-family: 'Inter', sans-serif;}
        .login-box { max-width: 400px; margin: 100px auto; background: #1e293b; padding: 40px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); text-align: center; border: 1px solid #334155;}
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown("<div class='login-box'>", unsafe_allow_html=True)
    st.markdown("<h1 style='font-size: 3rem; margin-bottom: 0;'>🛡️</h1>", unsafe_allow_html=True)
    st.markdown("<h2>ACCESSO RISERVATO</h2>", unsafe_allow_html=True)
    st.markdown("<p style='color: #94a3b8; margin-bottom: 20px;'>Brightstar CRM PRO - Inserisci il codice di sicurezza.</p>", unsafe_allow_html=True)
    
    pin_inserito = st.text_input("PIN:", type="password", placeholder="••••")
    
    if st.button("🔓 SBLOCCA SISTEMA", type="primary", use_container_width=True):
        if pin_inserito == PIN_SEGRETO:
            st.session_state.autenticato = True
            st.rerun()
        else:
            st.error("❌ Codice errato. Accesso negato.")
            
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop() # 🛑 BLOCCO TOTALE: Il resto del codice non viene letto se il PIN è sbagliato!

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
    .info-row { display: flex; flex-wrap: wrap; gap: 10px; color: #94a3b8; font-size: 0.9rem; margin-bottom: 15px; font-weight: 500;}
    .info-tag { background: rgba(255, 255, 255, 0.05); padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.1); }
    .badge-potenziale { background: rgba(16, 185, 129, 0.2); color: #34d399; padding: 5px 12px; border-radius: 8px; font-weight: bold; border: 1px solid rgba(16, 185, 129, 0.5);}
    .metric-val { font-size: 1.8rem; font-weight: 800; color: #38bdf8; }
    .btn-maps { background: linear-gradient(135deg, #10b981, #059669); color: white; text-align:center; padding: 10px; border-radius: 8px; display:block; font-weight:bold; text-decoration:none; margin-bottom:20px;}
    </style>
    """, unsafe_allow_html=True)

COORDS = { "Chianti": (43.661888, 11.305728), "Firenze": (43.7696, 11.2558), "Arezzo": (43.4631, 11.8781) }
SEDE_COORDS = COORDS["Chianti"]

@st.cache_resource
def connect_db():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_key(ID_DEL_FOGLIO)
        ws_main = sh.get_worksheet(0)
        titoli_fogli = {w.title.strip().upper(): w for w in sh.worksheets()}
        ws_mem = titoli_fogli.get("MEMORIA_GIRO")
        ws_pot = titoli_fogli.get("POTENZIALI")
        
        ws_log = titoli_fogli.get("LOG_VISITE")
        if not ws_log:
            try:
                ws_log = sh.add_worksheet(title="LOG_VISITE", rows=1000, cols=5)
                ws_log.update("A1:D1", [["DATA", "CLIENTE", "TIPO", "ATTIVITA"]])
            except: pass
            
        return ws_main, ws_mem, ws_pot, ws_log
    except: return None, None, None, None

def carica_storico_attivita(sh_memoria):
    try:
        raw = sh_memoria.get("D:E") 
        return {row[0]: json.loads(row[1]) for row in raw[1:] if len(row) >= 2} if raw else {}
    except: return {}

def aggiorna_attivita_cliente(sh_memoria, cliente, tasks_list):
    try:
        raw = sh_memoria.get("D:E")
        records = raw if raw else []
        row_idx = next((i + 1 for i, row in enumerate(records) if len(row) > 0 and row[0] == cliente), -1)
        if row_idx != -1:
            sh_memoria.update_cell(row_idx, 5, json.dumps(tasks_list))
        else:
            next_row = len(sh_memoria.col_values(4)) + 1
            sh_memoria.update_cell(next_row, 4, cliente)
            sh_memoria.update_cell(next_row, 5, json.dumps(tasks_list))
    except: pass

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

def euclidean_dist(c1, c2):
    dy = (c1[0] - c2[0]) * 111320
    dx = (c1[1] - c2[1]) * 81000
    return math.sqrt(dx*dx + dy*dy)

def calcola_distanza_pedonale(coord_partenza, coord_arrivo):
    try:
        url = f"http://router.project-osrm.org/route/v1/foot/{coord_partenza[1]},{coord_partenza[0]};{coord_arrivo[1]},{coord_arrivo[0]}?overview=false"
        res = requests.get(url, timeout=3).json()
        if res.get("code") == "Ok": return res["routes"][0]["distance"]
    except: pass
    return geodesic(coord_partenza, coord_arrivo).meters * 1.30

def optimize_route_2opt(raw_pool, start_coords):
    if not raw_pool: return []
    optimized = []
    current = start_coords
    unvisited = raw_pool.copy()
    
    while unvisited:
        next_node = min(unvisited, key=lambda x: euclidean_dist(current, x['coords']))
        optimized.append(next_node)
        current = next_node['coords']
        unvisited.remove(next_node)
        
    improvement = True
    while improvement:
        improvement = False
        for i in range(len(optimized) - 1):
            for j in range(i + 2, len(optimized)):
                node_i = start_coords if i == 0 else optimized[i-1]['coords']
                d1 = euclidean_dist(node_i, optimized[i]['coords'])
                d2 = euclidean_dist(optimized[j-1]['coords'], optimized[j]['coords'])
                d3 = euclidean_dist(node_i, optimized[j-1]['coords'])
                d4 = euclidean_dist(optimized[i]['coords'], optimized[j]['coords'])
                
                if d3 + d4 < d1 + d2:
                    optimized[i:j] = reversed(optimized[i:j])
                    improvement = True
    return optimized

def salva_giro_memoria(ws_mem, rotta):
    if not ws_mem: return
    try:
        rotta_copy = copy.deepcopy(rotta)
        for p in rotta_copy:
            if isinstance(p.get('arr'), datetime): p['arr'] = p['arr'].strftime("%Y-%m-%d %H:%M:%S")
        ws_mem.update_acell("B2", json.dumps(rotta_copy))
    except: pass

def carica_giro_da_foglio(sh_memoria):
    try:
        json_data = sh_memoria.acell("B2").value
        if json_data:
            rotta = json.loads(json_data)
            for p in rotta:
                if 'arr' in p and isinstance(p['arr'], str):
                    try: p['arr'] = datetime.strptime(p['arr'], "%Y-%m-%d %H:%M:%S")
                    except: p['arr'] = pd.to_datetime(p['arr']).to_pydatetime()
                if 'coords' not in p or p['coords'] is None: p['coords'] = SEDE_COORDS
                if 'tasks_completed' not in p: p['tasks_completed'] = []
            return rotta
    except: return None
    return None

def get_geo_data(query_list):
    time.sleep(0.3) 
    for q in query_list:
        try:
            url = f"https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?singleLine={requests.utils.quote(q)}&f=json&maxLocations=1"
            res = requests.get(url, timeout=4).json()
            if res.get('candidates'):
                loc = res['candidates'][0]['location']
                return (loc['y'], loc['x'])
        except: continue
    for q in query_list:
        try:
            url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(q)}&format=json&limit=1"
            res = requests.get(url, headers={'User-Agent': 'BrightstarApp/1.0'}, timeout=4).json()
            if res: return (float(res[0]['lat']), float(res[0]['lon']))
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
ws, ws_mem, ws_pot, ws_log = connect_db()

if 'radar_risultati' not in st.session_state: st.session_state.radar_risultati = None
if 'radar_scarti' not in st.session_state: st.session_state.radar_scarti = None

if ws:
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=[h.strip().upper() for h in data[0]])
    
    c_nom = next(c for c in df.columns if "CLIENTE" in c)
    c_ind = next(c for c in df.columns if "INDIRIZZO" in c or "VIA" in c)
    c_com = next(c for c in df.columns if "COMUNE" in c)
    c_vis = next(c for c in df.columns if "VISITATO" in c)
    c_prem = next((c for c in df.columns if "PREMIUM" in c), None)
    c_lat = next((c for c in df.columns if "LAT" in c.upper()), None)
    c_lon = next((c for c in df.columns if "LON" in c.upper()), None)
    c_note_sto = next((c for c in df.columns if "STORICO" in c or "NOTE" in c), None)
    c_att = next((c for c in df.columns if "ATTIVIT" in c), None)
    c_tel = next((c for c in df.columns if "TELEFONO" in c or "CELL" in c or "TEL" in c), None)
    c_piva = next((c for c in df.columns if "P.IVA" in c or "PIVA" in c), None)
    c_codice = next((c for c in df.columns if "CODICE" in c.upper() or "COD " in c.upper() or "COD." in c.upper()), None)
    c_pos = next((c for c in df.columns if "POS" in c.upper() or "DB_POS" in c.upper() or "DB" in c.upper()), None)
    
    c_cap = next((c for c in df.columns if "CAP" in c), None)
    if c_cap:
        df[c_cap] = df[c_cap].astype(str).str.replace('.0', '', regex=False).str.replace('nan', '').str.strip()
        df[c_cap] = df[c_cap].apply(lambda x: x.zfill(5) if x else '')

    if 'master_route' not in st.session_state and ws_mem:
        st.session_state.master_route = carica_giro_da_foglio(ws_mem)
    if 'db_tasks' not in st.session_state and ws_mem: 
        st.session_state.db_tasks = carica_storico_attivita(ws_mem)

    st.markdown("<div class='app-header'>🚀 BRIGHTSTAR CRM PRO v5.48</div>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["🚗 GIRO VISITE & NUOVI", "🛰️ RADAR 150m & TELEMACO"])

    with tab1:
        st.sidebar.markdown("### 🗺️ Opzioni Giro")
        indirizzo_start = st.sidebar.text_input("📍 Da dove parti?", value="", help="Es. 'Via Roma 10, Arezzo'. Se lasci vuoto, l'App calcola il centro esatto della zona e parte da lì!")
        num_visite = st.sidebar.slider("🚗 Clienti DB:", 1, 30, 8)
        only_premium = st.sidebar.toggle("💎 Solo PREMIUM", value=True)
        sel_zona_giro = st.sidebar.multiselect("🌍 Filtra Comune:", sorted([str(c).strip() for c in df[c_com].unique() if str(c).strip()]))
        
        sel_cap_giro = []
        if c_cap:
            lista_cap = sorted([str(x).strip() for x in df[c_cap].unique() if str(x).strip()])
            sel_cap_giro = st.sidebar.multiselect("📮 Filtra CAP:", lista_cap)
            
        st.sidebar.divider()
        st.sidebar.markdown("### 🎯 Sviluppo Rete")
        num_potenziali = st.sidebar.slider("🆕 Potenziali da inserire:", 0, 5, 1)

        if st.button("🔄 CALCOLA NUOVO GIRO OTTIMIZZATO", type="primary", use_container_width=True):
            with st.spinner("L'Intelligenza Artificiale sta stirando il percorso (Algoritmo 2-Opt)..."):
                sel_zona_clean = [c.strip().upper() for c in sel_zona_giro]
                sel_cap_clean = [c.strip() for c in sel_cap_giro]

                mask = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
                if sel_zona_clean: mask &= df[c_com].astype(str).str.strip().str.upper().isin(sel_zona_clean)
                if sel_cap_clean: mask &= df[c_cap].astype(str).str.strip().isin(sel_cap_clean)
                if only_premium and c_prem: mask &= df[c_prem].astype(str).str.upper().str.contains('SI', na=False)
                
                clienti_cg_completati = [n for n, tasks in st.session_state.db_tasks.items() if any("CG" in str(t).upper() for t in tasks)]
                mask &= ~df[c_nom].isin(clienti_cg_completati)
                
                df_pulito = df[mask].drop_duplicates(subset=[c_nom])
                raw_pool = df_pulito.head(num_visite).to_dict('records')
                for p in raw_pool: p['is_potenziale'] = False
                
                if num_potenziali > 0 and ws_pot:
                    try:
                        pot_data = ws_pot.get_all_values()
                        if len(pot_data) > 1:
                            for r_idx, row in enumerate(pot_data[1:]):
                                idx_stato = next((i for i, cell in enumerate(row) if "✅" in str(cell).upper() or "DISPONIBILE" in str(cell).upper()), -1)
                                if idx_stato >= 3:
                                    data_visita = str(row[idx_stato + 1]).strip() if len(row) > idx_stato + 1 else ""
                                    if not data_visita:
                                        com_pot = str(row[idx_stato - 1]).strip().upper()
                                        ind_pot = str(row[idx_stato - 2]).strip()
                                        nom_pot = str(row[idx_stato - 3]).strip()
                                        
                                        p_cap = True
                                        if sel_cap_clean:
                                            found_cap = re.findall(r'\b\d{5}\b', ind_pot)
                                            if found_cap and not any(c in found_cap for c in sel_cap_clean): p_cap = False
                                        
                                        p_com = True
                                        if sel_zona_clean and not any(z in com_pot for z in sel_zona_clean): p_com = False
                                            
                                        if p_cap and p_com:
                                            raw_pool.append({
                                                c_nom: nom_pot, c_ind: ind_pot, c_com: com_pot,
                                                "is_potenziale": True, "PIVA": str(row[idx_stato + 4]).strip() if len(row) > idx_stato + 4 else "",
                                                "row_idx": r_idx + 2, "idx_stato": idx_stato
                                            })
                                            if len([x for x in raw_pool if x['is_potenziale']]) >= num_potenziali: break
                    except: pass

                if not raw_pool:
                    st.warning("⚠️ Nessun cliente trovato con questi filtri.")
                else:
                    for p in raw_pool:
                        if not p['is_potenziale']:
                            la, lo = pulisci_coordinata_italy(p.get(c_lat), True), pulisci_coordinata_italy(p.get(c_lon), False)
                            p['coords'] = (la, lo) if la and lo else get_geo_data([f"{p[c_ind]}, {p[c_com]}, Italy", f"{p[c_com]}, Italy"])
                        else:
                            p['coords'] = get_geo_data([f"{p[c_ind]}, {p[c_com]}, Italy", f"{p[c_com]}, Italy"])
                        if not p['coords']: p['coords'] = SEDE_COORDS 
                    
                    if indirizzo_start.strip():
                        start_coords = get_geo_data([indirizzo_start, f"{indirizzo_start}, Italy"])
                        if not start_coords: 
                            st.toast("⚠️ Indirizzo non trovato. Parto dal centro della zona.", icon="🗺️")
                            start_coords = None
                    else: start_coords = None

                    if not start_coords:
                        avg_lat = sum(p['coords'][0] for p in raw_pool) / len(raw_pool)
                        avg_lon = sum(p['coords'][1] for p in raw_pool) / len(raw_pool)
                        start_coords = min(raw_pool, key=lambda x: euclidean_dist((avg_lat, avg_lon), x['coords']))['coords']

                    rotta_ottimizzata = optimize_route_2opt(raw_pool, start_coords)
                    
                    curr_t = datetime.now(TZ_ITALY).replace(hour=9, minute=0)
                    for p in rotta_ottimizzata:
                        p['arr'] = curr_t
                        p['tasks_completed'] = copy.deepcopy(st.session_state.db_tasks.get(p[c_nom], [])) if not p['is_potenziale'] else []
                        curr_t += timedelta(minutes=40)
                    
                    st.session_state.start_coords_route = start_coords
                    st.session_state.master_route = rotta_ottimizzata
                    salva_giro_memoria(ws_mem, rotta_ottimizzata)
                    st.rerun()

        if st.session_state.get('master_route'):
            if st.session_state.get('start_coords_route'):
                maps_url = f"https://www.google.com/maps/dir/{st.session_state.start_coords_route[0]},{st.session_state.start_coords_route[1]}"
                for t_p in st.session_state.master_route[:9]: maps_url += f"/{t_p['coords'][0]},{t_p['coords'][1]}"
                st.markdown(f"<a href='{maps_url}' target='_blank' class='btn-maps'>🗺️ APRI INTERO GIRO SU GOOGLE MAPS</a>", unsafe_allow_html=True)

            for i, p in enumerate(st.session_state.master_route):
                is_pot = p.get('is_potenziale', False)
                badge_html = "<span class='badge-potenziale'>🆕 POTENZIALE</span>" if is_pot else ("<span class='badge prem-badge'>💎 PREMIUM</span>" if c_prem and p.get(c_prem) == 'SI' else "")
                
                st.markdown(f"""
                <div class="client-card">
                    <div class="card-header"><div>{badge_html}</div><div class="arrival-time">{pd.to_datetime(p['arr']).strftime('%H:%M')}</div></div>
                    <div style="font-size:1.3rem; font-weight:bold; margin-bottom: 10px;">{i+1}. {p[c_nom]}</div>
                """, unsafe_allow_html=True)
                
                pronto = True
                if not is_pot:
                    msg_c, style_c = agente_strategico(p.get(c_note_sto, ''))
                    st.markdown(f"<div class='strategy-box' style='{style_c}'>{msg_c}</div>", unsafe_allow_html=True)
                    tel = str(p.get(c_tel, '')).replace('nan', '').strip()
                    info_h = ""
                    for k, v in {"P.IVA": p.get(c_piva), "Cod": p.get(c_codice), "POS": p.get(c_pos), "📞": tel}.items():
                        if v and str(v).lower() != 'nan': info_h += f"<span class='info-tag'>{k}: {v}</span>"
                    st.markdown(f"<div class='info-row'>{info_h}</div>", unsafe_allow_html=True)
                    
                    tasks_done = p.get('tasks_completed', [])
                    if c_att and p.get(c_att):
                        t_list = list(dict.fromkeys([t.strip() for t in str(p[c_att]).split(',') if t.strip() and t.lower() != 'nan']))
                        if t_list:
                            st.markdown("**📝 Attività:**")
                            for t_idx, task in enumerate(t_list):
                                key_name = f"chk_{re.sub(r'[^a-zA-Z0-9]', '', str(p[c_nom]))}_{t_idx}"
                                is_chk = st.checkbox(task, value=(task in tasks_done), key=key_name)
                                if is_chk and task not in tasks_done: tasks_done.append(task)
                                elif not is_chk and task in tasks_done: tasks_done.remove(task)
                            p['tasks_completed'] = tasks_done
                            if any("CG" in t.upper() for t in t_list): pronto = any("CG" in t.upper() for t in tasks_done)
                
                coord_alert = " ⚠️ (Precisione Mappa Ridotta)" if p.get('coords') == SEDE_COORDS and c_com not in "Chianti" else ""
                st.markdown(f"<div style='color:#94a3b8; font-weight:500; margin-bottom: 15px;'>📍 {p.get(c_ind, '')}, {p.get(c_com, '')}{coord_alert}</div>", unsafe_allow_html=True)
                
                esito_sel = ""
                if is_pot:
                    with st.expander("📝 Compila Dati", expanded=True):
                        c_p1, c_p2 = st.columns(2)
                        with c_p1: esito_sel = st.selectbox("Esito:", ["In Attesa", "Interessato", "Da richiamare", "Non interessato", "Chiuso"], key=f"esi_{i}")
                        with c_p2: st.text_input("Scoring (A,B,C):", key=f"sco_{i}")
                    pronto = esito_sel in ["Non interessato", "Chiuso"]
                
                c_dest = p.get('coords', SEDE_COORDS)
                c1, c2, c3 = st.columns([1, 1, 2])
                with c1: st.link_button("🚙 NAVIGA PUNTO", f"https://www.google.com/maps/dir/?api=1&destination={c_dest[0]},{c_dest[1]}", use_container_width=True)
                if not is_pot:
                    with c2: 
                        if tel: st.link_button("📞 CHIAMA", f"tel:{tel}", use_container_width=True)
                        else: st.button("📞 NO TEL", disabled=True, use_container_width=True)
                    with c3: 
                        if st.button("✅ CONCLUDI", key=f"bc_{i}", use_container_width=True, type="primary" if pronto else "secondary"):
                            if not pronto: st.warning("Spunta 'CG'!")
                            else:
                                vecchi_tasks = st.session_state.db_tasks.get(p[c_nom], [])
                                nuovi_tasks = [t for t in p['tasks_completed'] if t not in vecchi_tasks]
                                if ws_log:
                                    try:
                                        oggi_str = datetime.now(TZ_ITALY).strftime("%d/%m/%Y")
                                        str_task = ", ".join(nuovi_tasks) if nuovi_tasks else "Solo Visita"
                                        ws_log.append_row([oggi_str, p[c_nom], "CLIENTE DB", str_task])
                                    except: pass
                                
                                st.session_state.db_tasks[p[c_nom]] = p['tasks_completed']
                                if ws_mem: aggiorna_attivita_cliente(ws_mem, p[c_nom], p['tasks_completed'])
                                try:
                                    r_idx = df.index[df[c_nom] == p[c_nom]].tolist()[0] + 2
                                    ws.update_cell(r_idx, list(df.columns).index(c_vis)+1, "SI")
                                except: pass
                                st.session_state.master_route.pop(i)
                                salva_giro_memoria(ws_mem, st.session_state.master_route)
                                st.rerun()
                else:
                    with c3:
                        if st.button("✅ SALVA POT.", key=f"bc_{i}", use_container_width=True, type="primary" if pronto else "secondary"):
                            if not pronto: st.warning("Imposta esito conclusivo!")
                            else:
                                if ws_log:
                                    try:
                                        oggi_str = datetime.now(TZ_ITALY).strftime("%d/%m/%Y")
                                        ws_log.append_row([oggi_str, p[c_nom], "POTENZIALE", esito_sel])
                                    except: pass

                                if ws_pot:
                                    try: ws_pot.update_cell(p['row_idx'], p['idx_stato']+2, datetime.now(TZ_ITALY).strftime("%d/%m/%Y"))
                                    except: pass
                                st.session_state.master_route.pop(i)
                                salva_giro_memoria(ws_mem, st.session_state.master_route)
                                st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

            # --- INNESTO DINAMICO CORRETTO ---
            st.divider()
            with st.expander("➕ AGGIUNGI CLIENTE AL VOLO"):
                nomi_nel_giro = [p[c_nom] for p in st.session_state.master_route]
                clienti_cg_completati = [n for n, t in st.session_state.db_tasks.items() if any("CG" in str(x).upper() for x in t)]
                
                # BUGFIX: La variabile si chiama 'clienti_disponibili' e non 'disponibili'
                clienti_disponibili = sorted(df[~df[c_nom].isin(nomi_nel_giro) & ~df[c_nom].isin(clienti_cg_completati)][c_nom].dropna().unique().tolist())
                
                potenziali_disponibili = []
                if ws_pot:
                    try:
                        pot_data = ws_pot.get_all_values()
                        if len(pot_data) > 1:
                            for r_idx, row in enumerate(pot_data[1:]):
                                idx_stato = next((i for i, cell in enumerate(row) if "✅" in str(cell).upper() or "DISPONIBILE" in str(cell).upper()), -1)
                                if idx_stato >= 3:
                                    data_visita = str(row[idx_stato + 1]).strip() if len(row) > idx_stato + 1 else ""
                                    if not data_visita:
                                        nome_pot = str(row[idx_stato - 3]).strip()
                                        if nome_pot and nome_pot not in nomi_nel_giro:
                                            comune_pot = str(row[idx_stato - 1]).strip().title()
                                            potenziali_disponibili.append(f"🆕 {nome_pot} ({comune_pot}) [POTENZIALE]")
                    except: pass
                
                tutti_disponibili = [""] + potenziali_disponibili + clienti_disponibili
                scelto = st.selectbox("Seleziona:", tutti_disponibili)
                
                if st.button("⚡ INSERISCI", type="primary") and scelto:
                    p_new = {}
                    is_pot_selezionato = "🆕 " in scelto and "[POTENZIALE]" in scelto
                    
                    if is_pot_selezionato:
                        clean_name = scelto.split(" (")[0].replace("🆕 ", "").strip()
                        pot_data = ws_pot.get_all_values()
                        for r
