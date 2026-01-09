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
SEDE_COORDS = (43.661888, 11.305728) # Strada in Chianti (Via Ferrero)
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")

st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 20px; border-radius: 15px; border: 2px solid #FFD700; margin-bottom: 20px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 8px; color: white; }
    .indirizzo-testo { color: #FFD700; font-size: 0.95em; font-weight: bold; margin-bottom: 5px; }
    .time-badge { background-color: #FFD700; color: #001a41; padding: 2px 8px; border-radius: 5px; font-weight: bold; }
    .warning-text { color: #ff4b4b; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNZIONI ---
def get_google_data(nome, indirizzo, comune):
    if not API_KEY: return None
    # Tentativo 1: Ricerca precisa
    query = f"{indirizzo}, {comune}, Italy"
    try:
        url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={urllib.parse.quote(query)}&key={API_KEY}"
        res = requests.get(url).json()
        if res.get('status') == 'OK' and res.get('results'):
            res0 = res['results'][0]
            return {
                "coords": (res0['geometry']['location']['lat'], res0['geometry']['location']['lng']),
                "tel": res0.get('formatted_phone_number', ''),
                "found": True
            }
        
        # Tentativo 2: Solo Nome e Comune (se indirizzo è sbagliato)
        query_bis = f"{nome}, {comune}, Italy"
        res_bis = requests.get(f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={urllib.parse.quote(query_bis)}&key={API_KEY}").json()
        if res_bis.get('status') == 'OK' and res_bis.get('results'):
            res0 = res_bis['results'][0]
            return {
                "coords": (res0['geometry']['location']['lat'], res0['geometry']['location']['lng']),
                "tel": res0.get('formatted_phone_number', ''),
                "found": True
            }
    except: return None
    return None

# --- 3. DATI ---
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0"

@st.cache_resource
def init_gsheet(sheet_id):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        return gspread.authorize(creds).open_by_key(sheet_id).get_worksheet(0)
    except: return None

ws = init_gsheet(ID_DEL_FOGLIO)

if ws:
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=[h.strip().upper() for h in data[0]])
    
    # Rilevamento Colonne
    c_cliente = next((c for c in df.columns if "CLIENTE" in c), "CLIENTE")
    c_indirizzo = next((c for c in df.columns if "INDIRIZZO" in c or "VIA" in c), "INDIRIZZO")
    c_comune = next((c for c in df.columns if "COMUNE" in c), "COMUNE")
    c_cap = next((c for c in df.columns if "CAP" in c), "CAP")
    c_codice = next((c for c in df.columns if "CODICE" in c), "CODICE")
    c_tel = next((c for c in df.columns if "TELEFONO" in c), "TELEFONO")
    c_visitato = next((c for c in df.columns if "VISITATO" in c), "VISITATO")

    if not API_KEY:
        st.error("⚠️ ATTENZIONE: Google Maps API Key non trovata! La navigazione non funzionerà.")

    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1: sel_comuni = st.multiselect("📍 Filtra Zona:", sorted(df[c_comune].unique().tolist()))
        with col2: tappe_max = st.slider("Numero visite:", 5, 20, 10)
        
        if st.button("🚀 GENERA GIRO OTTIMIZZATO"):
            mask = ~df[c_visitato].str.contains('SI|SÌ', case=False, na=False)
            if sel_comuni: mask &= df[c_comune].isin(sel_comuni)
            potenziali = df[mask].to_dict('records')

            if potenziali:
                with st.spinner("Calcolo coordinate e rotta..."):
                    for p in potenziali:
                        g_data = get_google_data(p[c_cliente], p[c_indirizzo], p[c_comune])
                        
                        if g_data and g_data['found']:
                            p['coords'] = g_data['coords']
                            p['g_tel'] = g_data['tel']
                            p['valid_pos'] = True
                        else:
                            # Fallback SOLO per il calcolo, ma lo segnaliamo
                            p['coords'] = SEDE_COORDS
                            p['g_tel'] = p.get(c_tel, '')
                            p['valid_pos'] = False

                        # Angolo
                        p['angle'] = np.arctan2(p['coords'][0] - SEDE_COORDS[0], p['coords'][1] - SEDE_COORDS[1])
                    
                    # Ordiniamo
                    df_opt = pd.DataFrame(potenziali).sort_values(by=[c_comune, c_cap, 'angle'])
                    
                    giro_final = []
                    punto_att = SEDE_COORDS
                    ora_att = datetime.now().replace(hour=7, minute=30, second=0)
                    
                    for _, r in df_opt.head(tappe_max).iterrows():
                        dist = geodesic(punto_att, r['coords']).km
                        ora_arrivo = ora_att + timedelta(minutes=(dist/35)*60)
                        giro_final.append({
                            "NOME": r[c_cliente], "COD": r[c_codice], "ORA": ora_arrivo.strftime("%H:%M"),
                            "TEL": r['g_tel'], "LAT": r['coords'][0], "LON": r['coords'][1], 
                            "COMUNE": r[c_comune], "CAP": r[c_cap], "VIA": r[c_indirizzo], "NOTE": "",
                            "VALID_POS": r['valid_pos']
                        })
                        ora_att = ora_arrivo + timedelta(minutes=35)
                        punto_att = (r['coords'][0], r['coords'][1])
                    st.session_state.giro_igt = giro_final
                    st.rerun()

    # --- 4. VISUALIZZAZIONE RISULTATI ---
    if 'giro_igt' in st.session_state:
        for i, p in enumerate(st.session_state.giro_igt):
            with st.container():
                st.markdown(f"""
                <div class="tappa-card">
                    <div style="display:flex; justify-content:space-between">
                        <b>{i+1}. {p['NOME']}</b>
                        <span class="time-badge">{p['ORA']}</span>
                    </div>
                    <div class="indirizzo-testo">📍 {p['VIA']}, {p['COMUNE']}</div>
                    <small>Codice Cliente: {p['COD']}</small>
                </div>
                """, unsafe_allow_html=True)
                
                # Note
                st.session_state.giro_igt[i]['NOTE'] = st.text_area(f"Note per {p['NOME']}:", value=p['NOTE'], key=f"note_{i}", height=70)
                
                c1, c2, c3 = st.columns(3)
                with c1: 
                    # LINK NAVIGAZIONE CORRETTO
                    if p['VALID_POS']:
                        # Usa formato universale https://www.google.com/maps/dir/?api=1...
                        nav_url = f"https://www.google.com/maps/dir/?api=1&destination={p['LAT']},{p['LON']}&travelmode=driving"
                        st.link_button("🚙 NAVIGA", nav_url)
                    else:
                        st.warning("⚠️ Posizione non trovata")
                with c2: 
                    if p['TEL']: st.link_button("📞 CHIAMA", f"tel:{p['TEL']}")
                with c3:
                    if st.button("✅ FATTO", key=f"f_{i}"):
                        st.success("Tappa completata!")

        if st.button("📧 FINISCI E INVIA REPORT"):
            report = [f"{p['NOME']}: {p['NOTE']}" for p in st.session_state.giro_igt if p['NOTE'].strip()]
            if report: st.info("Report note generato!")
            else: st.warning("Nessuna nota inserita.")
