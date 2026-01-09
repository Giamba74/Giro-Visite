import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import datetime, timedelta
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Brightstar Google AI Pro", page_icon="⭐", layout="wide")
SEDE = (43.661888, 11.305728) # Strada in Chianti
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")

st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 20px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 25px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 8px; color: white; }
    .badge-open { background-color: #28a745; color: white; padding: 3px 10px; border-radius: 10px; font-size: 0.8em; font-weight: bold; }
    .badge-closed { background-color: #ff4b4b; color: white; padding: 3px 10px; border-radius: 10px; font-size: 0.8em; font-weight: bold; }
    .time-badge { background-color: #FFD700; color: #001a41; padding: 2px 8px; border-radius: 5px; font-weight: bold; font-size: 0.9em; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNZIONI GOOGLE API ---
def get_google_live_data(nome, indirizzo, comune):
    if not API_KEY: return None
    q = f"{nome} {indirizzo} {comune} Italy"
    try:
        url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={urllib.parse.quote(q)}&key={API_KEY}"
        res = requests.get(url).json()
        if res.get('status') == 'OK' and res.get('results'):
            p_id = res['results'][0]['place_id']
            det_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={p_id}&fields=opening_hours,formatted_phone_number,geometry&key={API_KEY}"
            det = requests.get(det_url).json().get('result', {})
            return {
                "coords": (det['geometry']['location']['lat'], det['geometry']['location']['lng']),
                "periods": det.get('opening_hours', {}).get('periods', []),
                "tel": det.get('formatted_phone_number', '')
            }
    except: return None
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

# INSERISCI L'ID DEL TUO FOGLIO QUI
ID_DEL_FOGLIO = "IL_TUO_ID_LUNGO_QUI" 

@st.cache_resource
def init_gsheet(sheet_id):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(sheet_id).get_worksheet(0)
    except Exception as e:
        st.error(f"Errore connessione: {e}")
        return None

ws = init_gsheet(ID_DEL_FOGLIO)

if ws:
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
                st.warning("⚠️ Google Maps API Key non trovata nei Secrets.")
            
            with st.spinner("Pianificazione in corso..."):
                giro_ris = []
                punto_att = SEDE
                ora_att = datetime.now().replace(hour=7, minute=30, second=0)
                
                for nome in sel_clienti:
                    riga = df[df['CLIENTE'] == nome].iloc[0]
                    info = get_google_live_data(nome, riga['INDIRIZZO'], riga['COMUNE'])
                    
                    if info:
                        coords, tel, periods = info['coords'], info['tel'], info['periods']
                    else:
                        coords, tel, periods = SEDE, riga.get('TELEFONO', ''), []

                    dist = geodesic(punto_att, coords).km
                    ora_arrivo = ora_att + timedelta(minutes=(dist/35)*60)
                    ora_str = ora_arrivo.strftime("%H:%M")
                    
                    giro_ris.append({
                        "NOME": nome, "ORA": ora_str,
                        "APERTO": is_open_check(ora_str, periods),
                        "TEL": tel, "COORDS": coords, "COMUNE": riga['COMUNE']
                    })
                    ora_att = ora_arrivo + timedelta(minutes=30)
                    punto_att = coords
                
                st.session_state.giro_igt = giro_ris
                dist_r = geodesic(punto_att, SEDE).km
                st.session_state.rientro = (ora_att + timedelta(minutes=(dist_r/35)*60)).strftime("%H:%M")
                st.rerun()

    if 'giro_igt' in st.session_state and st.session_state.giro_igt:
        st.info(f"🏁 Rientro stimato: **{st.session_state.rientro}**")
        for i, p in enumerate(st.session_state.giro_igt):
            with st.container():
                badge = '<span class="badge-open">APERTO ✅</span>' if p['APERTO'] else '<span class="badge-closed">CHIUSO ❌</span>'
                st.markdown(f"""
                <div class="tappa-card">
                    <div style="display:flex; justify-content:space-between">
                        <b>{i+1}. {p['NOME']}</b> {badge}
                    </div>
                    <span class="time-badge">Arrivo: {p['ORA']}</span><br>
                    📍 {p['COMUNE']} | 📞 {p['TEL']}
                </div>
                """, unsafe_allow_html=True)
                
                c1, c2 = st.columns(2)
                with c1:
                    url_nav = f"https://www.google.com/maps/dir/?api=1&destination={p['COORDS'][0]},{p['COORDS'][1]}&travelmode=driving"
                    st.link_button("🚙 NAVIGA", url_nav)
                with c2:
                    if st.button("✅ FATTO", key=f"f_{i}"):
                        try:
                            cell = ws.find(p['NOME'])
                            idx = list(df.columns).index("VISITATO") + 1
                            ws.update_cell(cell.row, idx, "SI")
                            st.session_state.giro_igt.pop(i)
                            st.rerun()
                        except: st.error("Errore aggiornamento foglio.")
