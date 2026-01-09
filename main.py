import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import datetime, timedelta
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials
import time

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar Pro Navigator", page_icon="⭐", layout="wide")
SEDE = (43.661888, 11.305728) # Strada in Chianti

st.markdown("""<style>.stApp { background-color: #001a41; } .header-box { background-color: #00122e; padding: 20px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 25px; } .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 8px; color: white; }</style>""", unsafe_allow_html=True)

# --- 2. CONNESSIONE CON CACHE (EVITA ERRORE 503) ---
@st.cache_resource(ttl=600) # Mantiene la connessione per 10 minuti
def get_gsheet_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

def carica_dati_sicuro(ws):
    try:
        all_v = ws.get_all_values()
        if len(all_v) > 1:
            headers = [str(h).strip().upper() for h in all_v[0]]
            df = pd.DataFrame(all_v[1:], columns=headers)
            for c in ['CODICE', 'TELEFONO', 'CAP']: 
                if c in df.columns: df[c] = df[c].astype(str).str.replace('.0','', regex=False).str.strip()
            return df
        return None
    except Exception as e:
        if "503" in str(e):
            st.warning("⚠️ Google è momentaneamente occupato. Riprovo tra 3 secondi...")
            time.sleep(3)
            return carica_dati_sicuro(ws)
        st.error(f"Errore caricamento: {e}")
        return None

# --- 3. LOGICA PRINCIPALE ---
st.title("⭐ BRIGHTSTAR PRO NAVIGATOR")

# INSERISCI IL TUO ID
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" 

client = get_gsheet_client()
if client:
    try:
        ws = client.open_by_key(ID_DEL_FOGLIO).get_worksheet(0)
        
        if 'df_db' not in st.session_state:
            st.session_state.df_db = carica_dati_sicuro(ws)
        
        df = st.session_state.df_db
        
        if df is not None:
            df_liberi = df[~df['VISITATO'].astype(str).str.upper().str.contains('SI|SÌ', na=False)]

            with st.container():
                st.markdown("<div class='header-box'>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                with c1: sel_comuni = st.multiselect("📍 Comuni:", sorted(df['COMUNE'].unique().tolist()))
                with c2: sel_caps = st.multiselect("📮 CAP:", sorted(df['CAP'].unique().tolist()))
                with c3: forzati = st.multiselect("📌 Prioritari:", sorted(df['CLIENTE'].unique().tolist()))
                
                num_tappe = st.slider("Numero visite:", 5, 20, 10)
                
                if st.button("🚀 GENERA GIRO OTTIMIZZATO"):
                    with st.spinner("Pianificazione in corso..."):
                        # Selezione
                        giro_raw = df[df['CLIENTE'].isin(forzati)].to_dict('records')
                        mask = df['CLIENTE'].isin(df_liberi['CLIENTE']) & ~df['CLIENTE'].isin(forzati)
                        if sel_comuni: mask &= df['COMUNE'].isin(sel_comuni)
                        if sel_caps: mask &= df['CAP'].isin(sel_caps)
                        extra = df[mask].head(num_tappe - len(giro_raw)).to_dict('records')
                        giro_raw.extend(extra)
                        
                        # Geocoding e Ordinamento per Comune (Antirimbalzo)
                        geo = Nominatim(user_agent="brightstar_final_v13")
                        # Ordiniamo prima il DataFrame per Comune per garantire il raggruppamento
                        df_ordinato = pd.DataFrame(giro_raw).sort_values(by=['COMUNE', 'INDIRIZZO'])
                        giro_lista = df_ordinato.to_dict('records')

                        opt = []
                        punto_precedente = SEDE
                        ora = datetime.now().replace(hour=7, minute=30, second=0)
                        
                        for p in giro_lista:
                            try:
                                loc = geo.geocode(f"{p['INDIRIZZO']}, {p['CAP']}, {p['COMUNE']}, Italy", timeout=5)
                                coords = (loc.latitude, loc.longitude) if loc else SEDE
                            except: coords = SEDE
                            
                            dist = geodesic(punto_precedente, coords).km
                            ora += timedelta(minutes=(dist/35)*60)
                            p['ora_arrivo'] = ora.strftime("%H:%M")
                            ora += timedelta(minutes=30)
                            p['ora_partenza'] = ora.strftime("%H:%M")
                            p['coords'] = coords
                            opt.append(p)
                            punto_precedente = coords
                        
                        st.session_state.giro_igt = opt
                        st.session_state.rientro = (ora + timedelta(minutes=(geodesic(punto_precedente, SEDE).km/35)*60)).strftime("%H:%M")
                        st.rerun()

            if 'giro_igt' in st.session_state:
                st.info(f"📍 Rientro stimato a Strada in Chianti: **{st.session_state.rientro}**")
                for i, p in enumerate(st.session_state.giro_igt):
                    with st.container():
                        st.markdown(f"""<div class="tappa-card"><b>{i+1}. {p['CLIENTE']}</b> (Arrivo: {p['ora_arrivo']})<br>📍 {p['COMUNE']} - {p['INDIRIZZO']}</div>""", unsafe_allow_html=True)
                        c1, c2 = st.columns(2)
                        with c1: st.link_button("🚙 WAZE", f"https://waze.com/ul?q={p['INDIRIZZO']}%20{p['COMUNE']}&navigate=yes")
                        with c2:
                            if st.button("✅ FATTO", key=f"f_{i}"):
                                try:
                                    riga = ws.find(str(p['CLIENTE']))
                                    ws.update_cell(riga.row, list(df.columns).index("VISITATO")+1, "SI")
                                    st.session_state.giro_igt.pop(i)
                                    st.rerun()
                                except: st.error("Errore salvataggio. Riprova.")
    except Exception as e:
        st.error(f"Errore accesso al foglio: {e}")
