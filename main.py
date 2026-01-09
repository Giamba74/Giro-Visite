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
    .indirizzo-testo { color: #FFD700; font-size: 0.95em; font-weight: bold; margin-bottom: 5px; }
    .time-badge { background-color: #FFD700; color: #001a41; padding: 2px 8px; border-radius: 5px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNZIONI ---
def get_google_data(nome, indirizzo, comune):
    if not API_KEY: return None
    query = f"{nome}, {indirizzo}, {comune}, Italy"
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

# --- 3. DATI ---
ID_DEL_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" # <--- Sostituisci con il tuo ID

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
    
    # Rilevamento Colonne Semplificato per evitare SyntaxError
    c_cliente = next((c for c in df.columns if "CLIENTE" in c), "CLIENTE")
    c_indirizzo = next((c for c in df.columns if "INDIRIZZO" in c or "VIA" in c), "INDIRIZZO")
    c_comune = next((c for c in df.columns if "COMUNE" in c), "COMUNE")
    c_cap = next((c for c in df.columns if "CAP" in c), "CAP")
    c_codice = next((c for c in df.columns if "CODICE" in c), "CODICE")
    c_tel = next((c for c in df.columns if "TELEFONO" in c), "TELEFONO")
    c_visitato = next((c for c in df.columns if "VISITATO" in c), "VISITATO")

    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1: 
            sel_comuni = st.multiselect("📍 Filtra Zona (Comuni):", sorted(df[c_comune].unique().tolist()))
        with col2: 
            tappe_max = st.slider("Numero visite:", 5, 20, 10)
        
        if st.button("🚀 GENERA GIRO OTTIMIZZATO"):
            mask = ~df[c_visitato].str.contains('SI|SÌ', case=False, na=False)
            if sel_comuni: mask &= df[c_comune].isin(sel_comuni)
            potenziali = df[mask].to_dict('records')

            if potenziali:
                with st.spinner("Pianificazione percorso..."):
                    for p in potenziali:
                        g_data = get_google_data(p[c_cliente], p[c_indirizzo], p

