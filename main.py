import streamlit as st
import pandas as pd
import numpy as np
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from datetime import datetime, timedelta
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials
import pytz
import json
import copy
import time
import re

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar CRM PRO", page_icon="💎", layout="wide")
TZ_ITALY = pytz.timezone('Europe/Rome')

# --- 🎨 DESIGN E STILE CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    .stApp { font-family: 'Inter', sans-serif; background: radial-gradient(circle at top left, #1e293b 0%, #0f172a 100%); color: #f1f5f9; }
    .app-header { background: linear-gradient(90deg, #2563eb, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.5rem; font-weight: 800; text-align: center; margin-bottom: 30px; letter-spacing: -1px;}
    .client-card { background: linear-gradient(145deg, rgba(30, 41, 59, 0.85), rgba(15, 23, 42, 0.9)); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 20px; padding: 24px; margin-bottom: 16px; box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
    .client-card:hover { transform: translateY(-4px) scale(1.01); box-shadow: 0 20px 40px -10px rgba(59, 130, 246, 0.25); border-color: rgba(59, 130, 246, 0.3); }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 12px; }
    .client-name { font-size: 1.45rem; font-weight: 800; color: #ffffff; letter-spacing: -0.5px; }
    .arrival-time { background: linear-gradient(135deg, #3b82f6, #6366f1); color: white; padding: 6px 16px; border-radius: 30px; font-weight: 700; font-size: 1.1rem; }
    .strategy-box { padding: 12px 16px; border-radius: 10px; margin-bottom: 18px; font-size: 0.95em; color: #e2e8f0; border-left: 5px solid; background: rgba(0,0,0,0.25); font-weight: 500; }
    .info-row { display: flex; gap: 15px; color: #94a3b8; font-size: 0.95rem; margin-bottom: 8px; font-weight: 500;}
    .highlight { color: #38bdf8; font-weight: 700; }
    .real-traffic { color: #fbbf24; font-size: 0.85rem; font-weight: 600; background: rgba(251, 191, 36, 0.1); padding: 2px 8px; border-radius: 6px;}
    .ai-badge { font-size: 0.8rem; background-color: rgba(51, 65, 85, 0.8); color: #cbd5e1; padding: 3px 10px; border-radius: 6px; font-weight: 600;}
    .badge { padding: 4px 10px; border-radius: 8px; margin-right: 8px; font-size: 0.75rem; text-transform: uppercase; font-weight: 700; display: inline-block; margin-bottom: 5px;}
    .forced-badge { background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.4); }
    .prem-badge { background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); }
    .done-badge { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
    .radar-ok { background: rgba(16, 185, 129, 0.15); color: #34d399; padding: 15px; border-radius: 12px; border: 1px solid rgba(16, 185, 129, 0.4); font-weight: bold; text-align: center; margin-bottom: 15px;}
    .radar-no { background: rgba(239, 68, 68, 0.15); color: #f87171; padding: 15px; border-radius: 12px; border: 1px solid rgba(239, 68, 68, 0.4); font-weight: bold; text-align: center; margin-bottom: 15px;}
    div[data-testid="stButton"] button { border-radius: 12px; font-weight: 700; transition: all 0.2s ease; border: none !important; text-transform: uppercase; padding: 10px 0; }
    div[data-testid="stButton"] button:hover { transform: scale(1.03) translateY(-2px); box-shadow: 0 8px 15px rgba(0,0,0,0.3); }
    .stTextArea textarea { border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); background: rgba(15,23,42,0.6); color: white;}
    </style>
    """, unsafe_allow_html=True)

COORDS = { "Chianti": (43.661888, 11.305728), "Firenze": (43.7696, 11.2558), "Arezzo": (43.4631, 11.8781) }
SEDE_COORDS = COORDS["Chianti"]

# ==============================================================================
# 👇 MODIFICA SOLO QUI SOTTO CON IL TUO VERO ID FOGLIO GOOGLE 👇
ID_DEL_FOGLIO = "IL_TUO_ID_QUI" 
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
             if not ws_mem.acell("A1").value:
                 ws_mem.update_acell("A1", "DATA"); ws_mem.update_acell("B1", "JSON_DATA"); ws_mem.update_acell("D1", "DB_CLIENTE"); ws_mem.update_acell("E1", "DB_TASKS")
                 
        ws_pot = sh.worksheet("POTENZIALI") if "POTENZIALI" in [w.title for w in sh.worksheets()] else None
        
        return ws_main, ws_log, ws_mem, ws_pot
    except Exception as e: 
        st.error(f"❌ Errore Connessione al Database: {e}")
        return None, None, None, None

def salva_giro_solo_rotta(sh_memoria, rotta_data):
    try:
        dati_export = copy.deepcopy(rotta_data)
        now_str = datetime.now(TZ_ITALY).strftime("%d-%m-%Y") 
        for p in dati_export:
            if isinstance(p.get('arr'), datetime): p['arr'] = p['arr'].strftime("%Y-%m-%d %H:%M:%S")
        sh_memoria.update_acell("A2", now_str); time.sleep(0.5); sh_memoria.update_acell("B2", json.dumps(dati_export)); sh_memoria.update_acell("A2", now_str) 
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
        return {row[0]: json.loads(row[1]) for row in raw[1:] if len(row) >= 2} if raw else {}
    except: return {}

def aggiorna_attivita_cliente(sh_memoria, cliente, tasks_list):
    try:
        records = sh_memoria.get_all_values()
        row_idx = next((i + 1 for i, row in enumerate(records) if len(row) > 3 and row[3] == cliente), -1)
        if row_idx != -1: sh_memoria.update_cell(row_idx, 5, json.dumps(tasks_list))
        else:
            next_row = len(sh_memoria.col_values(4)) + 1
            sh_memoria.update_cell(next_row, 4, cliente); sh_memoria.update_cell(next_row, 5, json.dumps(tasks_list))
    except: pass

def pulisci_attivita_cliente(sh_memoria, cliente):
    try:
        records = sh_memoria.get_all_values()
        row_idx = next((i + 1 for i, row in enumerate(records) if len(row) > 3 and row[3] == cliente), -1)
        if row_idx != -1: sh_memoria.update_cell(row_idx, 4, ""); sh_memoria.update_cell(row_idx, 5, "")
    except: pass

def get_real_travel_time(origin_coords, dest_coords):
    if not origin_coords or not dest_coords: return 20 
    try: return max(5, int(((geodesic(origin_coords, dest_coords).km * 1.5) / 45) * 60))
    except: return 20

def get_walking_distance(coords1, coords2):
    try:
        url = f"http://router.project-osrm.org/route/v1/foot/{coords1[1]},{coords1[0]};{coords2[1]},{coords2[0]}?overview=false"
        res = requests.get(url, timeout=5).json()
        if res['code'] == 'Ok': return int(res['routes'][0]['distance'])
    except: pass
    return int(geodesic(coords1, coords2).meters * 1.3)

def get_geo_data(query_list, fallback_city=""):
    geolocator = Nominatim(user_agent=f"brightstar_crm_app_v5_safe_{int(time.time())}")
    time.sleep(1.5)
    for q in query_list:
        try:
            location = geolocator.geocode(q, timeout=10)
            if location: return {"coords": (location.latitude, location.longitude), "tel": "", "found": True, "is_fallback": False}
        except Exception as e: 
            continue
    if fallback_city:
        try:
            time.sleep(1.5)
            location = geolocator.geocode(f"{fallback_city}, Italy", timeout=10)
            if location: return {"coords": (location.latitude, location.longitude), "tel": "", "found": True, "is_fallback": True}
        except: pass
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
        try: ws_log.append_row([cliente, datetime.now(TZ_ITALY).strftime("%d-%m-%Y"), datetime.now(TZ_ITALY).strftime("%H:%M"), durata, note_extra])
        except: pass

def agente_strategico(note_precedenti):
    if not note_precedenti: return "ℹ️ COACH: Nessuno storico recente.", "border-left-color: #475569;"
    txt = str(note_precedenti).lower()
    if any(x in txt for x in ['arrabbiato', 'reclamo', 'ritardo']): return "🛡️ COACH: Cliente a rischio. Focus su ascolto attivo.", "border-left-color: #ef4444; background: rgba(239, 68, 68, 0.15);"
    if any(x in txt for x in ['prezzo', 'costoso', 'sconto']): return "💎 COACH: Difendi il valore. Prepara argomenti su ROI.", "border-left-color: #f59e0b; background: rgba(245, 158, 11, 0.15);"
    if any(x in txt for x in ['interessato', 'preventivo']): return "🎯 COACH: È caldo! Punta alla chiusura oggi.", "border-left-color: #10b981; background: rgba(16, 185, 129, 0.15);"
    if 'voltura' in txt: return "🔄 COACH: Voltura in corso. Verifica stato documenti.", "border-left-color: #8b5cf6; background: rgba(139, 92, 246, 0.15);"
    return f"ℹ️ MEMO: {note_precedenti[:60]}...", "border-left-color: #3b82f6;"

def pulisci_nome(nome):
    nome = str(nome).upper()
    nome = re.sub(r'[^A-Z0-9\s]', '', nome)
    nome = re.sub(r'\b(SNC|SRL|SAS|SPA|SAPA|DI|IL|LA|LO|I|GLI|LE)\b', '', nome)
    nome = nome.replace('SAN ', 'S ').replace('SANTA ', 'S ')
    return ' '.join(nome.split())

# --- APP START ---
try: ws, ws_ai, ws_mem, ws_pot = connect_db()
except: ws, ws_ai, ws_mem, ws_pot = None, None, None, None

if ws is None: 
    pass
else:
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=[h.strip().upper() for h in data[0]])
    
    try:
        c_nom = next(c for c in df.columns if "CLIENTE" in c)
        c_ind = next(c for c in df.columns if "INDIRIZZO" in c or "VIA" in c)
        c_com = next(c for c in df.columns if "COMUNE" in c)
        c_cap = next((c for c in df.columns if "CAP" in c), "CAP")
        c_vis = next(c for c in df.columns if "VISITATO" in c)
    except StopIteration:
        st.error("❌ ERRORE: Colonne fondamentali mancanti nel Foglio 1.")
        st.stop()
    
    c_tel = next((c for c in df.columns if "TELEFONO" in c or "CELL" in c or "TEL" in c), "TELEFONO")
    if c_tel in df.columns: df[c_tel] = df[c_tel].astype(str).replace('nan', '').replace('None', '')
    c_att = next((c for c in df.columns if "ATTIVIT" in c), None)
    c_canv = next((c for c in df.columns if "CANVASS" in c or "PROMO" in c), None)
    c_note_sto = next((c for c in df.columns if "STORICO" in c or "NOTE" in c), None)
    c_prem = next((c for c in df.columns if "PREMIUM" in c), None)
    c_piva = next((c for c in df.columns if "P.IVA" in c or "PIVA" in c), None)
    
    if "CAP" in df.columns: 
        df[c_cap] = df[c_cap].astype(str).str.replace('.0','').str.strip().str.zfill(5)

    if 'master_route' not in st.session_state and ws_mem:
        rotta_salvata = carica_giro_da_foglio(ws_mem)
        if rotta_salvata:
            st.session_state.master_route = rotta_salvata
            st.toast("🔄 Giro Ripristinato", icon="💾")
    
    if 'db_tasks' not in st.session_state and ws_mem: st.session_state.db_tasks = carica_storico_attivita(ws_mem)

    # --- SIDEBAR DESIGN ---
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; color: #38bdf8; margin-bottom: 20px;'>⚙️ Impostazioni</h2>", unsafe_allow_html=True)
        indirizzo_start = st.text_input("📍 Luogo di Partenza:", value="Chianti, Sede")
        num_visite = st.slider("🚗 Clienti da visitare:", 1, 25, 8)
        st.divider()
        only_premium = st.toggle("💎 Mostra solo PREMIUM", value=True)
        sel_zona = st.multiselect("🌍 Filtra per Zona (Comuni)", sorted(df[c_com].unique()))
        st.divider()
        sel_forced = st.multiselect("⭐ Forzature (Clienti VIP):", sorted(df[c_nom].unique().tolist()))
        st.divider()
        if st.button("🗑️ SVUOTA MEMORIA GIRO", type="secondary"):
             if ws_mem: resetta_solo_rotta(ws_mem)
             if 'master_route' in st.session_state: del st.session_state.master_route
             st.rerun()

    st.markdown("<div class='app-header'>🚀 BRIGHTSTAR CRM PRO</div>", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["🚗 GIRO VISITE", "🚀 SVILUPPO RETE & RADAR 150m"])

    # ==========================================
    # TAB 1: IL GIRO VISITE QUOTIDIANO
    # ==========================================
    with tab1:
        if st.button("🔄 CALCOLA NUOVO GIRO OTTIMIZZATO", type="primary", use_container_width=True):
            start_coords = SEDE_COORDS
            if indirizzo_start:
                with st.spinner(f"🔍 Ricerca partenza..."):
                    loc_data = get_geo_data([indirizzo_start], fallback_city="Firenze")
                    if loc_data and loc_data['found']: start_coords = loc_data['coords']
            
            mask_standard = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
            if sel_zona: mask_standard &= df[c_com].isin(sel_zona)
            if only_premium and c_prem: mask_standard &= df[c_prem].astype(str).str.upper().str.contains('SI', na=False)

            clienti_cg_completato = [n for n, t in st.session_state.db_tasks.items() if any("CG" in str(x).upper() for x in t)]
            mask_standard &= ~df[c_nom].isin(clienti_cg_completato)

            df_final = pd.concat([df[df[c_nom].isin(sel_forced)], df[mask_standard]]).drop_duplicates(subset=[c_nom])
            raw = df_final.to_dict('records')
            
            if not raw: st.warning("🎯 Nessun cliente trovato.")
            else:
                prog_bar = st.progress(0, text="Ricerca Mappe in corso...")
                pool_pronta = []
                for i, p in enumerate(raw):
                    prog_bar.progress((i + 1) / len(raw), text=f"🔍 Mappatura: {p[c_nom]}")
                    if 'g_data' not in p:
                        res = get_geo_data([f"{p[c_ind]}, {p[c_com]}, Italy", f"{p[c_nom]}, {p[c_com]}"], fallback_city=p[c_com])
                        p['g_data'] = res if res and res['found'] else {'coords': SEDE_COORDS, 'found': False, 'is_fallback': False, 'tel': ''}
                    pool_pronta.append(p)
                prog_bar.empty()

                with st.spinner("⏳ IA: Creazione rotta ottimale..."):
                    rotta = []
                    curr_t = datetime.now(TZ_ITALY)
                    curr_t = curr_t.replace(hour=8, minute=0) if curr_t.hour >= 19 else curr_t
                    curr_loc = start_coords
                    pool = pool_pronta.copy()

                    while pool and len(rotta) < num_visite:
                        best = None; best_score = float('inf')
                        for p in pool:
                            c_target = p['g_data']['coords'] if p['g_data']['coords'] else curr_loc
                            try: dist_air = geodesic(curr_loc, c_target).km
                            except: dist_air = 9999 
                            score = dist_air
                            if p[c_nom] in sel_forced: score -= 10000000 
                            if c_prem and p.get(c_prem) == 'SI': score -= 2000 
                            if c_att and p.get(c_att) and str(p[c_att]).strip(): score -= 5000
                            if "CD" not in str(st.session_state.db_tasks.get(p[c_nom], [])).upper(): score -= 5000000
                            if score < best_score: best_score, best = score, p
                        
                        if best:
                            c_best = best['g_data']['coords'] if best['g_data']['coords'] else curr_loc
                            real_mins = get_real_travel_time(curr_loc, c_best)
                            dur_visita, learned = get_ai_duration(ws_ai, best[c_nom])
                            best['arr'] = curr_t + timedelta(minutes=real_mins)
                            best['travel_time'], best['duration'], best['learned'] = real_mins, dur_visita, learned
                            best['tasks_completed'] = st.session_state.db_tasks.get(best[c_nom], [])
                            rotta.append(best)
                            curr_t = best['arr'] + timedelta(minutes=dur_visita)
                            curr_loc = c_best
                            pool.remove(best)
                        else: break
                        
                    st.session_state.master_route = rotta
                    if ws_mem: salva_giro_solo_rotta(ws_mem, rotta)
                    st.rerun()

        if 'master_route' in st.session_state:
            route = st.session_state.master_route
            
            with st.expander("👓 ESPORTA HUD PER OCCHIALI SMART EVEN G2"):
                hud_text = "📅 GIRO BRIGHTSTAR\n" + "-" * 20 + "\n\n"
                for idx_hud, p_hud in enumerate(route):
                    tasks_hud = [t.strip() for t in str(p_hud.get(c_att, '')).split(',') if t.strip()]
                    t_str = f"\n⚠️ {', '.join(tasks_hud)}" if tasks_hud else ""
                    hud_text += f"[{p_hud['arr'].strftime('%H:%M')}] {idx_hud+1}. {str(p_hud[c_nom]).upper()}\n📍 {str(p_hud[c_com])}{t_str}\n\n"
                st.code(hud_text, language="markdown")
                
            for i, p in enumerate(route):
                ai_lbl = "AI" if p.get('learned') else "Std"
                tel_display = str(p.get(c_tel, '')).strip() if str(p.get(c_tel, '')).strip() else p['g_data'].get('tel', '')
                msg_coach, style_coach = agente_strategico(p.get(c_note_sto, ''))
                prem_html = "<span class='badge prem-badge'>💎 PREMIUM</span>" if c_prem and p.get(c_prem) == 'SI' else ""
                task_badge_html = "<span class='badge done-badge'>✅ CD FATTO</span>" if any("CD" in str(t).upper() for t in st.session_state.db_tasks.get(p[c_nom], [])) else ""
                
                st.markdown(f"""
                <div class="client-card">
                <div class="card-header"><div>{task_badge_html}{prem_html}</div><div class="arrival-time">{p['arr'].strftime('%H:%M')}</div></div>
                <div style="margin-bottom: 15px;"><span class="client-name">{i+1}. {p[c_nom]}</span></div>
                <div class="strategy-box" style="{style_coach}">{msg_coach}</div>
                <div class="info-row"><span>📍 {p[c_ind]}, {p[c_com]}</span><span class="real-traffic">🚗 ~{p['travel_time']} min</span></div>
                <div class="info-row"><span class="ai-badge">⏱️ Visita: {p['duration']} min</span><span class="highlight">📞 {tel_display}</span></div>
                </div>""", unsafe_allow_html=True)
                
                tasks_done = p.get('tasks_completed', [])
                if c_att and p.get(c_att):
                    t_list = [t.strip() for t in str(p[c_att]).split(',') if t.strip()]
                    for t_idx, task in enumerate(t_list):
                        is_chk = st.checkbox(task, value=(task in tasks_done), key=f"c_{i}_{t_idx}_{p[c_nom]}")
                        if is_chk and task not in tasks_done: tasks_done.append(task)
                        elif not is_chk and task in tasks_done: tasks_done.remove(task)
                
                c1, c2 = st.columns(2)
                with c1: 
                    if p['g_data'].get('found'): st.link_button("🚙 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={p['g_data']['coords'][0]},{p['g_data']['coords'][1]}", use_container_width=True)
                with c2:
                    pronto = True if not any("CG" in t.upper() for t in str(p.get(c_att, '')).split(',')) else any("CG" in t.upper() for t in tasks_done)
                    if st.button("✅ CONCLUDI" if pronto else "⚠️ CHIUDI", key=f"d_{i}", type="primary" if pronto else "secondary", use_container_width=True):
                        try:
                            riga_cliente = df.index[df[c_nom] == p[c_nom]].tolist()[0] + 2
                            col_visita = list(df.columns).index(c_vis) + 1
                            ws.update_cell(riga_cliente, col_visita, "SI")
                            report = (f"[ATT: {','.join(tasks_done)}] " if tasks_done else "")
                            log_visit(ws_ai, p[c_nom], p.get('duration', 20), report)
                            if ws_mem: pulisci_attivita_cliente(ws_mem, p[c_nom])
                            if p[c_nom] in st.session_state.db_tasks: del st.session_state.db_tasks[p[c_nom]]
                            st.session_state.master_route.pop(i)
                            if ws_mem: salva_giro_solo_rotta(ws_mem, st.session_state.master_route)
                            st.rerun()
                        except Exception as e: st.error(f"Errore: {e}")
                st.markdown("<hr style='border:1px solid rgba(255,255,255,0.05); margin: 20px 0;'>", unsafe_allow_html=True)

    # ==========================================
    # TAB 2: SVILUPPO RETE & RADAR 150 METRI
    # ==========================================
    with tab2:
        st.markdown("### 📋 Elenco POTENZIALI (Target Salvati)")
        if ws_pot:
            try:
                pot_records = ws_pot.get_all_records()
                if pot_records: st.dataframe(pd.DataFrame(pot_records), use_container_width=True)
                else: st.info("Nessun cliente potenziale salvato al momento.")
            except: st.info("Foglio POTENZIALI vuoto.")
        else: st.error("Errore: Foglio POTENZIALI non trovato su Google Sheets.")

        st.divider()

        st.markdown("### 🛰️ Radar Singolo (Verifica al volo 150m)")
        c_r1, c_r2 = st.columns(2)
        with c_r1: n_nome = st.text_input("Nome:", placeholder="Es. Bar Centrale")
        with c_r2: n_piva = st.text_input("P.IVA:", placeholder="Opzionale")
        c_r3, c_r4 = st.columns(2)
        with c_r3: n_ind = st.text_input("Indirizzo:", placeholder="Es. Via Roma 15")
        with c_r4: n_com = st.selectbox("Comune:", sorted(df[c_com].unique()))
        
        if st.button("📡 VERIFICA DISTANZA PEDONALE", type="primary", use_container_width=True) and n_ind and n_nome:
            with st.spinner("Calcolo verso la rete Premium..."):
                t_res = get_geo_data([f"{n_ind}, {n_com}, Italy"])
                t_coords = t_res['coords'] if t_res else None
                
                if t_coords:
                    df_prem = df[df[c_prem].str.upper().str.contains("SI", na=False)].copy()
                    violazione = False; vicini = []
                    for _, row in df_prem.iterrows():
                        p_res = get_geo_data([f"{row[c_ind]}, {row[c_com]}, Italy"], fallback_city=row[c_com])
                        p_c = p_res['coords'] if p_res else None
                        if p_c:
                            dist = get_walking_distance(t_coords, p_c)
                            if dist < 150: violazione = True; vicini.append(f"{row[c_nom]} ({dist} m)")
                    
                    if violazione: st.markdown(f"<div class='radar-no'>❌ Troppo vicino a: {', '.join(vicini)}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='radar-ok'>✅ OK! Oltre 150m dai Premium.</div>", unsafe_allow_html=True)
                        if st.button("💾 SALVA IN POTENZIALI", use_container_width=True):
                            ws_pot.append_row([datetime.now().strftime("%d/%m/%Y"), n_piva, n_nome, n_ind, n_com, "OK (Singolo)", ""])
                            st.success("Salvato!")
                else: st.error("Indirizzo non trovato sulla mappa.")

        st.divider()
        
        # --- CARICAMENTO FILE TELEMACO ---
        st.markdown("### 📂 Carica Lista Telemaco/InfoCamere")
        st.write("Carica il file Excel delle nuove aperture. L'IA rimuoverà i già clienti e calcolerà i 150m.")
        
        file_tel = st.file_uploader("Trascina qui il file (Excel o CSV)", type=['xlsx', 'xls', 'csv'])
        
        if file_tel:
            try:
                if file_tel.name.endswith('.csv'):
                    try: df_tel = pd.read_csv(file_tel, sep=';', encoding='latin1', dtype=str)
                    except:
                        file_tel.seek(0)
                        df_tel = pd.read_csv(file_tel, sep=',', encoding='utf-8', dtype=str)
                else:
                    df_tel = pd.read_excel(file_tel, dtype=str)
                
                st.success("File letto correttamente!")
                st.write("👀 **Anteprima del file caricato:**")
                st.dataframe(df_tel.head(3), use_container_width=True)
                
                st.markdown("#### ⚙️ Associa le Colonne")
                c_t1, c_t2, c_t3 = st.columns(3)
                
                idx_nome = list(df_tel.columns).index('Denominazione') if 'Denominazione' in df_tel.columns else 0
                with c_t1: col_nome_tel = st.selectbox("Colonna NOME AZIENDA:", df_tel.columns, index=idx_nome)
                
                idx_comune = list(df_tel.columns).index('Comune') if 'Comune' in df_tel.columns else 0
                with c_t2: col_com_tel = st.selectbox("Colonna COMUNE:", df_tel.columns, index=idx_comune)
                
                opzioni_piva = ["Nessuna"] + list(df_tel.columns)
                idx_piva_def = opzioni_piva.index('Partita IVA') if 'Partita IVA' in opzioni_piva else (opzioni_piva.index('P.IVA') if 'P.IVA' in opzioni_piva else 0)
                with c_t3: col_piva_tel = st.selectbox("Colonna PARTITA IVA:", opzioni_piva, index=idx_piva_def)
                
                st.markdown("<hr style='border:1px solid rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
                st.markdown("#### 🎯 Seleziona le tue zone:")
                
                comuni_nel_file = sorted(df_tel[col_com_tel].astype(str).str.upper().str.strip().unique().tolist())
                comuni_db_puliti = [pulisci_nome(c) for c in df[c_com].dropna().astype(str).unique()]
                
                default_sel = [c_tel_name for c_tel_name in comuni_nel_file if pulisci_nome(c_tel_name) in comuni_db_puliti]
                comuni_selezionati = st.multiselect("L'IA analizzerà SOLO i comuni che scegli qui sotto:", comuni_nel_file, default=default_sel)
                
                st.markdown("<br>", unsafe_allow_html=True)
                usa_filtro_cap = st.checkbox("📮 Usa il Filtro CAP", value=False)
                if usa_filtro_cap: col_cap_tel = st.selectbox("Colonna CAP:", list(df_tel.columns), index=list(df_tel.columns).index('Cap') if 'Cap' in df_tel.columns else 0)
                else: col_cap_tel = None
                
                if st.button("🚀 AVVIA SCANSIONE IA SULLA LISTA", type="primary", use_container_width=True):
                    if not comuni_selezionati:
                        st.error("⚠️ Seleziona almeno un comune dalla lista qui sopra prima di avviare!")
                    else:
                        st.info("Inizio scansione... (Calcolo Mappe e 150m in corso. Può richiedere qualche minuto)")
                        
                        df_prem = df[df[c_prem].str.upper().str.contains("SI", na=False)].copy()
                        nomi_esistenti_puliti = [pulisci_nome(n) for n in df[c_nom].astype(str).tolist()]
                        pive_esistenti = [str(p).strip() for p in df[c_piva].astype(str).tolist()] if c_piva else []
                        
                        mappa_zone = {}
                        for comune, cap_list in df.groupby(c_com)[c_cap].unique().items():
                            if pd.isna(comune) or not str(comune).strip(): continue
                            mappa_zone[pulisci_nome(str(comune))] = [str(c).replace('.0','').strip().zfill(5) for c in cap_list if pd.notna(c) and str(c).strip() != ""]
                        
                        risultati_positivi = []
                        scartati_zona = 0
                        scartati_clienti = 0
                        scartati_radar = 0
                        scartati_gps = 0 
                        
                        debug_cap_scartati = []
                        prog_tel = st.progress(0)
                        
                        for idx, riga in df_tel.iterrows():
                            try:
                                prog_tel.progress((idx + 1) / len(df_tel))
                                n_az = str(riga[col_nome_tel]).strip()
                                n_az_pulito = pulisci_nome(n_az)
                                
                                comune_target = str(riga[col_com_tel]).upper().strip()
                                cap_target = str(riga[col_cap_tel]).replace('.0', '').strip().zfill(5) if col_cap_tel else ""
                                
                                if 'Toponimo' in df_tel.columns and 'Via' in df_tel.columns and 'N civico' in df_tel.columns:
                                    ind_target = f"{str(riga['Toponimo']).strip()} {str(riga['Via']).strip()} {str(riga['N civico']).replace('.0','').strip()}".replace('nan', '').strip()
                                elif 'Indirizzo' in df_tel.columns:
                                    ind_target = str(riga['Indirizzo']).strip()
                                else:
                                    ind_target = ""
                                    
                                if comune_target not in comuni_selezionati:
                                    scartati_zona += 1
                                    continue
                                    
                                if usa_filtro_cap and cap_target:
                                    comune_tel_pulito = pulisci_nome(comune_target)
                                    caps_ammessi = mappa_zone.get(comune_tel_pulito, [])
                                    if len(caps_ammessi) > 0 and cap_target not in caps_ammessi:
                                        scartati_zona += 1
                                        debug_cap_scartati.append(f"{comune_target} (CAP {cap_target} scartato)")
                                        continue
                                    
                                se_piva = str(riga[col_piva_tel]).strip() if col_piva_tel and col_piva_tel != "Nessuna" else ""
                                is_gia_cliente = False
                                if se_piva and se_piva in pive_esistenti and se_piva != "nan":
                                    is_gia_cliente = True
                                else:
                                    if n_az_pulito in nomi_esistenti_puliti:
                                        is_gia_cliente = True
                                
                                if is_gia_cliente:
                                    scartati_clienti += 1
                                    continue 
                                    
                                # --- LA CORREZIONE CHE SALVA I 116 BAR ---
                                t_res = get_geo_data([f"{ind_target}, {riga[col_com_tel]}, Italy"])
                                t_coords = t_res['coords'] if t_res else None
                                
                                if t_coords:
                                    violazione = False
                                    for _, p_row in df_prem.iterrows():
                                        p_res = get_geo_data([f"{p_row[c_ind]}, {p_row[c_com]}, Italy"], fallback_city=p_row[c_com])
                                        p_c = p_res['coords'] if p_res else None
                                        
                                        if p_c and get_walking_distance(t_coords, p_c) < 150:
                                            violazione = True
                                            break
                                    
                                    if not violazione:
                                        risultati_positivi.append([datetime.now().strftime("%d/%m/%Y"), se_piva, n_az, ind_target, str(riga[col_com_tel]), "✅ OK (150m Superati)", f"CAP: {cap_target}"])
                                    else:
                                        scartati_radar += 1
                                else:
                                    scartati_gps += 1
                                    risultati_positivi.append([datetime.now().strftime("%d/%m/%Y"), se_piva, n_az, ind_target, str(riga[col_com_tel]), "⚠️ Mappa Fallita (Verifica a mano)", f"CAP: {cap_target}"])
                            except Exception as inner_e:
                                continue
                                
                        prog_tel.empty()
                        
                        st.markdown("### 📊 Report Scansione")
                        c_rep1, c_rep2, c_rep3, c_rep4 = st.columns(4)
                        c_rep1.metric("🌍 Comuni/CAP Ignorati", scartati_zona)
                        c_rep2.metric("👥 Già Clienti", scartati_clienti)
                        c_rep3.metric("🔴 < 150m", scartati_radar)
                        c_rep4.metric("⚠️ Mappe Fallite", scartati_gps)
                        
                        if debug_cap_scartati:
                            with st.expander("🔍 DEBUG: Vedi i CAP scartati su città valide"):
                                st.write(list(set(debug_cap_scartati)))
                        
                        if risultati_positivi:
                            st.success(f"🎯 BERSAGLIO! Trovati {len(risultati_positivi)} target potenziali liberi!")
                            try:
                                for r in risultati_positivi: ws_pot.append_row(r)
                                st.balloons()
                                st.info("Ricarica la pagina: i bar sono stati aggiunti alla tabella in alto e salvati su Excel.")
                            except Exception as e_sheet:
                                st.error("Trovati, ma c'è stato un problema nel salvarli su Google Sheet. Riprova.")
                        else:
                            st.warning("Nessun target valido in questo file (Tutti fuori zona, già clienti o a meno di 150m dai tuoi Premium).")
            except Exception as e:
                st.error(f"Errore critico: Assicurati che il file non sia corrotto o bloccato da Excel.")
