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
st.set_page_config(page_title="BETA - Brightstar CRM", page_icon="🧪", layout="wide")
TZ_ITALY = pytz.timezone('Europe/Rome')

# ==============================================================================
# 🔒 CONFIGURAZIONE DATI GIAMBATTISTA (V5.61 BETA - HUD + SCORING P.IVA)
# ==============================================================================
PIN_SEGRETO = "Takira74,1974"  
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" 
LA_TUA_EMAIL = "giambattista.giacchetti@gmail.com" 
CANALE_NTFY = "giamba_g2_crm_2026" 
# ==============================================================================

if "autenticato" not in st.session_state: st.session_state.autenticato = False

if not st.session_state.autenticato:
    st.markdown("""
        <style>
        .stApp { background: radial-gradient(circle at center, #0f172a 0%, #000000 100%); color: #f1f5f9; font-family: 'Inter', sans-serif;}
        .login-box { max-width: 400px; margin: 100px auto; background: #1e293b; padding: 40px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); text-align: center; border: 1px solid #334155;}
        </style>
    """, unsafe_allow_html=True)
    st.markdown("<div class='login-box'><h1 style='font-size: 3rem; margin-bottom: 0;'>🤖</h1><h2>AREA BETA v5.61</h2><p style='color: #94a3b8; margin-bottom: 20px;'>Accesso Protetto (Auto-HUD).</p>", unsafe_allow_html=True)
    pin_inserito = st.text_input("PIN:", type="password")
    if st.button("🔓 ACCEDI", type="primary", use_container_width=True):
        if pin_inserito == PIN_SEGRETO:
            st.session_state.autenticato = True
            st.rerun()
        else: st.error("❌ PIN Errato.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# --- 🎨 DESIGN ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    .stApp { font-family: 'Inter', sans-serif; background: radial-gradient(circle at top left, #1e293b 0%, #0f172a 100%); color: #f1f5f9; }
    .app-header { background: linear-gradient(90deg, #f59e0b, #ef4444); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.5rem; font-weight: 800; text-align: center; margin-bottom: 30px;}
    .client-card { background: linear-gradient(145deg, rgba(30, 41, 59, 0.85), rgba(15, 23, 42, 0.9)); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 20px; padding: 24px; margin-bottom: 16px; box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5);}
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 12px; }
    .arrival-time { background: linear-gradient(135deg, #3b82f6, #6366f1); color: white; padding: 6px 16px; border-radius: 30px; font-weight: 700; }
    .strategy-box { padding: 12px 16px; border-radius: 10px; margin-bottom: 18px; font-size: 0.95em; border-left: 5px solid; background: rgba(0,0,0,0.25); }
    .info-row { display: flex; flex-wrap: wrap; gap: 10px; color: #94a3b8; font-size: 0.9rem; margin-bottom: 15px; font-weight: 500;}
    .info-tag { background: rgba(255, 255, 255, 0.05); padding: 4px 10px; border-radius: 6px; border: 1px solid rgba(255, 255, 255, 0.1); }
    .badge-potenziale { background: rgba(16, 185, 129, 0.2); color: #34d399; padding: 5px 12px; border-radius: 8px; font-weight: bold; border: 1px solid rgba(16, 185, 129, 0.5);}
    .prem-badge { background: rgba(245, 158, 11, 0.2); color: #fbbf24; padding: 5px 12px; border-radius: 8px; font-weight: bold; border: 1px solid rgba(245, 158, 11, 0.5); }
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
        titoli = {w.title.strip().upper(): w for w in sh.worksheets()}
        return sh.get_worksheet(0), titoli.get("MEMORIA_GIRO"), titoli.get("POTENZIALI"), titoli.get("LOG_VISITE"), titoli.get("LOG_MERCATO"), titoli.get("DASHBOARD_G2")
    except: return None, None, None, None, None, None

def pulisci_nome_norm(nome):
    return str(nome).strip().upper()

def carica_storico_attivita_blindato(sh_memoria):
    try:
        raw = sh_memoria.get("D:E") 
        return {pulisci_nome_norm(row[0]): json.loads(row[1]) for row in raw[1:] if len(row) >= 2} if raw else {}
    except: return {}

def aggiorna_attivita_cliente_blindato(sh_memoria, cliente, tasks_list):
    try:
        raw = sh_memoria.get("D:E")
        records = raw if raw else []
        c_norm = pulisci_nome_norm(cliente)
        idx = -1
        for i, r in enumerate(records):
            if r and pulisci_nome_norm(r[0]) == c_norm:
                idx = i + 1
                break
        if idx != -1: sh_memoria.update_cell(idx, 5, json.dumps(tasks_list))
        else:
            n_row = len(sh_memoria.col_values(4)) + 1
            sh_memoria.update_cell(n_row, 4, cliente)
            sh_memoria.update_cell(n_row, 5, json.dumps(tasks_list))
    except: pass

def pulisci_coordinata_italy(c_str, is_lat=True):
    if pd.isna(c_str) or str(c_str).strip() == "": return None
    c = str(c_str).strip().replace(' ', '').replace(',', '.')
    try: 
        val = float(c)
        if abs(val) > 100:
            while abs(val) > 90: val = val / 10.0
        return val if (35 < val < 48 if is_lat else 6 < val < 20) else None
    except: return None

def optimize_route_2opt(pool, start):
    if not pool: return []
    opt, curr, unv = [], start, pool.copy()
    while unv:
        nxt = min(unv, key=lambda x: math.sqrt(((curr[1]-x['coords'][1])*81000)**2 + ((curr[0]-x['coords'][0])*111320)**2))
        opt.append(nxt); curr = nxt['coords']; unv.remove(nxt)
    return opt

def get_geo_data(queries):
    time.sleep(0.3)
    for q in queries:
        try:
            url = f"https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?singleLine={requests.utils.quote(q)}&f=json&maxLocations=1"
            res = requests.get(url, timeout=4).json()
            if res.get('candidates'): return (res['candidates'][0]['location']['y'], res['candidates'][0]['location']['x'])
        except: continue
    return None

def salva_giro_memoria_json(ws_mem, rotta):
    if not ws_mem: return
    try:
        r_c = copy.deepcopy(rotta)
        for p in r_c:
            if isinstance(p.get('arr'), datetime): p['arr'] = p['arr'].strftime("%Y-%m-%d %H:%M:%S")
        ws_mem.update_acell("B2", json.dumps(r_c))
    except: pass

def carica_giro_da_foglio_json(ws_mem):
    try:
        js = ws_mem.acell("B2").value
        if js:
            r = json.loads(js)
            for p in r:
                if 'arr' in p and isinstance(p['arr'], str): p['arr'] = datetime.strptime(p['arr'], "%Y-%m-%d %H:%M:%S")
                if 'coords' not in p: p['coords'] = SEDE_COORDS
                if 'tasks_completed' not in p: p['tasks_completed'] = []
            return r
    except: return None
    return None

def agente_strategico(note):
    if not note: return "Nessuno storico recente.", "border-left-color: #475569;"
    txt = str(note).lower()
    if any(x in txt for x in ['arrabbiato', 'reclamo']): return "⚠️ ATTENZIONE: Cliente a rischio.", "border-left-color: #ef4444;"
    return f"MEMO: {note[:60]}...", "border-left-color: #3b82f6;"

# 🎯 FUNZIONE PUSH DIRECT NTFY
def invia_notifica_push(cliente, indirizzo, nota):
    try:
        url = f"https://ntfy.sh/{CANALE_NTFY}"
        messaggio = f"{cliente} | {indirizzo}\nNote: {nota}"
        headers = {"Title": "Tappa Aggiornata", "Tags": "eyeglasses"}
        requests.post(url, data=messaggio.encode('utf-8'), headers=headers, timeout=3)
    except:
        pass

# 🎯 FUNZIONE MAGICA FULL AUTO PER G2
def aggiorna_lente_g2(ws_dash, rotta_rimanente, c_nom, c_ind, c_com, c_note_sto, c_prem):
    if not ws_dash: return
    try:
        if len(rotta_rimanente) > 0:
            prossimo = rotta_rimanente[0]
            nome = str(prossimo.get(c_nom, ''))
            indirizzo = f"{prossimo.get(c_ind, '')}, {prossimo.get(c_com, '')}"
            is_prem = str(prossimo.get(c_prem, '')).upper() == 'SI'
            badge = "[PREMIUM] " if is_prem else ""
            
            nota_grezza = str(prossimo.get(c_note_sto, ''))
            nota_pulita = nota_grezza[:50] + "..." if len(nota_grezza) > 50 else (nota_grezza if nota_grezza else "Standard")
            
            ws_dash.update('A2:C2', [[badge + nome, indirizzo, nota_pulita]])
            invia_notifica_push(badge + nome, indirizzo, nota_pulita)
        else:
            ws_dash.update('A2:C2', [['GIRO FINITO', 'Torna alla base', 'Ottimo lavoro!']])
            invia_notifica_push("GIRO FINITO", "Torna alla base", "Ottimo lavoro!")
    except: pass

# --- AVVIO APP ---
ws, ws_mem, ws_pot, ws_log, ws_mer, ws_dash = connect_db()

if ws:
    data = ws.get_all_values()
    headers = [h.strip().upper() for h in data[0]]
    df = pd.DataFrame(data[1:], columns=headers)
    
    # Mappatura Colonne
    c_nom = next(c for c in df.columns if "CLIENTE" in c)
    c_ind = next(c for c in df.columns if "INDIRIZZO" in c or "VIA" in c)
    c_com = next(c for c in df.columns if "COMUNE" in c)
    c_vis = next(c for c in df.columns if "VISITATO" in c)
    c_prem = next((c for c in df.columns if "PREMIUM" in c), None)
    c_lat = next((c for c in df.columns if "LAT" in c.upper()), None)
    c_lon = next((c for c in df.columns if "LON" in c.upper()), None)
    c_att = next((c for c in df.columns if "ATTIVIT" in c), None)
    c_tel = next((c for c in df.columns if "TELEFONO" in c or "CELL" in c or "TEL" in c), None)
    c_piva = next((c for c in df.columns if "P.IVA" in c or "PIVA" in c), None)
    c_codice = next((c for c in df.columns if "CODICE" in c.upper() or "COD " in c.upper() or "COD." in c.upper()), None)
    c_pos = next((c for c in df.columns if "POS" in c.upper() or "DB_POS" in c.upper() or "DB" in c.upper()), None)
    c_note_sto = next((c for c in df.columns if "STORICO" in c or "NOTE" in c), None)
    c_cap = next((c for c in df.columns if "CAP" in c), None)
    
    if c_cap:
        df[c_cap] = df[c_cap].astype(str).str.replace('.0', '', regex=False).str.replace('nan', '').str.strip()
        df[c_cap] = df[c_cap].apply(lambda x: x.zfill(5) if x else '')
    
    if 'master_route' not in st.session_state and ws_mem: 
        st.session_state.master_route = carica_giro_da_foglio_json(ws_mem)
    
    if 'db_tasks' not in st.session_state:
        st.session_state.db_tasks = carica_storico_attivita_blindato(ws_mem)

    st.markdown("<div class='app-header'>🚀 BRIGHTSTAR CRM v5.61 <span style='font-size:0.8rem;'>HUD AUTO</span></div>", unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs(["🚗 GIRO & SCOUTING", "🛰️ RADAR", "📊 REPORT"])

    with tab1:
        st.sidebar.markdown("### 🗺️ Opzioni Giro")
        ind_start = st.sidebar.text_input("📍 Partenza:", value="")
        num_v = st.sidebar.slider("Clienti DB:", 1, 30, 8)
        only_premium = st.sidebar.toggle("💎 Solo PREMIUM", value=True)
        sel_zona_giro = st.sidebar.multiselect("🌍 Filtra Comune:", sorted([str(c).strip() for c in df[c_com].unique() if str(c).strip()]))
        sel_cap_giro = []
        if c_cap:
            lista_cap = sorted([str(x).strip() for x in df[c_cap].unique() if str(x).strip()])
            sel_cap_giro = st.sidebar.multiselect("📮 Filtra CAP:", lista_cap)
            
        st.sidebar.divider()
        if st.sidebar.button("🔄 SINCRONIZZA MEMORIA"):
            st.session_state.db_tasks = carica_storico_attivita_blindato(ws_mem)
            st.rerun()
            
        num_p = st.sidebar.slider("🆕 Potenziali:", 0, 5, 1)

        if st.button("🔄 GENERA GIRO AGGIORNATO", type="primary", use_container_width=True):
            with st.spinner("Sincronizzazione dati e calcolo in corso..."):
                st.session_state.db_tasks = carica_storico_attivita_blindato(ws_mem)
                mask = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
                if sel_zona_giro: mask &= df[c_com].astype(str).str.strip().str.upper().isin([z.upper() for z in sel_zona_giro])
                if sel_cap_giro: mask &= df[c_cap].astype(str).str.strip().isin([c.strip() for c in sel_cap_giro])
                if only_premium and c_prem: mask &= df[c_prem].astype(str).str.upper().str.contains('SI', na=False)
                
                clienti_cg_completati = [n for n, tasks in st.session_state.db_tasks.items() if any("CG" in str(t).upper() for t in tasks)]
                mask &= ~df[c_nom].apply(lambda x: pulisci_nome_norm(x)).isin(clienti_cg_completati)
                
                raw_pool = df[mask].drop_duplicates(subset=[c_nom]).head(num_v).to_dict('records')
                for p in raw_pool: 
                    p['is_potenziale'] = False
                    p['tasks_completed'] = copy.deepcopy(st.session_state.db_tasks.get(pulisci_nome_norm(p[c_nom]), []))
                
                if num_p > 0 and ws_pot:
                    pot_d = ws_pot.get_all_values()
                    count_p = 0
                    for r_idx, row in enumerate(pot_d[1:]):
                        comune_pot = str(row[3]).strip().upper() if len(row) > 3 else ""
                        if sel_zona_giro:
                            comuni_selezionati = [z.upper() for z in sel_zona_giro]
                            if comune_pot not in comuni_selezionati:
                                continue 
                        
                        stato_pot = str(row[4]).strip().upper() if len(row) > 4 else ""
                        note_pot = str(row[7]).strip() if len(row) > 7 else ""

                        # Aggiunge al giro solo se ha la spunta ✅
                        if "✅" in stato_pot:
                            nota_storico = note_pot if note_pot else "Scouting Nuovo"
                            raw_pool.append({
                                c_nom: row[1], 
                                c_ind: row[2], 
                                c_com: row[3], 
                                'is_potenziale': True, 
                                'row_idx': r_idx+2, 
                                'tasks_completed': [],
                                c_note_sto: nota_storico,
                                c_prem: 'NO'
                            })
                            count_p += 1
                            if count_p >= num_p: break

                for p in raw_pool:
                    la, lo = pulisci_coordinata_italy(p.get(c_lat), True), pulisci_coordinata_italy(p.get(c_lon), False)
                    p['coords'] = (la, lo) if la and lo else get_geo_data([f"{p[c_ind]}, {p[c_com]}, Italy"]) or SEDE_COORDS

                start_c = get_geo_data([ind_start]) if ind_start else (raw_pool[0]['coords'] if raw_pool else SEDE_COORDS)
                st.session_state.master_route = optimize_route_2opt(raw_pool, start_c)
                salva_giro_memoria_json(ws_mem, st.session_state.master_route)
                
                aggiorna_lente_g2(ws_dash, st.session_state.master_route, c_nom, c_ind, c_com, c_note_sto, c_prem)
                st.rerun()

        if st.session_state.get('master_route'):
            for i, p in enumerate(st.session_state.master_route):
                is_pot = p.get('is_potenziale', False)
                is_premium = True if c_prem and str(p.get(c_prem, '')).upper() == 'SI' else False
                badge_html = "<span class='badge-potenziale'>🆕 POTENZIALE</span>" if is_pot else ("<span class='prem-badge'>💎 PREMIUM</span>" if is_premium else "<span style='background:#475569; color:white; padding:5px 12px; border-radius:8px; font-weight:bold;'>STANDARD</span>")
                st.markdown(f"<div class='client-card'><div class='card-header'><div>{badge_html}</div></div><div style='font-size:1.3rem; font-weight:bold;'>{p[c_nom]}</div>", unsafe_allow_html=True)
                pronto = True
                
                if not is_pot:
                    msg_c, style_c = agente_strategico(p.get(c_note_sto, ''))
                    st.markdown(f"<div class='strategy-box' style='{style_c}'>{msg_c}</div>", unsafe_allow_html=True)
                    tel = str(p.get(c_tel, '')).replace('nan', '').strip()
                    info_h = "".join([f"<span class='info-tag'>{k}: {v}</span>" for k, v in {"P.IVA": p.get(c_piva), "Cod": p.get(c_codice), "📞": tel}.items() if v and str(v).lower() != 'nan'])
                    st.markdown(f"<div class='info-row'>{info_h}</div>", unsafe_allow_html=True)
                    tasks_done = p.get('tasks_completed', [])
                    if c_att in p:
                        t_list = [t.strip() for t in str(p[c_att]).split(',') if t.strip()]
                        for t in t_list:
                            if ("CG" in t.upper() or "CD" in t.upper()) and not is_premium:
                                st.markdown(f"<div style='color:#64748b; font-style:italic;'>🚫 {t} (Solo Premium)</div>", unsafe_allow_html=True)
                                if t in tasks_done: tasks_done.remove(t)
                            else:
                                chk = st.checkbox(t, value=(t in tasks_done), key=f"t_{i}_{t}_{p[c_nom]}")
                                if chk and t not in tasks_done: tasks_done.append(t)
                                elif not chk and t in tasks_done: tasks_done.remove(t)
                        p['tasks_completed'] = tasks_done
                        if is_premium and any("CG" in t.upper() for t in t_list): pronto = any("CG" in t.upper() for t in tasks_done)
                else:
                    # Per i potenziali mostriamo la nota di P.IVA e scoring precedente se esiste
                    nota_p = p.get(c_note_sto, '')
                    if "Score" in nota_p or "P.IVA" in nota_p:
                        colore_bordo = "#f59e0b" # Giallo default
                        if "🟢" in nota_p: colore_bordo = "#10b981"
                        elif "🔴" in nota_p: colore_bordo = "#ef4444"
                        st.markdown(f"<div class='strategy-box' style='border-left-color: {colore_bordo};'>⚠️ INFO: {nota_p}</div>", unsafe_allow_html=True)

                st.markdown(f"<div style='color:#94a3b8; margin-bottom:10px;'>📍 {p[c_ind]}, {p[c_com]}</div>", unsafe_allow_html=True)
                col1, col2, col3 = st.columns([1, 1, 2])
                with col1: st.link_button("🚙 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={p['coords'][0]},{p['coords'][1]}", use_container_width=True)
                with col2: 
                    if not is_pot and tel: st.link_button("📞 CHIAMA", f"tel:{tel}", use_container_width=True)
                    else: st.button("📞 NO TEL", disabled=True, use_container_width=True)
                with col3:
                    if not is_pot:
                        btn_testo = "✅ CONCLUDI" if pronto else "⚠️ MANCA CG"
                        if st.button(btn_testo, key=f"btn_{i}_{p[c_nom]}", type="primary" if pronto else "secondary", use_container_width=True):
                            if not pronto: st.warning("Spunta 'CG' obbligatoria!")
                            else:
                                oggi = datetime.now(TZ_ITALY).strftime("%d/%m/%Y")
                                try:
                                    r_idx_real = df[df[c_nom] == p[c_nom]].index[0] + 2
                                    ws.update_cell(r_idx_real, headers.index(c_vis)+1, "SI")
                                except: pass
                                if ws_mem: aggiorna_attivita_cliente_blindato(ws_mem, p[c_nom], p['tasks_completed'])
                                if ws_log: ws_log.append_row([oggi, p[c_nom], "CLIENTE DB", ", ".join(p['tasks_completed']) or "Visita Standard"])
                                
                                st.session_state.master_route.pop(i)
                                salva_giro_memoria_json(ws_mem, st.session_state.master_route)
                                
                                aggiorna_lente_g2(ws_dash, st.session_state.master_route, c_nom, c_ind, c_com, c_note_sto, c_prem)
                                st.rerun()
                    else:
                        st.markdown("<div style='text-align:center; padding-top:8px; color:#34d399; font-weight:bold;'>↓ COMPILA ESITO ↓</div>", unsafe_allow_html=True)

                # ==========================================
                # 🎯 PANNELLO ESITO SCOUTING PER POTENZIALI
                # ==========================================
                if is_pot:
                    st.markdown("<div style='background:rgba(0,0,0,0.25); padding:15px; border-radius:10px; margin-top:15px; border: 1px solid rgba(255,255,255,0.1);'>", unsafe_allow_html=True)
                    esito_scelta = st.selectbox("🎯 Fase della trattativa:", ["Seleziona...", "🔍 In Trattativa / Verifica Creditizia", "🎉 Contratto Firmato", "❌ Non Interessato (Scarta)"], key=f"esito_{i}_{p[c_nom]}")
                    
                    piva_input = ""
                    scoring_scelta = ""
                    
                    if esito_scelta in ["🔍 In Trattativa / Verifica Creditizia", "🎉 Contratto Firmato"]:
                        st.markdown("##### ⚖️ Controllo Scoring Aziendale")
                        piva_input = st.text_input("Partita IVA del cliente:", key=f"piva_{i}_{p[c_nom]}")
                        scoring_scelta = st.radio("Esito Scoring:", ["🟢 Verde", "🟡 Giallo", "🔴 Rosso (KO)"], horizontal=True, key=f"score_{i}_{p[c_nom]}")
                        
                        if scoring_scelta == "🔴 Rosso (KO)":
                            st.error("⚠️ SCORING ROSSO: Il cliente verrà scartato e rimosso definitivamente dai giri futuri.")

                    if esito_scelta != "Seleziona...":
                        if st.button("💾 REGISTRA ESITO E PROCEDI", key=f"btn_pot_salva_{i}_{p[c_nom]}", type="primary", use_container_width=True):
                            oggi = datetime.now(TZ_ITALY).strftime("%d/%m/%Y")
                            if ws_pot:
                                riga = p['row_idx']
                                note_finali = f"P.IVA: {piva_input} | Score: {scoring_scelta}" if piva_input or scoring_scelta else ""
                                
                                # LOGICA DEL CANCELLO (Il GATEKEEPER)
                                if esito_scelta == "❌ Non Interessato (Scarta)" or scoring_scelta == "🔴 Rosso (KO)":
                                    esito_txt = "Scartato (Scoring Rosso)" if scoring_scelta == "🔴 Rosso (KO)" else "Non Interessato"
                                    ws_pot.update(f"E{riga}:H{riga}", [["KO", oggi, esito_txt, note_finali]])
                                elif esito_scelta == "🎉 Contratto Firmato":
                                    ws_pot.update(f"E{riga}:H{riga}", [["VENDUTO", oggi, "Contratto Firmato", note_finali]])
                                else:
                                    ws_pot.update(f"E{riga}:H{riga}", [["✅", oggi, "In Trattativa", note_finali]])
                            
                            if ws_log: 
                                ws_log.append_row([oggi, p[c_nom], "POTENZIALE", f"{esito_scelta} {scoring_scelta}".strip()])
                            
                            st.session_state.master_route.pop(i)
                            salva_giro_memoria_json(ws_mem, st.session_state.master_route)
                            aggiorna_lente_g2(ws_dash, st.session_state.master_route, c_nom, c_ind, c_com, c_note_sto, c_prem)
                            st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

            st.divider()
            with st.expander("➕ AGGIUNGI CLIENTE AL VOLO"):
                nomi_esistenti = [p[c_nom] for p in st.session_state.master_route]
                clienti_cg_completati = [n for n, tasks in st.session_state.db_tasks.items() if any("CG" in str(t).upper() for t in tasks)]
                clienti_disp = sorted(df[~df[c_nom].isin(nomi_esistenti) & ~df[c_nom].apply(lambda x: pulisci_nome_norm(x)).isin(clienti_cg_completati)][c_nom].dropna().unique().tolist())
                scelto = st.selectbox("Seleziona bar:", [""] + clienti_disp)
                if st.button("⚡ INSERISCI") and scelto:
                    p_new = df[df[c_nom] == scelto].iloc[0].to_dict()
                    p_new['is_potenziale'] = False
                    p_new['tasks_completed'] = copy.deepcopy(st.session_state.db_tasks.get(pulisci_nome_norm(scelto), []))
                    la, lo = pulisci_coordinata_italy(p_new.get(c_lat), True), pulisci_coordinata_italy(p_new.get(c_lon), False)
                    p_new['coords'] = (la, lo) if la and lo else get_geo_data([f"{p_new[c_ind]}, {p_new[c_com]}, Italy"]) or SEDE_COORDS
                    st.session_state.master_route.insert(0, p_new) 
                    salva_giro_memoria_json(ws_mem, st.session_state.master_route)
                    
                    aggiorna_lente_g2(ws_dash, st.session_state.master_route, c_nom, c_ind, c_com, c_note_sto, c_prem)
                    st.rerun()

            with st.expander("🕵️ SCOUTING E NUOVI CONTRATTI"):
                with st.form("scout"):
                    n_s = st.text_input("Nome Bar *")
                    v_s = st.text_input("Indirizzo *")
                    c_s = st.text_input("Comune *")
                    piva_s = st.text_input("P.IVA (Opzionale)")
                    e_s = st.selectbox("Esito *", ["Interessato / Da Verificare", "Contratto GeV FIRMATO! 🎉", "Non Interessato / Scoring Rosso"])
                    if st.form_submit_button("💾 SALVA SCOUTING"):
                        oggi = datetime.now(TZ_ITALY).strftime("%d/%m/%Y")
                        log_t = "HUNTING, GEV, PREMIUM, CD, CG, DIGITAL" if "FIRMATO" in e_s else f"HUNTING - {e_s}"
                        
                        stato_pot_s = "KO" if ("Non" in e_s or "Rosso" in e_s) else "✅"
                        if "FIRMATO" in e_s: stato_pot_s = "VENDUTO"
                        
                        nota_pot_s = f"P.IVA: {piva_s}" if piva_s else ""
                        
                        if ws_pot: ws_pot.append_row([oggi, n_s, v_s, c_s, stato_pot_s, oggi, e_s, nota_pot_s, ""])
                        if ws_log: ws_log.append_row([oggi, n_s, "POTENZIALE", log_t])
                        st.success("Salvato!")

            st.divider()
            with st.expander("🎙️ ANNOTAZIONI MERCATO (Per Irene)"):
                st.info("💡 Usa il Microfono della tastiera per dettare la tua nota!")
                with st.form("form_mercato"):
                    cat_m = st.selectbox("Categoria:", ["Concorrenza", "Problematiche Piattaforma", "Feedback Clienti", "Altro"])
                    nota_m = st.text_area("Cosa succede sul campo?", height=100)
                    if st.form_submit_button("💾 SALVA NOTA"):
                        if nota_m and ws_mer:
                            ws_mer.append_row([datetime.now(TZ_ITALY).strftime("%d/%m/%Y"), cat_m, nota_m])
                            st.success("✅ Nota salvata!")

    with tab2: st.write("Funzione Radar")

    with tab3:
        if st.button("🔄 GENERA REPORT WHATSAPP (CAPO)", type="primary", use_container_width=True):
            if ws_log:
                d = ws_log.get_all_values()
                rep = {"GeV_W":0, "GeV_Y":0, "Prem_W":0, "Prem_Y":0, "Hunt_W":0, "Car_W":0, "Dis_W":0, "Vol_W":0, "DS_W":0, "DS_Y":57, "CD_W":0, "CD_Y":442, "CG_W":0, "CG_Y":232, "VV_W":0, "VV_Y":11}
                sett_start = datetime.now(TZ_ITALY) - timedelta(days=datetime.now(TZ_ITALY).weekday())
                for r in d[1:]:
                    try:
                        dt = datetime.strptime(r[0], "%d/%m/%Y").replace(tzinfo=TZ_ITALY)
                        t = r[3].upper()
                        if dt.year == 2026:
                            if "GEV" in t: rep["GeV_Y"] += 1
                            if "PREMIUM" in t: rep["Prem_Y"] += 1
                            if "DS" in t: rep["DS_Y"] += 1
                            if "CD" in t: rep["CD_Y"] += 1
                            if "CG" in t: rep["CG_Y"] += 1
                            if "VINCITE" in t: rep["VV_Y"] += 1
                        if dt >= sett_start.replace(hour=0):
                            if "GEV" in t: rep["GeV_W"] += 1
                            if "PREMIUM" in t: rep["Prem_W"] += 1
                            if "HUNTING" in t: rep["Hunt_W"] += 1
                            if "CARING" in t: rep["Car_W"] += 1
                            if "DISDETT" in t: rep["Dis_W"] += 1
                            if "VOLTURA" in t: rep["Vol_W"] += 1
                            if "DS" in t: rep["DS_W"] += 1
                            if "CD" in t: rep["CD_W"] += 1
                            if "CG" in t: rep["CG_W"] += 1
                            if "VINCITE" in t: rep["VV_W"] += 1
                    except: continue
                msg = f"Contratti GeV :{rep['GeV_W']}\n\nContratti Premium : {rep['Prem_W']}\n\ndi cui:\n  Hunting : {rep['Hunt_W']}\n  Caring : {rep['Car_W']}\n\nControdisdette : {rep['Dis_W']}\n  Voltura Padre/Figlio: {rep['Vol_W']}\n\nNoContratti DS : {rep['DS_W']}\nContratti DS totali dal 1/1/2026: {rep['DS_Y']}\n\nContratti Conto Deposito : {rep['CD_W']}\nContratti Conto Deposito dal 1/1/2026 :{rep['CD_Y']}\n\nContratti Conto Gioco : {rep['CG_W']}\nContratti Conto Gioco dal 1/1/2026 : {rep['CG_Y']}\n\nContratti Verifica Vincite : {rep['VV_W']}\nContratti Verifica Vincite dal 1/1/2026 :{rep['VV_Y']}"
                st.code(msg)
                st.markdown(f"<a href='https://wa.me/?text={requests.utils.quote(msg)}' target='_blank' style='background:#25D366; color:white; padding:10px; border-radius:8px; display:block; text-align:center; text-decoration:none;'>📲 INVIA AL CAPO</a>", unsafe_allow_html=True)

        st.divider()
        if st.button("📧 PREPARA REPORT PER IRENE (MAIL)", use_container_width=True):
            if ws_mer:
                d = ws_mer.get_all_values()
                body = "Buongiorno Irene,\n\nti condivido il riepilogo settimanale con i feedback dal mercato, le segnalazioni dei clienti e gli aggiornamenti sulla concorrenza raccolti in questi giorni:\n\n"
                sett_start = datetime.now(TZ_ITALY) - timedelta(days=datetime.now(TZ_ITALY).weekday())
                ha_n = False
                for r in d[1:]:
                    if datetime.strptime(r[0], "%d/%m/%Y").replace(tzinfo=TZ_ITALY) >= sett_start.replace(hour=0):
                        body += f"📌 {r[1].upper()}: {r[2]}\n"
                        ha_n = True
                if not ha_n: body += "Nessuna annotazione particolare questa settimana.\n"
                body += "\nResto a disposizione per qualsiasi approfondimento.\n\nBuon lavoro e un buon weekend,\nGiambattista"
                st.code(body)
                st.markdown(f"<a href='mailto:{LA_TUA_EMAIL}?subject=Report Mercato&body={requests.utils.quote(body)}' style='background:#3b82f6; color:white; padding:10px; border-radius:8px; display:block; text-align:center; text-decoration:none;'>✉️ RICEVI EMAIL DA INOLTRARE</a>", unsafe_allow_html=True)

