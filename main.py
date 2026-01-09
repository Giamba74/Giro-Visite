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
    .header-box { background-color: #00122e; padding: 20px; border-radius: 15px; border: 2px solid #FFD700; margin-bottom: 20px; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 8px; color: white; }
    .badge-open { background-color: #28a745; color: white; padding: 3px 10px; border-radius: 10px; font-size: 0.8em; font-weight: bold; }
    .badge-closed { background-color: #ff4b4b; color: white; padding: 3px 10px; border-radius: 10px; font-size: 0.8em; font-weight: bold; }
    .error-box { background-color: #ae0000; color: white; padding: 10px; border-radius: 5px; margin-bottom: 10px; }
</style>""", unsafe_allow_html=True)

# --- 2. FUNZIONI GOOGLE LIVE ---
def get_google_live_data(nome, indirizzo, comune):
    """Cerca il cliente su Google Maps. Se fallisce col nome, prova con l'indirizzo."""
    queries = [f"{nome} {comune} Italy", f"{indirizzo} {comune} Italy"]
    
    for q in queries:
        try:
            search_url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={urllib.parse.quote(q)}&key={API_KEY}"
            res = requests.get(search_url).json()
            if res.get('results'):
                p_id = res['results'][0]['place_id']
                det_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={p_id}&fields=opening_hours,formatted_phone_number,geometry&key={API_KEY}"
                det = requests.get(det_url).json().get('result', {})
                return {
                    "coords": (det['geometry']['location']['lat'], det['geometry']['location']['lng']),
                    "periods": det.get('opening_hours', {}).get('periods', []),
                    "tel": det.get('formatted_phone_number', '')
                }
        except: continue
    return None

def is_open_check(ora_str, periods):
    if not periods: return True
    # Google: 0=Dom, 1=Lun... | Python: 0=Lun, 6=Dom
    giorno_goog = (datetime.now().weekday() + 1) % 7
    ora_int = int(ora_str.replace(":", ""))
    for p in periods:
        if p['open']['day'] == giorno_goog:
            apre = int(p['open']['time'])
            chiude = int(p['close']['time'])
            if apre <= ora_int <= chiude: return True
    return False

# --- 3. LOGICA PRINCIPALE ---
st.title("⭐ BRIGHTSTAR GOOGLE AI - FULL FILTERS")

# --- INSERISCI L'ID DEL TUO FOGLIO QUI ---
ID_FOGLIO = "1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0" 

@st.cache_resource
def init_gs():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], 
                                                    scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Errore inizializzazione Google Sheets: {e}")
        return None

gc = init_gs()
if gc:
    try:
        ws = gc.open_by_key(ID_FOGLIO).get_worksheet(0)
        data = ws.get_all_values()
        df = pd.DataFrame(data[1:], columns=[h.upper() for h in data[0]])
        
        # Pulizia CAP
        if 'CAP' in df.columns:
            df['CAP'] = df['CAP'].astype(str).str.replace('.0', '', regex=False).str.strip
