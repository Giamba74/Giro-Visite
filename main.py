import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import datetime
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar PRO", page_icon="⭐", layout="wide")

st.markdown("""<style>.stApp { background-color: #001a41; } .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 5px; color: white; }</style>""", unsafe_allow_html=True)

# --- 2. CONNESSIONE ---
@st.cache_resource(show_spinner="Connessione a Google Sheets...")
def connetti_google():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        
        # CAMBIA QUESTO CON IL NOME ESATTO
        sh = client.open("GiroVisite_Dati") 
        return sh.get_worksheet(0)
    except Exception as e:
        st.error(f"Errore connessione: {e}")
        return None

# --- 3. LOGICA PRINCIPALE ---
st.title("⭐ BRIGHTSTAR PRO")

ws = connetti_google()

if ws:
    # Carichiamo i dati una volta sola per sessione per non rallentare
    if 'df_lavoro' not in st.session_state:
        with st.spinner("Caricamento dati..."):
            records = ws.get_all_records()
            df = pd.DataFrame(records)
            df.columns = [str(c).strip().upper() for c in df.columns]
            st.session_state.df_lavoro = df
    
    df = st.session_state.df_lavoro

    # Filtro: solo non visitati
    if 'VISITATO' in df.columns:
        df_liberi = df[~df['VISITATO'].astype(str).str.upper().str.contains('SI|SÌ', na=False)]
    else:
        st.error("Colonna 'VISITATO' non trovata!")
        df_liberi = df

    with st.container():
        st.write("### 🛠️ Configura il giro")
        c1, c2 = st.columns(2)
        with c1:
            comuni = st.multiselect("Comuni:", sorted(df['COMUNE'].unique().tolist()) if 'COMUNE' in df.columns else [])
        with c2:
            forzati = st.multiselect("Clienti Obbligatori:", sorted(df['CLIENTE'].unique().tolist()) if 'CLIENTE' in df.columns else [])
        
        if st.button("🚀 GENERA 10 VISITE"):
            with st.status("Calcolo percorso ottimale..."):
                # Selezione
                giro = df[df['CLIENTE'].isin(forzati)].to_dict('records')
                mask = df['CLIENTE'].isin(df_liberi['CLIENTE']) & ~df['CLIENTE'].isin(forzati)
                if comuni: mask &= df['COMUNE'].isin(comuni)
                
                extra = df[mask].head(10 - len(giro)).to_dict('records')
                giro.extend(extra)
                
                # Geocoding veloce (solo per i 10 eletti)
                geolocator = Nominatim(user_agent="bright_fast_v1")
                for r in giro:
                    addr = f"{r.get('INDIRIZZO','')}, {r.get('COMUNE','')}, Italy"
                    try:
                        l = geolocator.geocode(addr, timeout=3)
                        r['coords'] = (l.latitude, l.longitude) if l else (43.6, 11.3)
                    except:
                        r['coords'] = (43.6, 11.3)
                
                # Ordinamento base
                st.session_state.giro_igt = giro
                st.rerun()

    # --- LISTA RISULTATI ---
    if 'giro_igt' in st.session_state and st.session_state.giro_igt:
        st.success(f"Giro generato: {len(st.session_state.giro_igt)} tappe")
        
        for i, p in enumerate(st.session_state.giro_igt):
            with st.container():
                st.markdown(f"""<div class="tappa-card"><b>{i+1}. {p['CLIENTE']}</b><br>📍 {p['COMUNE']} - {p['INDIRIZZO']}</div>""", unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.link_button("🚙 NAVIGA", f"https://waze.com/ul?q={p['INDIRIZZO'].replace(' ','%20')}%20{p['COMUNE']}&navigate=yes")
                with col2:
                    if st.button("✅ FATTO", key=f"f_{i}"):
                        try:
                            # Aggiorna Google Sheet
                            cella = ws.find(str(p['CLIENTE']))
                            # Trova colonna VISITATO
                            headers = [h.upper() for h in ws.row_values(1)]
                            idx_v = headers.index("VISITATO") + 1
                            ws.update_cell(cella.row, idx_v, "SI")
                            
                            # Rimuovi dalla lista e aggiorna lo stato locale
                            st.session_state.giro_igt.pop(i)
                            st.session_state.df_lavoro.loc[st.session_state.df_lavoro['CLIENTE'] == p['CLIENTE'], 'VISITATO'] = "SI"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore: {e}")
