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
SEDE = (43.661888, 11.305728)

st.markdown("""<style>.stApp { background-color: #001a41; } .header-box { background-color: #00122e; padding: 20px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 25px; } .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 8px; color: white; }</style>""", unsafe_allow_html=True)

# --- 2. FUNZIONE DI CONNESSIONE DIAGNOSTICA ---
def get_gsheet_ws(sheet_id):
    if sheet_id == "IL_TUO_ID_LUNGO_QUI" or not sheet_id:
        st.error("❌ Errore: Non hai inserito l'ID del foglio alla riga 55 del codice!")
        return None
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(sheet_id).get_worksheet(0)
    except Exception as e:
        st.error(f"❌ Errore di connessione: {e}")
        st.info("Assicurati di aver condiviso il foglio con l'email del Service Account.")
        return None

# --- 3. APP ---
st.title("⭐ BRIGHTSTAR PRO NAVIGATOR")

# --- INSERISCI QUI IL TUO ID ---
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" 

ws = get_gsheet_ws(ID_DEL_FOGLIO)

if ws:
    st.success("✅ Connesso al database!")
    
    # Caricamento dati forzato
    try:
        all_v = ws.get_all_values()
        if len(all_v) > 1:
            headers = [str(h).strip().upper() for h in all_v[0]]
            df = pd.DataFrame(all_v[1:], columns=headers)
            for c in ['CODICE', 'TELEFONO', 'CAP']: 
                if c in df.columns: df[c] = df[c].astype(str).str.replace('.0','', regex=False)
            
            # Mostra i filtri solo se i dati sono caricati
            df_liberi = df[~df['VISITATO'].astype(str).str.upper().str.contains('SI|SÌ', na=False)]
            
            with st.container():
                st.markdown("<div class='header-box'>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                with c1: sel_comuni = st.multiselect("📍 Comuni:", sorted(df['COMUNE'].unique().tolist()))
                with c2: sel_caps = st.multiselect("📮 CAP:", sorted(df['CAP'].unique().tolist()))
                with c3: forzati = st.multiselect("📌 Prioritari:", sorted(df['CLIENTE'].unique().tolist()))
                
                num_tappe = st.slider("Numero visite:", 5, 20, 10)
                
                if st.button("🚀 GENERA GIRO"):
                    # ... (resto della logica di ottimizzazione tappe)
                    giro = df[df['CLIENTE'].isin(forzati)].to_dict('records')
                    mask = df['CLIENTE'].isin(df_liberi['CLIENTE']) & ~df['CLIENTE'].isin(forzati)
                    if sel_comuni: mask &= df['COMUNE'].isin(sel_comuni)
                    if sel_caps: mask &= df['CAP'].isin(sel_caps)
                    extra = df[mask].head(num_tappe - len(giro)).to_dict('records')
                    giro.extend(extra)
                    
                    # Calcolo Geografico e Orario
                    geo = Nominatim(user_agent="brightstar_final")
                    for r in giro:
                        try:
                            loc = geo.geocode(f"{r['INDIRIZZO']}, {r['CAP']}, {r['COMUNE']}, Italy", timeout=3)
                            r['coords'] = (loc.latitude, loc.longitude) if loc else SEDE
                        except: r['coords'] = SEDE

                    # Ordinamento per Comune (Anti-Rimbalzo)
                    df_giro = pd.DataFrame(giro)
                    df_giro['ORDINE_COMUNE'] = df_giro['COMUNE'].apply(lambda x: geodesic(SEDE, geo.geocode(f"{x}, Italy")).km if x else 0)
                    giro_ordinato = df_giro.sort_values(by=['ORDINE_COMUNE', 'COMUNE']).to_dict('records')

                    opt = []
                    punto = SEDE
                    ora = datetime.now().replace(hour=7, minute=30, second=0)
                    for prox in giro_ordinato:
                        dist = geodesic(punto, prox['coords']).km
                        ora += timedelta(minutes=(dist/35)*60)
                        prox['ora_arrivo'] = ora.strftime("%H:%M")
                        ora += timedelta(minutes=30)
                        prox['ora_partenza'] = ora.strftime("%H:%M")
                        opt.append(prox); punto = prox['coords']
                    
                    st.session_state.giro_igt = opt
                    st.session_state.rientro = (ora + timedelta(minutes=(geodesic(punto, SEDE).km/35)*60)).strftime("%H:%M")
                    st.rerun()
                    
            # Visualizzazione risultati
            if 'giro_igt' in st.session_state:
                st.info(f"📍 Rientro stimato: {st.session_state.rientro}")
                for i, p in enumerate(st.session_state.giro_igt):
                    st.markdown(f"""<div class="tappa-card"><b>{i+1}. {p['CLIENTE']}</b> ({p['ora_arrivo']})<br>📍 {p['COMUNE']} - {p['INDIRIZZO']}</div>""", unsafe_allow_html=True)
                    if st.button("✅ FATTO", key=f"f_{i}"):
                        riga = ws.find(str(p['CLIENTE']))
                        ws.update_cell(riga.row, headers.index("VISITATO")+1, "SI")
                        st.session_state.giro_igt.pop(i)
                        st.rerun()
        else:
            st.warning("Il foglio Google sembra non avere righe di dati sotto l'intestazione.")
    except Exception as e:
        st.error(f"Errore durante il caricamento dei dati dal foglio: {e}")
