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
    h1 { color: #FFD700 !important; text-align: center; font-family: sans-serif; }
    .header-box { background-color: #00122e; padding: 15px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 20px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 5px; color: white; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); color: #002D72 !important; font-weight: bold; border: none; }
    div.stButton > button[key^="f_"] { background: #28a745 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. AGENTE VOCALE ---
def parla(testo):
    componente_audio = f"""<script>var msg = new SpeechSynthesisUtterance('{testo}'); msg.lang = 'it-IT'; window.speechSynthesis.speak(msg);</script>"""
    st.components.v1.html(componente_audio, height=0)

# --- 3. CONNESSIONE GOOGLE SHEETS ---
def connetti_e_carica():
    try:
        # Credenziali dai Secrets
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        
        # APERTURA FILE - SOSTITUISCI CON IL NOME ESATTO DEL TUO FILE
        sh = client.open("GiroVisite_Dati") 
        worksheet = sh.get_worksheet(0)
        
        # Caricamento dati
        records = worksheet.get_all_records()
        if not records:
            return worksheet, pd.DataFrame()
            
        df = pd.DataFrame(records)
        df.columns = [str(c).strip().upper() for c in df.columns]
        return worksheet, df
    except Exception as e:
        st.error(f"Errore di connessione: {e}")
        return None, None

# --- 4. AGENTE METEO (FIRENZE/AREZZO) ---
def agente_meteo_multi_zona(tappe):
    if datetime.now().weekday() >= 5: return None, None, None
    # Punto di controllo: se non c'è il giro, usa il centro del raggio d'azione
    lat, lon = (43.66, 11.30) if not tappe else tappe[0]['coords']
    try:
        res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1").json()
        temp_8am = res['hourly']['temperature_2m'][8]
        prob_pioggia = max(res['hourly']['precipitation_probability'][8:18])
        
        if temp_8am < 3 or prob_pioggia > 30:
            return "AUTO 🚗", f"Meteo: {temp_8am}°C / {prob_pioggia}% pioggia. Usa l'auto.", "#ff4b4b"
        return "ZONTES 350D 🛵", f"Meteo OK ({temp_8am}°C). Vai di Zontes!", "#28a745"
    except: return "INFO", "Meteo non disponibile", "#FFD700"

# --- 5. LOGICA PRINCIPALE ---
st.title("⭐ BRIGHTSTAR AI PRO")

ws, df = connetti_e_carica()

if df is not None:
    # Filtro automatico: escludi chi ha già "SI" in VISITATO
    df_liberi = df[~df['VISITATO'].astype(str).str.upper().str.contains('SI|SÌ', na=False)]

    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            sel_comuni = st.multiselect("📍 Filtra Comuni:", sorted(df['COMUNE'].unique().tolist()))
        with c2:
            forzati = st.multiselect("📌 Clienti Obbligatori:", sorted(df['CLIENTE'].unique().tolist()))
        
        if st.button("🚀 GENERA GIRO (10 TAPPE)"):
            with st.status("Ottimizzazione in corso..."):
                # 1. Prendi i forzati
                giro = df[df['CLIENTE'].isin(forzati)].to_dict('records')
                # 2. Riempi fino a 10 con i non visitati
                mask = df['CLIENTE'].isin(df_liberi['CLIENTE']) & ~df['CLIENTE'].isin(forzati)
                if sel_comuni: mask &= df['COMUNE'].isin(sel_comuni)
                
                extra = df[mask].head(10 - len(giro)).to_dict('records')
                giro.extend(extra)
                
                # Geocoding
                geolocator = Nominatim(user_agent="brightstar_final")
                for r in giro:
                    loc = geolocator.geocode(f"{r['INDIRIZZO']}, {r['COMUNE']}, Italy")
                    r['coords'] = (loc.latitude, loc.longitude) if loc else (43.7, 11.2)
                
                # Ordinamento per distanza
                opt = []
                pos = (43.661888, 11.305728) # Sede
                while giro:
                    prox = min(giro, key=lambda x: geodesic(pos, x['coords']).km)
                    opt.append(prox)
                    pos = prox['coords']
                    giro.remove(prox)
                
                st.session_state.giro_igt = opt
                parla("Giro generato correttamente.")
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # --- VISUALIZZAZIONE TAPPE ---
    if 'giro_igt' in st.session_state and st.session_state.giro_igt:
        mezzo, sug, col = agente_meteo_multi_zona(st.session_state.giro_igt)
        st.markdown(f"<div style='border:2px solid {col}; padding:10px; border-radius:10px; text-align:center; color:white;'><b>{mezzo}</b>: {sug}</div>", unsafe_allow_html=True)
        
        for i, p in enumerate(st.session_state.giro_igt):
            with st.container():
                st.markdown(f"""<div class="tappa-card"><b>{i+1}. {p['CLIENTE']}</b> (Cod: {p.get('CODICE','')})<br>📍 {p['COMUNE']} - {p['INDIRIZZO']}</div>""", unsafe_allow_html=True)
                
                nota = st.text_area("Note (Materiali/Problemi):", key=f"n_{i}")
                
                c1, c2, c3 = st.columns([1,1,1])
                with c1:
                    st.link_button("🚙 VAI", f"https://waze.com/ul?q={p['INDIRIZZO'].replace(' ','%20')}%20{p['COMUNE']}&navigate=yes")
                with c2:
                    if p.get('TELEFONO'): st.link_button("📞 TEL", f"tel:{p['TELEFONO']}")
                with c3:
                    if st.button("✅ FATTO", key=f"f_{i}"):
                        try:
                            # Aggiornamento Google Sheets
                            cella = ws.find(str(p['CLIENTE']))
                            # Trova la colonna VISITATO dinamicamente
                            col_idx = df.columns.get_loc("VISITATO") + 1
                            ws.update_cell(cella.row, col_idx, "SI")
                            
                            # Salva nel report serale
                            if 'report_serale' not in st.session_state: st.session_state.report_serale = []
                            st.session_state.report_serale.append({"c": p['CLIENTE'], "cod": p.get('CODICE',''), "n": nota})
                            
                            st.session_state.giro_igt.pop(i)
                            parla(f"Tappa completata. Registrato su Excel.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore aggiornamento: {e}")

# --- 6. REPORT MAIL ---
if 'report_serale' in st.session_state and st.session_state.report_serale:
    st.divider()
    if st.button("📧 GENERA REPORT MAIL"):
        data_s = datetime.now().strftime("%d/%m/%Y")
        corpo = f"REPORT VISITE {data_s}\n\n"
        for r in st.session_state.report_serale:
            corpo += f"- {r['c']} (Cod: {r['cod']}): {r['n']}\n"
        link = f"mailto:giambattista.giacchetti@gmail.com?subject=Report%20{data_s}&body={urllib.parse.quote(corpo)}"
        st.link_button("Invia ora", link)
