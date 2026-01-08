import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium

# --- CONFIGURAZIONE FISSA ---
SEDE_INDIRIZZO = "Via G. Ferrero 122, Strada in Chianti, FI, Italy"
SEDE_COORDS = (43.6558, 11.3103)  # Strada in Chianti

# !!! SOSTITUISCI IL LINK QUI SOTTO CON IL TUO LINK DI GOOGLE SHEETS !!!
URL_SHEET = "INCOLLA_QUI_IL_TUO_LINK_DI_GOOGLE_SHEETS"

st.set_page_config(
    page_title="Giro Visite Pro", 
    page_icon="🚚", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# Funzione per geocodifica con cache (per velocizzare il Pixel)
@st.cache_data(ttl=600)
def get_coords(address):
    try:
        geolocator = Nominatim(user_agent="pixel9_pro_nav_system_v2")
        loc = geolocator.geocode(address, timeout=10)
        return (loc.latitude, loc.longitude) if loc else None
    except:
        return None

# Funzione per leggere Google Sheets via CSV
def load_data(url):
    try:
        # Trasforma il link di condivisione in link di download diretto CSV
        path = url.split("/edit")[0] + "/export?format=csv"
        return pd.read_csv(path)
    except Exception as e:
        st.error(f"Errore nel caricamento del foglio Google: {e}")
        return None

st.title("🚚 Pianificatore Visite")

# --- CARICAMENTO E PULIZIA DATI ---
raw_df = load_data(URL_SHEET)

if raw_df is not None:
    df = raw_df.copy()
    
    # 1. Pulizia Nomi Colonne (Rimuove spazi e uniforma)
    df.columns = df.columns.astype(str).str.strip()
    rename_dict = {}
    for col in df.columns:
        c_low = col.lower()
        if c_low == 'cliente': rename_dict[col] = 'Cliente'
        elif c_low == 'indirizzo': rename_dict[col] = 'Indirizzo'
        elif c_low == 'cap': rename_dict[col] = 'CAP'
        elif c_low == 'comune': rename_dict[col] = 'Comune'
        elif c_low == 'visitato': rename_dict[col] = 'Visitato'
    df = df.rename(columns=rename_dict)

    # 2. Controllo colonne obbligatorie
    cols_check = ['Cliente', 'Indirizzo', 'CAP', 'Comune']
    mancanti = [c for c in cols_check if c not in df.columns]
    
    if mancanti:
        st.error(f"❌ Colonne mancanti nel foglio: {', '.join(mancanti)}")
        st.info("Assicurati che la prima riga del foglio contenga esattamente: Cliente, Indirizzo, CAP, Comune, Visitato")
        st.stop()

    # 3. Pulizia Contenuti
    df['CAP'] = df['CAP'].astype(str).str.replace('.0', '', regex=False).str.strip()
    df['Comune'] = df['Com
