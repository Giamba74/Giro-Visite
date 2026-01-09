import streamlit as st
import pandas as pd
import numpy as np
from geopy.distance import geodesic
from datetime import datetime, timedelta
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar Pro Intelligence", page_icon="⭐", layout="wide")
SEDE_COORDS = (43.661888, 11.305728) # Strada in Chianti
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")

st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 20px; border-radius: 15px; border: 2px solid #FFD700; margin-bottom: 20px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 8px; color: white; }
    .time-badge { background-color: #FFD700; color: #001a41; padding: 2px 8px; border-radius: 5px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNZIONI ---
def agente_meteo(lat, lon):
    try:
        res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1").json()
        temp = res['hourly']['temperature_2m'][10] 
        pioggia = max(res['hourly']['precipitation_probability'][8:18])
        if temp < 5 or pioggia > 30:
            return "AUTO 🚗", f"Meteo critico ({temp}°C / Pioggia {pioggia}%).", "#ff4b4b"
        return "ZONTES 🛵", f"Meteo ottimo ({temp}°C). Vai in scooter!", "#28a745"
    except: return "INFO ℹ️", "Meteo N/D", "#FFD700"

def get_google_data(nome, indirizzo, comune):
    if not API_KEY: return None
    query = f"{nome} {indirizzo} {comune} Italy"
    try:
        url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={urllib.parse.quote(query)}&key={API_KEY}"
        res = requests.get(url).json()
        if res.get('status') == 'OK' and res.get('results'):
            res0 = res['results'][0]
            return {
                "coords": (res0['geometry']['location']['lat'], res0['geometry']['location']['lng']),
                "tel": res0.get('formatted_phone_number', '')
            }
    except: return None

# --- 3. LOGICA DI CONNESSIONE E CALCOLO ---
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0"

@st.cache_resource
def init_gsheet(sheet_id):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(sheet_id).get_worksheet(0)
    except: return None

ws = init_gsheet(ID_DEL_FOGLIO)

if ws:
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=[h.strip().upper() for h in data[0]])
    
    # Rilevamento Colonne e Pulizia
    c_cap = next((c for c in df.columns if "CAP" in c), "CAP")
    df[c_cap] = df[c_cap].astype(str).str.replace('.0', '', regex=False).str.pad(5, fillchar='0')
    
    c_cliente = next((c for c in df.columns if "CLIENTE" in c), "CLIENTE")
    c_indirizzo = next((c for c in df.columns if "INDIRIZZO" in c or "VIA" in c), "INDIRIZZO")
    c_comune = next((c for c in df.columns if "COMUNE" in c), "COMUNE")
    c_codice = next((c for c in df.columns if "CODICE" in c), "CODICE")
    c_tel = next((c for c in df.columns if "TELEFONO" in c), "TELEFONO")
    c_visitato = next((c for c in df.columns if "VISITATO" in c), "VISITATO")

    mezzo, consiglio, colore = agente_meteo(43.66, 11.30)
    st.markdown(f"<div style='background-color:{colore}; color:white; padding:10px; border-radius:10px; text-align:center; font-weight:bold;'>{mezzo}: {consiglio}</div>", unsafe_allow_html=True)

    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1: sel_comuni = st.multiselect("📍 Comuni:", sorted(df[c_comune].unique().tolist()))
        with col2: sel_caps = st.multiselect("📮 CAP (es. Firenze):", sorted(df[c_cap].unique().tolist()))
        with col3: tappe_max = st.slider("Numero tappe:", 5, 20, 10)
        
        inverti = st.checkbox("Inverti giro (inizia dal più lontano)")
        
        if st.button("🚀 GENERA GIRO OTTIMIZZATO"):
            mask = ~df[c_visitato].str.contains('SI|SÌ', case=False, na=False)
            if sel_comuni: mask &= df[c_comune].isin(sel_comuni)
            if sel_caps: mask &= df[c_cap].isin(sel_caps)
            
            potenziali = df[mask].to_dict('records')

            if not potenziali:
                st.warning("Nessun cliente trovato!")
            else:
                with st.spinner("Calcolo logistico zonale..."):
                    for p in potenziali:
                        g_data = get_google_data(p[c_cliente], p[c_indirizzo], p[c_comune])
                        p['coords'] = g_data['coords'] if g_data else SEDE_COORDS
                        p['g_tel'] = g_data['tel'] if g_data else p.get(c_tel, '')
                        # Calcolo angolo e distanza per ordinamento a zone
                        p['angle'] = np.arctan2(p['coords'][0] - SEDE_COORDS[0], p['coords'][1] - SEDE_COORDS[1])
                        p['dist_casa'] = geodesic(SEDE_COORDS, p['coords']).km

                    # ORDINAMENTO: Comune -> CAP -> Angolo -> Distanza
                    df_opt = pd.DataFrame(potenziali).sort_values(by=[c_comune, c_cap, 'angle', 'dist_casa'], ascending=not inverti)
                    
                    giro_final = []
                    punto_att = SEDE_COORDS
                    ora_att = datetime.now().replace(hour=7, minute=30, second=0)
                    
                    for _, r in df_opt.head(tappe_max).iterrows():
                        dist = geodesic(punto_att, r['coords']).km
                        ora_arrivo = ora_att + timedelta(minutes=(dist/35)*60)
                        
                        # Salvataggio ESPLICITO di tutte le chiavi per evitare KeyError
                        giro_final.append({
                            "NOME": r[c_cliente], 
                            "COD": r[c_codice], 
                            "ORA": ora_arrivo.strftime("%H:%M"),
                            "TEL": r['g_tel'], 
                            "COORDS": r['coords'], 
                            "COMUNE": r[c_comune], 
                            "CAP": r[c_cap]
                        })
                        ora_att = ora_arrivo + timedelta(minutes=35)
                        punto_att = r['coords']

                    st.session_state.giro_igt = giro_final
                    st.session_state.rientro = (ora_att + timedelta(minutes=(geodesic(punto_att, SEDE_COORDS).km/35)*60)).strftime("%H:%M")
                    st.rerun()

    # --- 4. VISUALIZZAZIONE RISULTATI ---
    if 'giro_igt' in st.session_state:
        st.info(f"🏁 Rientro a Strada in Chianti: **{st.session_state.rientro}**")
        for i, p in enumerate(st.session_state.giro_igt):
            st.markdown(f"""
            <div class="tappa-card">
                <div style="display:flex; justify-content:space-between">
                    <b>{i+1}. {p['NOME']}</b>
                    <span class="time-badge">{p['ORA']}</span>
                </div>
                <small>Cod: {p['COD']} | 📍 {p['CAP']} {p['COMUNE']}</small>
            </div>
            """, unsafe_allow_html=True)
            
            c1, c2, c3 = st.columns(3)
            with c1: st.link_button("🚙 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={p['COORDS'][0]},{p['COORDS'][1]}")
            with c2: 
                if p['TEL']: st.link_button("📞 CHIAMA", f"tel:{p['TEL']}")
            with c3:
                if st.button("✅ FATTO", key=f"f_{i}"):
                    cell = ws.find(p['NOME'])
                    ws.update_cell(cell.row, list(df.columns).index(c_visitato)+1, "SI")
                    st.session_state.giro_igt.pop(i)
                    st.rerun()
