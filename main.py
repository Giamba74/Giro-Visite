import streamlit as st
import pandas as pd
from geopy.distance import geodesic
from datetime import datetime, timedelta
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE ---
st.set_page_config(page_title="Brightstar Pro Navigator", page_icon="⭐", layout="wide")
SEDE = (43.661888, 11.305728) # Strada in Chianti
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")

st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 20px; border-radius: 15px; border: 2px solid #FFD700; margin-bottom: 25px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 8px; color: white; }
    .badge-open { background-color: #28a745; color: white; padding: 3px 10px; border-radius: 10px; font-size: 0.8em; font-weight: bold; }
    .badge-closed { background-color: #ff4b4b; color: white; padding: 3px 10px; border-radius: 10px; font-size: 0.8em; font-weight: bold; }
    .time-badge { background-color: #FFD700; color: #001a41; padding: 2px 8px; border-radius: 5px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNZIONI INTELLIGENTI ---
def agente_meteo(lat, lon):
    try:
        res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1").json()
        temp = res['hourly']['temperature_2m'][10] # Temperatura ore 10:00
        pioggia = max(res['hourly']['precipitation_probability'][8:18])
        if temp < 5 or pioggia > 30:
            return "AUTO 🚗", f"Meteo critico ({temp}°C / Pioggia {pioggia}%). Usa l'auto.", "#ff4b4b"
        return "ZONTES 🛵", f"Meteo ottimo ({temp}°C). Vai in scooter!", "#28a745"
    except: return "INFO ℹ️", "Meteo non disponibile", "#FFD700"

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

# --- 3. CONNESSIONE ---
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
    
    # Rilevamento Colonne
    c_cliente = next((c for c in df.columns if "CLIENTE" in c), "CLIENTE")
    c_indirizzo = next((c for c in df.columns if "INDIRIZZO" in c or "VIA" in c), "INDIRIZZO")
    c_comune = next((c for c in df.columns if "COMUNE" in c), "COMUNE")
    c_codice = next((c for c in df.columns if "CODICE" in c), "CODICE")
    c_tel = next((c for c in df.columns if "TELEFONO" in c), "TELEFONO")
    c_visitato = next((c for c in df.columns if "VISITATO" in c), "VISITATO")

    # Meteo in alto
    mezzo, consiglio, colore = agente_meteo(43.66, 11.30)
    st.markdown(f"<div style='background-color:{colore}; color:white; padding:10px; border-radius:10px; text-align:center; font-weight:bold; margin-bottom:20px;'>{mezzo}: {consiglio}</div>", unsafe_allow_html=True)

    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        with col_a: sel_comuni = st.multiselect("📍 Comune:", sorted(df[c_comune].unique().tolist()))
        with col_b: num_visite = st.number_input("Tappe massime:", 1, 20, 10)
        
        mask = ~df[c_visitato].str.contains('SI|SÌ', case=False, na=False)
        if sel_comuni: mask &= df[c_comune].isin(sel_comuni)
        
        df_filtrato = df[mask]
        lista_nomi = df_filtrato[c_cliente].tolist()
        sel_clienti = st.multiselect("🎯 Clienti individuati:", lista_nomi, default=lista_nomi[:num_visite])

        if st.button("🚀 GENERA GIRO INTELLIGENTE"):
            with st.spinner("Ottimizzazione percorso in corso..."):
                giro_ris = []
                punto_att = SEDE
                ora_att = datetime.now().replace(hour=8, minute=30, second=0)
                
                # Ottimizzazione: ordiniamo i clienti per distanza dal punto precedente
                rimanenti = [df[df[c_cliente] == n].iloc[0] for n in sel_clienti]
                
                while rimanenti and len(giro_ris) < num_visite:
                    # Trova il più vicino
                    prox_riga = min(rimanenti, key=lambda x: geodesic(punto_att, get_google_live_data(x[c_cliente], x[c_indirizzo], x[c_comune])['coords'] if API_KEY else SEDE).km)
                    
                    info = get_google_live_data(prox_riga[c_cliente], prox_riga[c_indirizzo], prox_riga[c_comune])
                    coords = info['coords'] if info else SEDE
                    
                    dist = geodesic(punto_att, coords).km
                    ora_arrivo = ora_att + timedelta(minutes=(dist/35)*60)
                    
                    giro_ris.append({
                        "NOME": prox_riga[c_cliente], "ORA": ora_arrivo.strftime("%H:%M"),
                        "APERTO": is_open_check(ora_arrivo.strftime("%H:%M"), info['periods'] if info else []),
                        "TEL": info['tel'] if info else prox_riga[c_tel],
                        "COD": prox_riga[c_codice], "COORDS": coords, "COMUNE": prox_riga[c_comune]
                    })
                    ora_att = ora_arrivo + timedelta(minutes=30)
                    punto_att = coords
                    rimanenti = [r for r in rimanenti if r[c_cliente] != prox_riga[c_cliente]]

                st.session_state.giro_igt = giro_ris
                st.session_state.rientro = (ora_att + timedelta(minutes=(geodesic(punto_att, SEDE).km/35)*60)).strftime("%H:%M")
                st.rerun()

    if 'giro_igt' in st.session_state and st.session_state.giro_igt:
        st.info(f"🏁 Rientro previsto: **{st.session_state.rientro}**")
        for i, p in enumerate(st.session_state.giro_igt):
            badge = '<span class="badge-open">APERTO ✅</span>' if p['APERTO'] else '<span class="badge-closed">CHIUSO ❌</span>'
            st.markdown(f"""
            <div class="tappa-card">
                <div style="display:flex; justify-content:space-between">
                    <b>{i+1}. {p['NOME']}</b> {badge}
                </div>
                <small>Codice: {p['COD']} | 📍 {p['COMUNE']}</small><br>
                <span class="time-badge">Arrivo: {p['ORA']}</span>
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
