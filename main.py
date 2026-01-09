import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import datetime
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Brightstar Pro Navigator", page_icon="⭐", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 20px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 25px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 8px; color: white; border-bottom: 1px solid #333; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); color: #002D72 !important; font-weight: bold; border: none; }
    div.stButton > button[key^="f_"] { background: #28a745 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNZIONI AGENTI ---
def parla(testo):
    st.components.v1.html(f"""<script>var msg = new SpeechSynthesisUtterance('{testo}'); msg.lang = 'it-IT'; window.speechSynthesis.speak(msg);</script>""", height=0)

@st.cache_resource(show_spinner="Connessione al Database Google...")
def get_gsheet_ws(sheet_id):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_key(sheet_id)
        return sh.get_worksheet(0)
    except Exception as e:
        st.error(f"Errore di connessione API: {e}")
        return None

def agente_meteo(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1"
        res = requests.get(url).json()
        temp = res['hourly']['temperature_2m'][8]
        pioggia = max(res['hourly']['precipitation_probability'][8:18])
        if temp < 3 or pioggia > 30:
            return "AUTO 🚗", f"{temp}°C / {pioggia}% pioggia. Usa l'auto.", "#ff4b4b"
        return "ZONTES 350D 🛵", f"Meteo perfetto ({temp}°C). Vai di scooter!", "#28a745"
    except: 
        return "INFO", "Meteo non disp.", "#FFD700"

# --- 3. LOGICA PRINCIPALE ---
st.title("⭐ BRIGHTSTAR PRO NAVIGATOR")

# --- INSERISCI QUI L'ID DEL TUO FOGLIO ---
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" 

ws = get_gsheet_ws(ID_DEL_FOGLIO)

if ws:
    if 'df_db' not in st.session_state:
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        df.columns = [str(c).strip().upper() for c in df.columns]
        st.session_state.df_db = df
    
    df = st.session_state.df_db
    df_liberi = df[~df['VISITATO'].astype(str).str.upper().str.contains('SI|SÌ', na=False)]

    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            comuni = st.multiselect("📍 Comuni:", sorted(df['COMUNE'].unique().tolist()) if 'COMUNE' in df.columns else [])
        with col2:
            forzati = st.multiselect("📌 Clienti Obbligatori:", sorted(df['CLIENTE'].unique().tolist()) if 'CLIENTE' in df.columns else [])
        
        if st.button("🚀 GENERA 10 VISITE OTTIMIZZATE"):
            with st.spinner("Calcolo percorso..."):
                giro = df[df['CLIENTE'].isin(forzati)].to_dict('records')
                mask = df['CLIENTE'].isin(df_liberi['CLIENTE']) & ~df['CLIENTE'].isin(forzati)
                if comuni: mask &= df['COMUNE'].isin(comuni)
                
                extra = df[mask].head(10 - len(giro)).to_dict('records')
                giro.extend(extra)
                
                geo = Nominatim(user_agent="brightstar_v5")
                for r in giro:
                    try:
                        loc = geo.geocode(f"{r['INDIRIZZO']}, {r['COMUNE']}, Italy", timeout=3)
                        r['coords'] = (loc.latitude, loc.longitude) if loc else (43.66, 11.30)
                    except: 
                        r['coords'] = (43.66, 11.30)
                
                # --- CALCOLO PERCORSO OTTIMO ---
                opt = []
                punto_attuale = (43.661888, 11.305728) # Sede
                while giro:
                    prossima = min(giro, key=lambda x: geodesic(punto_attuale, x['coords']).km)
                    opt.append(prossima)
                    punto_attuale = prossima['coords']
                    giro.remove(prossima)
                
                st.session_state.giro_igt = opt
                parla("Giro pronto.")
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    if 'giro_igt' in st.session_state and st.session_state.giro_igt:
        mezzo, sug, col_m = agente_meteo(43.66, 11.30)
        st.markdown(f"<div style='border:2px solid {col_m}; padding:10px; border-radius:10px; text-align:center; color:white; margin-bottom:15px;'><b>{mezzo}</b>: {sug}</div>", unsafe_allow_html=True)

        for i, p in enumerate(st.session_state.giro_igt):
            with st.container():
                st.markdown(f"<div class='tappa-card'><b>{i+1}. {p['CLIENTE']}</b><br>📍 {p['COMUNE']} - {p['INDIRIZZO']}</div>", unsafe_allow_html=True)
                
                nota = st.text_area("Note visita:", key=f"n_{i}")
                
                c1, c2, c3 = st.columns(3)
                with c1: 
                    st.link_button("🚙 WAZE", f"https://waze.com/ul?q={p['INDIRIZZO'].replace(' ','%20')}%20{p['COMUNE']}&navigate=yes")
                with c2: 
                    tel = str(p.get('TELEFONO','')).replace(".0","")
                    if tel: st.link_button("📞 CHIAMA", f"tel:{tel}")
                with c3:
                    if st.button("✅ FATTO", key=f"f_{i}"):
                        try:
                            riga = ws.find(str(p['CLIENTE']))
                            headers = [h.upper() for h in ws.row_values(1)]
                            col_v = headers.index("VISITATO") + 1
                            ws.update_cell(riga.row, col_v, "SI")
                            
                            if 'rep_serale' not in st.session_state: st.session_state.rep_serale = []
                            st.session_state.rep_serale.append({"c": p['CLIENTE'], "cod": p.get('CODICE',''), "n": nota})
                            
                            st.session_state.giro_igt.pop(i)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore: {e}")

# --- REPORT SERALE ---
if 'rep_serale' in st.session_state and st.session_state.rep_serale:
    st.divider()
    if st.button("📧 GENERA REPORT MAIL"):
        data = datetime.now().strftime("%d/%m/%Y")
        corpo = f"Report Visite {data}\n\n"
        for r in st.session_state.rep_serale:
            corpo += f"- {r['c']} (Cod: {r['cod']}): {r['n']}\n"
        subj = f"REPORT VISITE {data} - GIAMBATTISTA"
        link = f"mailto:giambattista.giacchetti@gmail.com?subject={urllib.parse.quote(subj)}&body={urllib.parse.quote(corpo)}"
        st.link_button("Invia ora", link)
