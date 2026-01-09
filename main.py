import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import datetime, timedelta
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar Pro Navigator", page_icon="⭐", layout="wide")
SEDE = (43.661888, 11.305728) # Strada in Chianti

st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 20px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 25px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 8px; color: white; }
    .time-badge { background-color: #FFD700; color: #001a41; padding: 2px 8px; border-radius: 5px; font-weight: bold; font-size: 0.9em; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); color: #002D72 !important; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNZIONI ---
@st.cache_resource(show_spinner="Connessione Database...")
def get_gsheet_ws(sheet_id):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(sheet_id).get_worksheet(0)
    except: return None

def agente_meteo(lat, lon):
    try:
        res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1").json()
        temp, pioggia = res['hourly']['temperature_2m'][8], max(res['hourly']['precipitation_probability'][8:18])
        if temp < 3 or pioggia > 30: return "AUTO 🚗", f"Meteo critico ({temp}°C/Pioggia). Usa l'auto.", "#ff4b4b"
        return "ZONTES 🛵", f"Meteo ottimo ({temp}°C). Vai in scooter!", "#28a745"
    except: return "INFO", "Meteo N/D", "#FFD700"

# --- 3. LOGICA DI CALCOLO ---
st.title("⭐ BRIGHTSTAR PRO NAVIGATOR")

# --- INSERISCI QUI IL TUO ID ---
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" 
ws = get_gsheet_ws(ID_DEL_FOGLIO)

if ws:
    if 'df_db' not in st.session_state:
        all_v = ws.get_all_values()
        if len(all_v) > 1:
            df = pd.DataFrame(all_v[1:], columns=[str(h).strip().upper() for h in all_v[0]])
            for c in ['CODICE', 'TELEFONO', 'CAP']: 
                if c in df.columns: df[c] = df[c].astype(str).str.replace('.0','', regex=False)
            st.session_state.df_db = df

    if 'df_db' in st.session_state:
        df = st.session_state.df_db
        df_liberi = df[~df['VISITATO'].astype(str).str.upper().str.contains('SI|SÌ', na=False)]

        with st.container():
            st.markdown("<div class='header-box'>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            with c1: sel_comuni = st.multiselect("📍 Comuni:", sorted(df['COMUNE'].unique().tolist()))
            with c2: sel_caps = st.multiselect("📮 CAP:", sorted(df['CAP'].unique().tolist()))
            with c3: forzati = st.multiselect("📌 Prioritari:", sorted(df['CLIENTE'].unique().tolist()))
            
            num_tappe = st.slider("Quante visite vuoi pianificare?", 5, 20, 10)
            
            if st.button("🚀 OTTIMIZZA PERCORSO E ORARI"):
                with st.spinner("Pianificando il giro perfetto..."):
                    giro = df[df['CLIENTE'].isin(forzati)].to_dict('records')
                    mask = df['CLIENTE'].isin(df_liberi['CLIENTE']) & ~df['CLIENTE'].isin(forzati)
                    if sel_comuni: mask &= df['COMUNE'].isin(sel_comuni)
                    if sel_caps: mask &= df['CAP'].isin(sel_caps)
                    
                    extra = df[mask].head(num_tappe - len(giro)).to_dict('records')
                    giro.extend(extra)
                    
                    geo = Nominatim(user_agent="brightstar_v10")
                    for r in giro:
                        try:
                            loc = geo.geocode(f"{r['INDIRIZZO']}, {r['CAP']}, {r['COMUNE']}, Italy", timeout=3)
                            r['coords'] = (loc.latitude, loc.longitude) if loc else SEDE
                        except: r['coords'] = SEDE

                    opt = []
                    punto = SEDE
                    ora_attuale = datetime.now().replace(hour=7, minute=30, second=0, microsecond=0)
                    
                    while giro:
                        prox = min(giro, key=lambda x: geodesic(punto, x['coords']).km)
                        dist = geodesic(punto, prox['coords']).km
                        tempo_viaggio = (dist / 40) * 60 
                        ora_attuale += timedelta(minutes=tempo_viaggio)
                        prox['ora_arrivo'] = ora_attuale.strftime("%H:%M")
                        
                        ora_attuale += timedelta(minutes=30)
                        prox['ora_partenza'] = ora_attuale.strftime("%H:%M")
                        
                        opt.append(prox); punto = prox['coords']; giro.remove(prox)
                    
                    dist_rientro = geodesic(punto, SEDE).km
                    ora_attuale += timedelta(minutes=(dist_rientro/40)*60)
                    
                    st.session_state.rientro = ora_attuale.strftime("%H:%M")
                    st.session_state.giro_igt = opt
                    st.rerun()

        if 'giro_igt' in st.session_state and 'rientro' in st.session_state:
            mezzo, sug, col_m = agente_meteo(43.66, 11.30)
            
            st.info(f"📍 Rientro stimato a Strada in Chianti: **{st.session_state.rientro}**")
            
            rientro_dt = datetime.strptime(st.session_state.rientro, "%H:%M")
            if rientro_dt.hour < 18:
                st.warning("⚠️ Finirai molto presto! Considera di aggiungere 2-3 tappe al cursore sopra.")
            elif rientro_dt.hour >= 19 and rientro_dt.minute > 30:
                st.error("🚨 Attenzione: Il giro stimato supera le 19:30!")

            for i, p in enumerate(st.session_state.giro_igt):
                with st.container():
                    st.markdown(f"""
                    <div class="tappa-card">
                        <span class="time-badge">Arrivo: {p['ora_arrivo']}</span><br>
                        <b>{i+1}. {p['CLIENTE']}</b> (Cod: {p.get('CODICE','')})<br>
                        📍 {p.get('CAP','')} {p.get('COMUNE','')} - {p.get('INDIRIZZO','')}<br>
                        ⏱️ Sosta prevista fino alle {p['ora_partenza']}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    nota = st.text_area("Note visita:", key=f"n_{i}")
                    col1, col2, col3 = st.columns(3)
                    with col1: st.link_button("🚙 WAZE", f"https://waze.com/ul?q={p['INDIRIZZO']}%20{p['CAP']}%20{p['COMUNE']}&navigate=yes")
                    with col2: 
                        tel = p.get('TELEFONO','')
                        if tel: st.link_button("📞 CHIAMA", f"tel:{tel}")
                    with col3:
                        if st.button("✅ FATTO", key=f"f_{i}"):
                            try:
                                riga = ws.find(str(p['CLIENTE']))
                                headers = [h.upper() for h in ws.row_values(1)]
                                ws.update_cell(riga.row, headers.index("VISITATO")+1, "SI")
                                if nota.strip():
                                    if 'rep_serale' not in st.session_state: st.session_state.rep_serale = []
                                    st.session_state.rep_serale.append({"c": p['CLIENTE'], "cod": p.get('CODICE',''), "n": nota})
                                st.session_state.giro_igt.pop(i)
                                st.rerun()
                            except Exception as e: st.error(f"Errore: {e}")

    if 'rep_serale' in st.session_state and len(st.session_state.rep_serale) > 0:
        st.divider()
        if st.button("📧 GENERA REPORT MAIL"):
            data = datetime.now().strftime("%d/%m/%Y")
            corpo = f"Report Visite {data}\n\n"
            for r in st.session_state.rep_serale:
                corpo += f"- {r['c']} (Cod: {r['cod']}): {r['n']}\n"
            subj = f"REPORT VISITE {data} - GIAMBATTISTA"
            link = f"mailto:giambattista.giacchetti@gmail.com?subject={urllib.parse.quote(subj)}&body={urllib.parse.quote(corpo)}"
            st.link_button("Invia ora", link)
