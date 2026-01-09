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

# Stile CSS per un look professionale sul tuo Pixel 9 Pro
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

# --- 2. RECUPERO CHIAVI E CONNESSIONI ---
API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY")

@st.cache_resource(show_spinner="Connessione al database...")
def init_gsheet(sheet_id):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(sheet_id).get_worksheet(0)
    except Exception as e:
        st.error(f"Errore connessione Google Sheets: {e}")
        return None

def get_google_live_data(nome, indirizzo, comune):
    """Interroga le API di Google Maps per orari e coordinate reali"""
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
    """Verifica apertura
