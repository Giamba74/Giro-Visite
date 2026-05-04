import streamlit as st
import pandas as pd
import numpy as np
from geopy.distance import geodesic
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import pytz
import json
import copy
import time
import re
import requests

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar CRM PRO", page_icon="💎", layout="wide")
TZ_ITALY = pytz.timezone('Europe/Rome')

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
    </style>
    """, unsafe_allow_html=True)

COORDS = { "Chianti": (43.661888, 11.305728), "Firenze": (43.7696, 11.2558), "Arezzo": (43.4631, 11.8781) }
SEDE_COORDS = COORDS["Chianti"]

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
        ws_mem = sh.worksheet("MEMORIA_GIRO") if "MEMORIA_GIRO" in [w.title for w in sh.worksheets()] else None
        ws_pot = sh.worksheet("POTENZIALI") if "POTENZIALI" in [w.title for w in sh.worksheets()] else None
        return ws_main, ws_mem, ws_pot
    except: return None, None, None

def carica_storico_attivita(sh_memoria):
    try:
        raw = sh_memoria.get("D:E") 
        return {row[0]: json.loads(row[1]) for row in raw[1:] if len(row) >= 2} if raw else {}
    except: return {}

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

def carica_giro_da_foglio(sh_memoria):
    try:
        json_data = sh_memoria.acell("B2").value
        if json_data:
            rotta = json.loads(json_data)
            for p in rotta:
                if 'arr' in p and isinstance(p['arr'], str):
                    p['arr'] = datetime.strptime(p['arr'], "%Y-%m-%d %H:%M:%S")
                if 'coords' not in p or p['coords'] is None: p['coords'] = SEDE_COORDS
                if 'tasks_completed' not in p: p['tasks_completed'] = []
            return rotta
    except: return None
    return None

def get_geo_data(query_list):
    time.sleep(0.5) 
    for q in query_list:
        try:
            url = f"https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?singleLine={requests.utils.quote(q)}&f=json&maxLocations=1"
            risposta = requests.get(url, timeout=8).json()
            if risposta.get('candidates') and len(risposta['candidates']) > 0:
                lat = risposta['candidates'][0]['location']['y']
                lon = risposta['candidates'][0]['location']['x']
                return (lat, lon)
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
ws, ws_mem, ws_pot = connect_db()
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
    c_codice = df.columns[7] if len(df.columns) > 7 else None
    c_pos = df.columns[12] if len(df.columns) > 12 else None
    
    c_cap = next((c for c in df.columns if "CAP" in c), None)
    if c_cap:
        df[c_cap] = df[c_cap].astype(str).str.replace('.0', '', regex=False).str.replace('nan', '').str.strip()
        df[c_cap] = df[c_cap].apply(lambda x: x.zfill(5) if x else '')

    if 'master_route' not in st.session_state and ws_mem:
        st.session_state.master_route = carica_giro_da_foglio(ws_mem)
        
    # Carica la memoria delle spunte passate
    if 'db_tasks' not in st.session_state and ws_mem: 
        st.session_state.db_tasks = carica_storico_attivita(ws_mem)

    st.markdown("<div class='app-header'>🚀 BRIGHTSTAR CRM PRO v5.29</div>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["🚗 GIRO VISITE & NUOVI", "🛰️ RADAR 150m & TELEMACO"])

    # ==========================================
    # TAB 1: GIRO VISITE 
    # ==========================================
    with tab1:
        st.sidebar.markdown("### 🗺️ Opzioni Giro")
        indirizzo_start = st.sidebar.text_input("📍 Partenza:", value="Chianti, Sede")
        num_visite = st.sidebar.slider("🚗 Clienti DB:", 1, 20, 5)
        only_premium = st.sidebar.toggle("💎 Solo PREMIUM", value=True)
        sel_zona_giro = st.sidebar.multiselect("🌍 Filtra Comune:", sorted([str(c) for c in df[c_com].unique() if str(c).strip()]))
        
        sel_cap_giro = []
        if c_cap:
            lista_cap = sorted([str(x) for x in df[c_cap].unique() if str(x).strip()])
            sel_cap_giro = st.sidebar.multiselect("📮 Filtra CAP:", lista_cap)
            
        st.sidebar.divider()
        st.sidebar.markdown("### 🎯 Sviluppo Rete")
        include_potenziali = st.sidebar.toggle("➕ Includi Potenziali nel Giro", value=True, help="Aggiunge al giro i nuovi bar trovati dal radar non ancora visitati.")

        if st.button("🔄 CALCOLA NUOVO GIRO OTTIMIZZATO", type="primary", use_container_width=True):
            with st.spinner("IA sta calcolando la rotta includendo i nuovi obiettivi..."):
                mask = ~df[c_vis].str.contains('SI|SÌ', case=False, na=False)
                if sel_zona_giro: mask &= df[c_com].isin(sel_zona_giro)
                if sel_cap_giro: mask &= df[c_cap].isin(sel_cap_giro)
                if only_premium and c_prem: mask &= df[c_prem].astype(str).str.upper().str.contains('SI', na=False)
                
                pool = df[mask].head(num_visite).to_dict('records')
                for p in pool: p['is_potenziale'] = False
                
                if include_potenziali and ws_pot:
                    try:
                        pot_recs = ws_pot.get_all_records()
                        for r_idx, r in enumerate(pot_recs):
                            if not r.get("DATA_VISITA") and r.get("STATO", "") == "✅ DISPONIBILE":
                                passa_filtro_cap = True
                                if sel_cap_giro:
                                    addr_pot = str(r.get("INDIRIZZO", ""))
                                    if not any(cap in addr_pot for cap in sel_cap_giro): passa_filtro_cap = False
                                
                                passa_filtro_comune = True
                                if sel_zona_giro:
                                    if str(r.get("COMUNE", "")).upper() not in [c.upper() for c in sel_zona_giro]: passa_filtro_comune = False
                                        
                                if passa_filtro_cap and passa_filtro_comune:
                                    p_new = {
                                        c_nom: r.get("CLIENTE", "Sconosciuto"),
                                        c_ind: r.get("INDIRIZZO", ""),
                                        c_com: r.get("COMUNE", ""),
                                        "is_potenziale": True,
                                        "PIVA": str(r.get("PIVA", "")).replace('nan',''),
                                        "row_idx": r_idx + 2 
                                    }
                                    pool.append(p_new)
                    except: pass
                
                rotta = []
                curr_t = datetime.now(TZ_ITALY).replace(hour=9, minute=0)
                for p in pool:
                    p['arr'] = curr_t
                    
                    # Carica le spunte passate dalla memoria (se esistono)
                    p['tasks_completed'] = st.session_state.db_tasks.get(p[c_nom], []) if not p['is_potenziale'] else []
                    
                    if not p['is_potenziale']:
                        la, lo = pulisci_coordinata_italy(p.get(c_lat), True), pulisci_coordinata_italy(p.get(c_lon), False)
                        p['coords'] = (la, lo) if la and lo else get_geo_data([f"{p[c_ind]}, {p[c_com]}, Italy"]) or SEDE_COORDS
                    else:
                        p['coords'] = get_geo_data([f"{p[c_ind]}, {p[c_com]}, Italy"]) or SEDE_COORDS
                        
                    rotta.append(p)
                    curr_t += timedelta(minutes=40)
                
                st.session_state.master_route = rotta
                if ws_mem: ws_mem.update_acell("B2", json.dumps(rotta, default=str))
                st.rerun()

        if st.session_state.get('master_route'):
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
                    
                    tel = str(p.get(c_tel, '')).replace('nan', '').strip() if c_tel else ''
                    piva = str(p.get(c_piva, '')).replace('nan', '').strip() if c_piva else ''
                    cod = str(p.get(c_codice, '')).replace('nan', '').strip() if c_codice else ''
                    pos = str(p.get(c_pos, '')).replace('nan', '').strip() if c_pos else ''
                    cap_cliente = str(p.get(c_cap, '')).replace('nan', '').strip() if c_cap else ''
                    
                    info_h = ""
                    if piva: info_h += f"<span class='info-tag'>P.IVA: {piva}</span>"
                    if cod: info_h += f"<span class='info-tag'>Cod: {cod}</span>"
                    if pos: info_h += f"<span class='info-tag'>POS: {pos}</span>"
                    if tel: info_h += f"<span class='info-tag'>📞 {tel}</span>"
                    st.markdown(f"<div class='info-row'>{info_h}</div>", unsafe_allow_html=True)
                    
                    tasks_done = p.get('tasks_completed', [])
                    if c_att and p.get(c_att):
                        t_list = [t.strip() for t in str(p[c_att]).split(',') if t.strip() and t.lower() != 'nan']
                        if t_list:
                            st.markdown("**📝 Attività:**")
                            for task in t_list:
                                is_chk = st.checkbox(task, value=(task in tasks_done), key=f"chk_{i}_{task}")
                                if is_chk and task not in tasks_done: tasks_done.append(task)
                                elif not is_chk and task in tasks_done: tasks_done.remove(task)
                            p['tasks_completed'] = tasks_done
                            
                            # Logica Tasto Concludi (Solo per chi ha CG)
                            if any("CG" in t.upper() for t in t_list):
                                pronto = any("CG" in t.upper() for t in tasks_done)
                else:
                    cap_cliente = "" 
                
                cap_display = f" (CAP: {cap_cliente})" if cap_cliente else ""
                st.markdown(f"<div style='color:#94a3b8; font-weight:500; margin-bottom: 15px;'>📍 {p.get(c_ind, '')}, {p.get(c_com, '')}{cap_display}</div>", unsafe_allow_html=True)
                
                esito_selezionato = ""
                if is_pot:
                    with st.expander("📝 Compila Dati Esplorazione", expanded=True):
                        col_p1, col_p2 = st.columns(2)
                        with col_p1:
                            esito_selezionato = st.selectbox("Esito:", ["In Attesa", "Interessato", "Da richiamare", "Non interessato", "Chiuso"], key=f"esito_{i}")
                            st.text_input("Scoring (A, B, C):", key=f"score_{i}")
                        with col_p2:
                            st.text_input("P.IVA Rilevata:", value=p.get("PIVA", ""), key=f"piva_{i}")
                    
                    # Logica Tasto Concludi per Potenziali
                    pronto = esito_selezionato in ["Non interessato", "Chiuso"]
                
                c_dest = p.get('coords', SEDE_COORDS)
                if not isinstance(c_dest, (list, tuple)) or len(c_dest) < 2: c_dest = SEDE_COORDS
                
                # PULSANTIERA
                if not is_pot:
                    c1, c2, c3 = st.columns([1, 1, 2])
                    with c1: st.link_button("🚙 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={c_dest[0]},{c_dest[1]}", use_container_width=True)
                    with c2: 
                        if tel: st.link_button("📞 CHIAMA", f"tel:{tel}", use_container_width=True)
                        else: st.button("📞 NO TEL", disabled=True, use_container_width=True)
                    with c3: 
                        btn_label = "✅ CONCLUDI VISITA" if pronto else "⚠️ MANCA SPUNTA CG"
                        if st.button(btn_label, key=f"btn_close_{i}", use_container_width=True, type="primary" if pronto else "secondary"):
                            if not pronto:
                                st.warning("Per i clienti a DB devi spuntare 'CG' per concludere la visita!")
                            else:
                                st.session_state.master_route.pop(i)
                                if ws_mem: ws_mem.update_acell("B2", json.dumps(st.session_state.master_route, default=str))
                                st.rerun()
                else:
                    c1, c2 = st.columns(2)
                    with c1: st.link_button("🚙 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={c_dest[0]},{c_dest[1]}", use_container_width=True)
                    with c2: 
                        btn_label = "✅ SALVA E CONCLUDI" if pronto else "⚠️ SELEZIONA ESITO"
                        if st.button(btn_label, key=f"btn_close_{i}", use_container_width=True, type="primary" if pronto else "secondary"):
                            if not pronto:
                                st.warning("Per chiudere questo potenziale, l'esito deve essere 'Non interessato' o 'Chiuso'.")
                            else:
                                if ws_pot:
                                    riga = p['row_idx']
                                    data_visita = datetime.now(TZ_ITALY).strftime("%d/%m/%Y")
                                    scoring = st.session_state.get(f"score_{i}", "")
                                    piva = st.session_state.get(f"piva_{i}", "")
                                    
                                    ws_pot.update_cell(riga, 6, data_visita)
                                    ws_pot.update_cell(riga, 7, esito_selezionato)
                                    ws_pot.update_cell(riga, 8, scoring)
                                    ws_pot.update_cell(riga, 9, piva)
                                    st.toast(f"Dati salvati per {p[c_nom]}!", icon="💾")
                                
                                st.session_state.master_route.pop(i)
                                if ws_mem: ws_mem.update_acell("B2", json.dumps(st.session_state.master_route, default=str))
                                st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

    # ==========================================
    # TAB 2: RADAR & TELEMACO
    # ==========================================
    with tab2:
        file_tel = st.file_uploader("📂 Carica File Telemaco (Excel/CSV)", type=['xlsx', 'csv'])
        if file_tel:
            df_tel = pd.read_excel(file_tel, dtype=str) if file_tel.name.endswith('.xlsx') else pd.read_csv(file_tel, sep=None, engine='python', dtype=str)
            
            c_t1, c_t2, c_t3 = st.columns(3)
            with c_t1: col_nome_tel = st.selectbox("Colonna Nome:", df_tel.columns, index=0)
            idx_ind_tel = next((i for i, c in enumerate(df_tel.columns) if "COMPLETO" in c.upper() or "INDIRIZZO" in c.upper()), 0)
            with c_t2: col_ind_tel = st.selectbox("Colonna Indirizzo:", df_tel.columns, index=idx_ind_tel)
            with c_t3: col_com_tel = st.selectbox("Colonna Comune:", df_tel.columns, index=next((i for i, c in enumerate(df_tel.columns) if "COMUNE" in c.upper()), 0))

            modalita_cecchino = st.toggle("🎯 MODALITÀ CECCHINO (Filtra solo comuni del tuo database)", value=True)
            comuni_miei_puliti = [pulisci_nome(c) for c in df[c_com].unique() if str(c).strip()]
            
            if not modalita_cecchino:
                comuni_file = sorted(df_tel[col_com_tel].unique())
                sel_comuni_radar = st.multiselect("🌍 Seleziona Comuni da scansionare:", comuni_file, default=comuni_file[:3])
            else:
                sel_comuni_radar = comuni_miei_puliti

            if st.button("🚀 AVVIA RADAR 150m", type="primary", use_container_width=True):
                df_prem = df[df[c_prem].astype(str).str.upper().str.contains("SI", na=False)].copy() if c_prem else df.head(0)
                premium_coords = []
                for _, pr in df_prem.iterrows():
                    la, lo = pulisci_coordinata_italy(pr.get(c_lat),True), pulisci_coordinata_italy(pr.get(c_lon),False)
                    if la: premium_coords.append((la, lo))
                
                risultati_ok = []
                scarti = {"ZONA": 0, "CLIENTI": 0, "RADAR": 0, "MAPPA": 0}
                nomi_miei_puliti = [pulisci_nome(n) for n in df[c_nom].unique()]
                
                prog = st.progress(0)
                for i, r_tel in df_tel.iterrows():
                    prog.progress((i+1)/len(df_tel))
                    com_t_raw = str(r_tel[col_com_tel]).strip()
                    com_t_pulito = pulisci_nome(com_t_raw)
                    nome_t_pulito = pulisci_nome(r_tel[col_nome_tel])
                    
                    if modalita_cecchino:
                        if com_t_pulito not in comuni_miei_puliti:
                            scarti["ZONA"] += 1; continue
                    else:
                        if com_t_raw not in sel_comuni_radar:
                            scarti["ZONA"] += 1; continue

                    if nome_t_pulito in nomi_miei_puliti:
                        scarti["CLIENTI"] += 1; continue
                    
                    ind_t = str(r_tel.get(col_ind_tel, '')).strip()
                    if "Indirizzo" in ind_t or ind_t in ["", "nan"]:
                        try:
                            via = str(r_tel.iloc[7]).replace('nan', '').strip()
                            civ = str(r_tel.iloc[8]).replace('nan', '').strip()
                            ind_t = f"{via} {civ}".strip()
                        except: ind_t = ""
                    
                    t_c = get_geo_data([f"{ind_t}, {com_t_raw}, Italy", f"{com_t_raw}, Italy"])
                    if t_c:
                        vicino = any(geodesic(t_c, pc).meters < 150 for pc in premium_coords)
                        if vicino: scarti["RADAR"] += 1
                        else: risultati_ok.append([nome_t_pulito, ind_t, com_t_raw, "✅ DISPONIBILE"])
                    else: scarti["MAPPA"] += 1

                st.markdown("### 📊 Report Scansione")
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Fuori Zona", scarti["ZONA"])
                c2.metric("Già Clienti", scarti["CLIENTI"])
                c3.metric("Troppo Vicini", scarti["RADAR"])
                c4.metric("Errori Mappa", scarti["MAPPA"])
                
                if risultati_ok:
                    df_res = pd.DataFrame(risultati_ok, columns=["CLIENTE", "INDIRIZZO", "COMUNE", "STATO"])
                    st.success(f"🎯 Radar completato! Trovati {len(risultati_ok)} bar validi.")
                    
                    if st.button("💾 SALVA TUTTI IN 'POTENZIALI'", use_container_width=True):
                        if ws_pot:
                            if not ws_pot.acell("A1").value:
                                ws_pot.append_row(["DATA_INS", "CLIENTE", "INDIRIZZO", "COMUNE", "STATO", "DATA_VISITA", "ESITO", "SCORING", "PIVA"])
                            for row in risultati_ok:
                                ws_pot.append_row([datetime.now(TZ_ITALY).strftime("%d/%m/%Y"), row[0], row[1], row[2], row[3], "", "", "", ""])
                            st.success("Tutti i contatti salvati nel Foglio Google! Ora li vedrai nel Giro Visite.")
