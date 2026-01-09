import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
from datetime import datetime
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE E STILE ---
st.set_page_config(page_title="Brightstar AI PRO", page_icon="⭐", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 15px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 20px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 5px; color: white; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); color: #002D72 !important; font-weight: bold; }
    div.stButton > button[key^="f_"] { background: #28a745 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONNESSIONE SCRITTURA GOOGLE SHEETS ---
def connetti_e_carica():
    try:
        # Usa i Secrets di Streamlit per le credenziali (caricale nel pannello di controllo Streamlit)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        # Sostituisci col nome del tuo file e del foglio (es. "Foglio1")
        sh = client.open("https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing")
        worksheet = sh.get_worksheet(0) 
        df = pd.DataFrame(worksheet.get_all_records())
        df.columns = [str(c).strip().upper() for c in df.columns]
        return worksheet, df
    except Exception as e:
        st.error(f"Errore di connessione: {e}")
        return None, None

# --- 3. AGENTI AI (VOCE E METEO) ---
def parla(testo):
    st.components.v1.html(f"""<script>var msg = new SpeechSynthesisUtterance('{testo}'); msg.lang = 'it-IT'; window.speechSynthesis.speak(msg);</script>""", height=0)

def agente_meteo_multi_zona(tappe):
    if datetime.now().weekday() >= 5: return None, None, None
    punti = [p['coords'] for p in tappe] if tappe else [(43.76, 11.24)]
    try:
        res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={punti[0][0]}&longitude={punti[0][1]}&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1").json()
        temp = res['hourly']['temperature_2m'][8]
        pioggia = max(res['hourly']['precipitation_probability'][8:18])
        if temp < 3 or pioggia > 30:
            return "AUTO 🚗", f"Meteo: {temp}°C / {pioggia}% pioggia. Usa l'auto.", "#ff4b4b"
        return "ZONTES 350D 🛵", f"Meteo OK ({temp}°C). Vai di Zontes!", "#28a745"
    except: return "INFO", "Meteo non disp.", "#FFD700"

# --- 4. LOGICA PRINCIPALE ---
st.title("⭐ BRIGHTSTAR FI-AR: 10 TAPPE SMART")

ws, df = connetti_e_carica()

if df is not None:
    # FILTRO: Escludi chi è già stato visitato (tranne se forzato dopo)
    df_da_visitare = df[~df['VISITATO'].astype(str).str.upper().str.contains('SI|SÌ', na=False)]

    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        comuni = st.multiselect("📍 Filtra per Comune:", sorted(df['COMUNE'].unique().tolist()))
        forzati = st.multiselect("📌 Clienti Obbligatori (anche se già visitati):", sorted(df['CLIENTE'].unique().tolist()))
        
        if st.button("🚀 GENERA 10 VISITE"):
            # 1. Prendi i forzati (anche se visitati)
            giro = df[df['CLIENTE'].isin(forzati)].to_dict('records')
            # 2. Riempi fino a 10 con quelli NON visitati
            mask = df['CLIENTE'].isin(df_da_visitare['CLIENTE']) & ~df['CLIENTE'].isin(forzati)
            if comuni: mask &= df['COMUNE'].isin(comuni)
            
            extra = df[mask].head(10 - len(giro)).to_dict('records')
            giro.extend(extra)
            
            # Geocoding e Ottimizzazione (Semplificata per brevità)
            geolocator = Nominatim(user_agent="brightstar_pro")
            for r in giro:
                loc = geolocator.geocode(f"{r['INDIRIZZO']}, {r['COMUNE']}, Italy")
                if loc: r['coords'] = (loc.latitude, loc.longitude)
            
            st.session_state.giro_igt = giro
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # --- LISTA VISITE ---
    if 'giro_igt' in st.session_state and st.session_state.giro_igt:
        mezzo, sug, col = agente_meteo_multi_zona(st.session_state.giro_igt)
        st.info(f"{mezzo}: {sug}")

        for i, p in enumerate(st.session_state.giro_igt):
            with st.container():
                st.markdown(f"<div class='tappa-card'><b>{i+1}. {p['CLIENTE']}</b><br>📍 {p['COMUNE']} - {p['INDIRIZZO']}</div>", unsafe_allow_html=True)
                
                c1, c2 = st.columns(2)
                with c1:
                    st.link_button("🚙 VAI", f"https://waze.com/ul?q={p['INDIRIZZO'].replace(' ','%20')}%20{p['COMUNE']}&navigate=yes")
                with c2:
                    if st.button("✅ SEGNA COME FATTO", key=f"f_{i}"):
                        # SCRITTURA SU GOOGLE SHEET
                        try:
                            # Trova la cella basata sul CODICE CLIENTE o RAGIONE SOCIALE
                            cella = ws.find(str(p['CLIENTE']))
                            # Assumendo che 'VISITATO' sia la colonna E (indice 5)
                            # Modifica l'indice in base alla tua colonna reale
                            col_visitato = df.columns.get_loc("VISITATO") + 1
                            ws.update_cell(cella.row, col_visitato, "SI")
                            
                            st.session_state.giro_igt.pop(i)
                            parla(f"Visita a {p['CLIENTE']} registrata su Google Sheets")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore aggiornamento: {e}")

# --- REPORT SERALE (MAIL) ---
# [Codice Mail già fornito precedentemente rimane invariato]
