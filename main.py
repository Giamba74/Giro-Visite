import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time
from datetime import datetime
import urllib.parse
import requests

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Brightstar FI-AR Navigator", page_icon="⭐", layout="wide")

# --- 2. STILE ---
st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 15px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 20px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 5px; color: white; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); color: #002D72 !important; font-weight: bold; }
    div.stButton > button[key^="f_"] { background: #28a745 !important; color: white !important; }
    div.stButton > button[key^="d_"] { background: #ff4b4b !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. AGENTI AI ---
def parla(testo):
    componente_audio = f"""<script>var msg = new SpeechSynthesisUtterance('{testo}'); msg.lang = 'it-IT'; window.speechSynthesis.speak(msg);</script>"""
    st.components.v1.html(componente_audio, height=0)

def agente_meteo_multi_zona(tappe):
    if datetime.now().weekday() >= 5: return None, None, None
    punti = [p['coords'] for p in tappe] if tappe else [(43.76, 11.24)] # Default Firenze
    min_temp, max_rain = 40, 0
    try:
        for lat, lon in punti[:3]: # Controlla i punti principali per velocità
            res = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1").json()
            min_t = min(res['hourly']['temperature_2m'][8:18])
            max_r = max(res['hourly']['precipitation_probability'][8:18])
            if min_t < min_temp: min_temp = min_t
            if max_r > max_rain: max_rain = max_r
        if min_temp < 3 or max_rain > 30:
            return "AUTO 🚗", f"Allerta FI/AR: Previsti {min_temp}°C e {max_rain}% pioggia. Usa l'auto.", "#ff4b4b"
        return "ZONTES 350D 🛵", f"Meteo OK su tutto il giro ({min_temp}°C). Vai di Zontes!", "#28a745"
    except: return "DECIDI TU", "Meteo FI/AR non disponibile", "#FFD700"

@st.cache_data(ttl=3600)
def get_coords(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="brightstar_ai_v28")
    try:
        loc = geolocator.geocode(f"{indirizzo}, {cap}, {comune}, Italy", timeout=8)
        return (loc.latitude, loc.longitude) if loc else None
    except: return None

def load_data(url):
    try:
        path = url.split("/edit")[0] + "/export?format=csv"
        df = pd.read_csv(path)
        df.columns = [str(c).strip().upper() for c in df.columns]
        mappa = {c: "Cliente" if "CLIENTE" in c else "Indirizzo" if "INDIRIZZO" in c else "CAP" if "CAP" in c else "Comune" if "COMUNE" in c else "CODICE" if "COD" in c else "TELEFONO" if "TEL" in c else "Visitato" if "VISITATO" in c else c for c in df.columns}
        df = df.rename(columns=mappa)
        df['TELEFONO'] = df['TELEFONO'].fillna("").astype(str).str.replace(".0", "", regex=False)
        return df
    except: return None

# --- 4. SESSIONE ---
if 'giro_igt' not in st.session_state: st.session_state.giro_igt = []
if 'report_serale' not in st.session_state: st.session_state.report_serale = []
SEDE_COORDS = (43.661888, 11.305728) # Strada in Chianti
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

# --- 5. INTERFACCIA ---
st.title("⭐ BRIGHTSTAR FI-AR NAVIGATOR")

mezzo, suggerimento, colore_mezzo = agente_meteo_multi_zona(st.session_state.giro_igt)
if mezzo:
    st.markdown(f"<div style='background-color:#00122e;padding:15px;border-radius:15px;border:2px solid {colore_mezzo};text-align:center;'><h3>{mezzo}</h3><p>{suggerimento}</p></div>", unsafe_allow_html=True)
    if 'saluto_fatto' not in st.session_state: parla(suggerimento); st.session_state.saluto_fatto = True

df = load_data(URL_SHEET)
if df is not None:
    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        comuni = st.multiselect("📍 Comuni FI/AR:", sorted(df['Comune'].unique().tolist()))
        forzati = st.multiselect("📌 Clienti Obbligatori:", sorted(df['Cliente'].unique().tolist()))
        if st.button("🚀 GENERA GIRO OTTIMIZZATO"):
            giro = []
            selezionati = df[df['Cliente'].isin(forzati)].to_dict('records')
            for r in selezionati:
                c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                if c: r['coords'] = c; giro.append(r)
            mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ','SI','S'])
            if comuni: mask &= (df['Comune'].isin(comuni))
            extra = df[mask].head(10).to_dict('records')
            for r in extra:
                c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                if c: r['coords'] = c; giro.append(r)
            opt = []
            pos = SEDE_COORDS
            while giro:
                prox = min(giro, key=lambda x: geodesic(pos, x['coords']).km)
                opt.append(prox); pos = prox['coords']; giro.remove(prox)
            st.session_state.giro_igt = opt
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.giro_igt:
        for i, p in enumerate(st.session_state.giro_igt):
            with st.container():
                st.markdown(f"<div class='tappa-card'><b>{i+1}. {p['Cliente']}</b> (Cod: {p.get('CODICE','N/D')})<br>📍 {p['Comune']} - {p['Indirizzo']}<br>📞 {p['TELEFONO']}</div>", unsafe_allow_html=True)
                nota = st.text_area("Note:", key=f"v_{i}")
                c1, c2, c3, c4 = st.columns(4)
                with c1: st.link_button("🚙 VAI", f"https://waze.com/ul?q={p['Indirizzo'].replace(' ','%20')}%20{p['Comune']}&navigate=yes")
                with c2: 
                    if p['TELEFONO']: st.link_button("📞 TEL", f"tel:{p['TELEFONO']}")
                with c3:
                    if st.button("✅ FATTO", key=f"f_{i}"):
                        st.session_state.report_serale.append({"cod": p.get("CODICE","N/D"), "nome": p["Cliente"], "comune": p["Comune"], "nota": nota})
                        st.session_state.giro_igt.pop(i); st.rerun()
                with c4:
                    if st.button("❌", key=f"d_{i}"): st.session_state.giro_igt.pop(i); st.rerun()

    if st.session_state.report_serale:
        st.divider()
        data_s = datetime.now().strftime("%d/%m/%Y")
        corpo = f"REPORT VISITE {data_s}\n\n"
        for r in st.session_state.report_serale:
            corpo += f"• {r['nome']} ({r['cod']}) - {r['comune']}: {r['nota']}\n"
        link = f"mailto:giambattista.giacchetti@gmail.com?subject=REPORT {data_s}&body={urllib.parse.quote(corpo)}"
        st.link_button("📧 INVIA REPORT FINALE", link, use_container_width=True)
