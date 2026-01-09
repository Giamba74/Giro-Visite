import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import datetime
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar AI PRO", page_icon="⭐", layout="wide")

# Stile CSS
st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 15px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 20px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 5px; color: white; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); color: #002D72 !important; font-weight: bold; }
    div.stButton > button[key^="f_"] { background: #28a745 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNZIONI DI SERVIZIO ---
def parla(testo):
    st.components.v1.html(f"""<script>var msg = new SpeechSynthesisUtterance('{testo}'); msg.lang = 'it-IT'; window.speechSynthesis.speak(msg);</script>""", height=0)

def connetti_e_carica():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        
        # --- SOSTITUISCI CON IL NOME ESATTO DEL TUO FILE ---
        sh = client.open("GiroVisite_Dati") 
        worksheet = sh.get_worksheet(0)
        
        # Recupero dati ignorando eventuali messaggi di stato HTTP
        records = worksheet.get_all_records()
        if not records:
            return worksheet, pd.DataFrame()
            
        df = pd.DataFrame(records)
        
        # Normalizzazione Colonne: Trasforma 'Cliente' o 'cliente' in 'CLIENTE'
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        return worksheet, df
    except Exception as e:
        # Se l'errore contiene "200", significa che è andata bene ma gspread ha risposto in modo strano
        if "200" in str(e):
            return None, "RETRY"
        st.error(f"Errore reale: {e}")
        return None, None

def agente_meteo(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1"
        r = requests.get(url)
        if r.status_code == 200:
            data = r.json()
            t = data['hourly']['temperature_2m'][8]
            p = max(data['hourly']['precipitation_probability'][8:18])
            if t < 3 or p > 30:
                return "AUTO 🚗", f"{t}°C / {p}% pioggia", "#ff4b4b"
            return "ZONTES 🛵", f"Meteo OK ({t}°C)", "#28a745"
    except: pass
    return "INFO", "Meteo N/D", "#FFD700"

# --- 3. LOGICA APP ---
st.title("⭐ BRIGHTSTAR PRO")

ws, df = connetti_e_carica()

# Se restituisce "RETRY", ricarichiamo la pagina una volta sola
if df == "RETRY":
    st.rerun()

if df is not None and isinstance(df, pd.DataFrame):
    # Filtro: Escludi chi ha già SI in VISITATO (case-insensitive)
    if 'VISITATO' in df.columns:
        df_liberi = df[~df['VISITATO'].astype(str).str.upper().str.contains('SI|SÌ', na=False)]
    else:
        st.error("Colonna 'VISITATO' non trovata nel foglio!")
        df_liberi = df

    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            comuni = st.multiselect("📍 Comuni:", sorted(df['COMUNE'].unique().tolist()) if 'COMUNE' in df.columns else [])
        with c2:
            forzati = st.multiselect("📌 Obbligatori:", sorted(df['CLIENTE'].unique().tolist()) if 'CLIENTE' in df.columns else [])
        
        if st.button("🚀 GENERA 10 VISITE"):
            with st.spinner("Ottimizzazione percorso..."):
                # Selezione tappe
                giro = df[df['CLIENTE'].isin(forzati)].to_dict('records')
                mask = df['CLIENTE'].isin(df_liberi['CLIENTE']) & ~df['CLIENTE'].isin(forzati)
                if comuni: mask &= df['COMUNE'].isin(comuni)
                
                extra = df[mask].head(10 - len(giro)).to_dict('records')
                giro.extend(extra)
                
                # Coordinate e Ordinamento
                geolocator = Nominatim(user_agent="brightstar_v3")
                for r in giro:
                    l = geolocator.geocode(f"{r.get('INDIRIZZO','')}, {r.get('COMUNE','')}, Italy")
                    r['coords'] = (l.latitude, l.longitude) if l else (43.6, 11.3)
                
                opt = []
                pos = (43.66, 11.30)
                while giro:
                    prox = min(giro, key=lambda x: geodesic(pos, x['coords']).km)
                    opt.append(prox); pos = prox['coords']; giro.remove(prox)
                
                st.session_state.giro_igt = opt
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # Visualizzazione
    if 'giro_igt' in st.session_state and st.session_state.giro_igt:
        mezzo, info, col = agente_meteo(43.66, 11.30)
        st.markdown(f"<div style='border:2px solid {col}; padding:10px; border-radius:10px; text-align:center; color:white;'><b>{mezzo}</b>: {info}</div>", unsafe_allow_html=True)

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
                            # Cerchiamo la riga
                            cella = ws.find(str(p['CLIENTE']))
                            # Troviamo la colonna VISITATO
                            headers = [h.upper() for h in ws.row_values(1)]
                            idx_v = headers.index("VISITATO") + 1
                            ws.update_cell(cella.row, idx_v, "SI")
                            
                            st.session_state.giro_igt.pop(i)
                            parla("Tappa completata")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore salvataggio: {e}")
                            
