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
    h1 { color: #FFD700 !important; text-align: center; }
    .header-box { background-color: #00122e; padding: 15px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 20px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 5px; color: white; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); color: #002D72 !important; font-weight: bold; }
    div.stButton > button[key^="f_"] { background: #28a745 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

def parla(testo):
    st.components.v1.html(f"""<script>var msg = new SpeechSynthesisUtterance('{testo}'); msg.lang = 'it-IT'; window.speechSynthesis.speak(msg);</script>""", height=0)

# --- 2. CONNESSIONE GOOGLE SHEETS (CORRETTA) ---
def connetti_e_carica():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        
        # --- ATTENZIONE: SCRIVI IL NOME DEL FILE ESATTAMENTE COME SU GOOGLE ---
        sh = client.open("GiroVisite_Dati") # Modifica qui con il nome reale
        worksheet = sh.get_worksheet(0)
        
        records = worksheet.get_all_records()
        if not records:
            return worksheet, pd.DataFrame()
            
        df = pd.DataFrame(records)
        
        # QUESTA RIGA TRASFORMA TUTTI I TUOI NOMI (Cliente, Visitato...) IN MAIUSCOLO PER IL CODICE
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        return worksheet, df
    except Exception as e:
        st.error(f"Errore di connessione: {e}")
        return None, None

# --- 3. LOGICA METEO ---
def agente_meteo_multi_zona(tappe):
    if datetime.now().weekday() >= 5: return None, None, None
    lat, lon = (43.66, 11.30) if not tappe else tappe[0]['coords']
    try:
        res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1").json()
        temp = res['hourly']['temperature_2m'][8]
        pioggia = max(res['hourly']['precipitation_probability'][8:18])
        if temp < 3 or pioggia > 30:
            return "AUTO 🚗", f"Meteo: {temp}°C / {pioggia}% pioggia.", "#ff4b4b"
        return "ZONTES 350D 🛵", f"Meteo OK ({temp}°C). Vai di Zontes!", "#28a745"
    except: return "INFO", "Meteo N/D", "#FFD700"

# --- 4. APP ---
st.title("⭐ BRIGHTSTAR PRO")

ws, df = connetti_e_carica()

if df is not None:
    # Cerchiamo la colonna VISITATO (ora è diventata maiuscola nel DataFrame)
    df_liberi = df[~df['VISITATO'].astype(str).str.upper().str.contains('SI|SÌ', na=False)]

    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            sel_comuni = st.multiselect("📍 Comuni:", sorted(df['COMUNE'].unique().tolist()))
        with col2:
            forzati = st.multiselect("📌 Clienti Obbligatori:", sorted(df['CLIENTE'].unique().tolist()))
        
        if st.button("🚀 GENERA 10 VISITE"):
            with st.status("Ottimizzazione..."):
                giro = df[df['CLIENTE'].isin(forzati)].to_dict('records')
                mask = df['CLIENTE'].isin(df_liberi['CLIENTE']) & ~df['CLIENTE'].isin(forzati)
                if sel_comuni: mask &= df['COMUNE'].isin(sel_comuni)
                
                extra = df[mask].head(10 - len(giro)).to_dict('records')
                giro.extend(extra)
                
                geolocator = Nominatim(user_agent="brightstar_pro_v2")
                for r in giro:
                    loc = geolocator.geocode(f"{r['INDIRIZZO']}, {r['COMUNE']}, Italy")
                    r['coords'] = (loc.latitude, loc.longitude) if loc else (43.7, 11.2)
                
                opt = []
                pos = (43.66, 11.30)
                while giro:
                    prox = min(giro, key=lambda x: geodesic(pos, x['coords']).km)
                    opt.append(prox); pos = prox['coords']; giro.remove(prox)
                
                st.session_state.giro_igt = opt
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    if 'giro_igt' in st.session_state and st.session_state.giro_igt:
        m_info, s_info, c_info = agente_meteo_multi_zona(st.session_state.giro_igt)
        st.info(f"{m_info}: {s_info}")

        for i, p in enumerate(st.session_state.giro_igt):
            with st.container():
                st.markdown(f"<div class='tappa-card'><b>{i+1}. {p['CLIENTE']}</b><br>📍 {p['COMUNE']} - {p['INDIRIZZO']}</div>", unsafe_allow_html=True)
                
                c1, c2, c3 = st.columns(3)
                with c1: st.link_button("🚙 VAI", f"https://waze.com/ul?q={p['INDIRIZZO'].replace(' ','%20')}%20{p['COMUNE']}&navigate=yes")
                with c2: 
                    if p.get('TELEFONO'): st.link_button("📞 TEL", f"tel:{p['TELEFONO']}")
                with c3:
                    if st.button("✅ FATTO", key=f"f_{i}"):
                        try:
                            # Cerchiamo la riga nel foglio Google
                            # Usiamo il valore originale del foglio per la ricerca
                            cella = ws.find(str(p['CLIENTE']))
                            
                            # Troviamo quale colonna è "Visitato" (senza preoccuparci delle maiuscole)
                            headers = ws.row_values(1)
                            idx_visitato = 1
                            for j, h in enumerate(headers):
                                if h.strip().upper() == "VISITATO":
                                    idx_visitato = j + 1
                                    break
                            
                            ws.update_cell(cella.row, idx_visitato, "SI")
                            st.session_state.giro_igt.pop(i)
                            parla(f"Tappa completata")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore: {e}")
