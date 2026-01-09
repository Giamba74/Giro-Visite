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
st.set_page_config(page_title="Brightstar Google AI Pro", page_icon="⭐", layout="wide")
SEDE = (43.661888, 11.305728) # Strada in Chianti
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")

st.markdown("""<style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 20px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 20px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 8px; color: white; }
    .badge-open { background-color: #28a745; color: white; padding: 3px 10px; border-radius: 10px; font-size: 0.8em; font-weight: bold; }
    .badge-closed { background-color: #ff4b4b; color: white; padding: 3px 10px; border-radius: 10px; font-size: 0.8em; font-weight: bold; }
</style>""", unsafe_allow_html=True)

# --- 2. FUNZIONI GOOGLE PLACES (Corrette per evitare 404) ---
def get_google_live_data(nome, indirizzo, comune):
    # Usiamo l'endpoint ufficiale Places Text Search
    q = f"{nome} {comune} Italy"
    try:
        search_url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={urllib.parse.quote(q)}&key={API_KEY}"
        res = requests.get(search_url).json()
        
        if res.get('status') == 'OK' and res.get('results'):
            p_id = res['results'][0]['place_id']
            # Chiamata Place Details ufficiale
            det_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={p_id}&fields=opening_hours,formatted_phone_number,geometry&key={API_KEY}"
            det_res = requests.get(det_url).json()
            
            if det_res.get('status') == 'OK':
                det = det_res.get('result', {})
                return {
                    "coords": (det['geometry']['location']['lat'], det['geometry']['location']['lng']),
                    "periods": det.get('opening_hours', {}).get('periods', []),
                    "tel": det.get('formatted_phone_number', '')
                }
    except Exception as e:
        st.error(f"Errore chiamata API Google: {e}")
    return None

def is_open_check(ora_str, periods):
    if not periods: return True
    giorno_goog = (datetime.now().weekday() + 1) % 7
    ora_int = int(ora_str.replace(":", ""))
    for p in periods:
        if p['open']['day'] == giorno_goog:
            apre = int(p['open']['time'])
            chiude = int(p['close']['time'])
            if apre <= ora_int <= chiude: return True
    return False

# --- 3. LOGICA PRINCIPALE ---
st.title("⭐ BRIGHTSTAR GOOGLE AI")

ID_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" # <--- METTI IL TUO ID QUI

@st.cache_resource
def init_gs():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], 
                                                    scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Errore Google Sheets: {e}")
        return None

gc = init_gs()

if gc:
    try:
        ws = gc.open_by_key(ID_FOGLIO).get_worksheet(0)
        data = ws.get_all_values()
        df = pd.DataFrame(data[1:], columns=[h.upper() for h in data[0]])
        
        if 'CAP' in df.columns:
            df['CAP'] = df['CAP'].astype(str).str.replace('.0', '', regex=False).str.strip()

        with st.container():
            st.markdown("<div class='header-box'>", unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                sel_comuni = st.multiselect("📍 Comune:", sorted(df['COMUNE'].unique().tolist()))
            with col2:
                sel_caps = st.multiselect("📮 CAP:", sorted(df['CAP'].unique().tolist()))
            
            mask = pd.Series([True] * len(df))
            if sel_comuni: mask &= df['COMUNE'].isin(sel_comuni)
            if sel_caps: mask &= df['CAP'].isin(sel_caps)
            mask &= ~df['VISITATO'].str.contains('SI|SÌ', case=False, na=False)
            
            df_filtrato = df[mask]
            sel_clienti = st.multiselect("🎯 Scegli clienti:", df_filtrato['CLIENTE'].tolist())
            
            if st.button("🚀 GENERA GIRO"):
                if not API_KEY:
                    st.error("Manca la GOOGLE_MAPS_API_KEY nei Secrets!")
                else:
                    giro_calcolato = []
                    punto_att = SEDE
                    ora_att = datetime.now().replace(hour=7, minute=30, second=0)
                    
                    for nome in sel_clienti:
                        riga = df[df['CLIENTE']==nome].iloc[0]
                        info = get_google_live_data(nome, riga['INDIRIZZO'], riga['COMUNE'])
                        
                        if info:
                            dist = geodesic(punto_att, info['coords']).km
                            ora_arrivo = ora_att + timedelta(minutes=(dist/35)*60)
                            ora_str = ora_arrivo.strftime("%H:%M")
                            
                            giro_calcolato.append({
                                "NOME": nome, "ORA": ora_str,
                                "APERTO": is_open_check(ora_str, info['periods']),
                                "TEL": info['tel'], "COORDS": info['coords'],
                                "COMUNE": riga['COMUNE']
                            })
                            ora_att = ora_arrivo + timedelta(minutes=30)
                            punto_att = info['coords']
                    
                    st.session_state.giro_live = giro_calcolato
                    st.session_state.rientro_goog = (ora_att + timedelta(minutes=(geodesic(punto_att, SEDE).km/35)*60)).strftime("%H:%M")
                    st.rerun()

        if 'giro_live' in st.session_state and st.session_state.giro_live:
            st.info(f"🏁 Rientro: **{st.session_state.rientro_goog}**")
            for i, p in enumerate(st.session_state.giro_live):
                badge = '<span class="badge-open">APERTO ✅</span>' if p['APERTO'] else '<span class="badge-closed">CHIUSO ❌</span>'
                st.markdown(f"""<div class="tappa-card">
                    <b>{i+1}. {p['NOME']}</b> {badge}<br>
                    📍 {p['COMUNE']} | Arrivo: {p['ORA']} | 📞 {p['TEL']}
                </div>""", unsafe_allow_html=True)
                
                c1, c2 = st.columns(2)
                with c1:
                    # LINK NAVIGAZIONE UFFICIALE
                    url_nav = f"https://www.google.com/maps/dir/?api=1&destination={p['COORDS'][0]},{p['COORDS'][1]}&travelmode=driving"
                    st.link_button("🚙 NAVIGA", url_nav)
                with c2:
                    if st.button("✅ FATTO", key=f"btn_{i}"):
                        r = ws.find(p['NOME'])
                        ws.update_cell(r.row, list(df.columns).index("VISITATO")+1, "SI")
                        st.session_state.giro_live.pop(i)
                        st.rerun()
    except Exception as e:
        st.error(f"Errore: {e}")
