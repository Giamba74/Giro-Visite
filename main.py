import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium

# --- CONFIGURAZIONE ---
SEDE_INDIRIZZO = "Via G. Ferrero 122, Strada in Chianti, FI, Italy"
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

st.set_page_config(page_title="Giro Visite Pro", page_icon="🚚", layout="wide")

@st.cache_data(ttl=300)
def get_coords(address):
    try:
        geolocator = Nominatim(user_agent="pixel9_pro_nav_system")
        loc = geolocator.geocode(address, timeout=10)
        return (loc.latitude, loc.longitude) if loc else None
    except: return None

def load_data(url):
    # Trasforma il link di condivisione in link di download diretto CSV
    path = url.split("/edit")[0] + "/export?format=csv"
    return pd.read_csv(path)

st.title("🚚 Pianificatore Visite")

# Caricamento dati
try:
    df = load_data(URL_SHEET)
    # Pulizia nomi colonne e dati
    df.columns = df.columns.str.strip()
    df['CAP'] = df['CAP'].astype(str).str.replace('.0', '', regex=False).str.strip()
    df['Comune'] = df['Comune'].astype(str).str.upper().str.strip()
    st.success(f"✅ Database Sincronizzato ({len(df)} clienti)")
except Exception as e:
    st.error(f"Configura il link Google Sheets nel codice. Errore: {e}")
    st.stop()

# --- INTERFACCIA FILTRI ---
col1, col2 = st.columns(2)
with col1:
    comuni = sorted(df['Comune'].unique())
    sel_comuni = st.multiselect("📍 Comuni:", comuni)
with col2:
    caps = sorted(df['CAP'].unique())
    sel_caps = st.multiselect("📮 CAP:", caps)

mask = (df['Visitato'].get('Visitato', 'No') != 'Sì') # Gestisce se la colonna manca
if sel_comuni: mask &= (df['Comune'].isin(sel_comuni))
if sel_caps: mask &= (df['CAP'].isin(sel_caps))

da_visitare = df[mask].copy()

if st.button("🚀 GENERA GIRO (10 Tappe)", use_container_width=True):
    if da_visitare.empty:
        st.warning("Nessun cliente trovato.")
    else:
        with st.spinner('Calcolo percorso...'):
            sede_coords = (43.6558, 11.3103)
            da_visitare['coords'] = da_visitare['Indirizzo'].apply(get_coords)
            da_visitare = da_visitare.dropna(subset=['coords'])
            
            clienti = da_visitare.to_dict('records')
            percorso = []
            pos = sede_coords
            while len(percorso) < 10 and clienti:
                p = min(clienti, key=lambda x: geodesic(pos, x['coords']).km)
                percorso.append(p)
                pos = p['coords']
                clienti.remove(p)
            st.session_state.giro = percorso

# --- MAPPA E NAVIGAZIONE ---
if 'giro' in st.session_state:
    percorso = st.session_state.giro
    
    # Mappa
    m = folium.Map(location=[43.6558, 11.3103], zoom_start=11)
    for i, p in enumerate(percorso):
        folium.Marker(p['coords'], popup=p['Cliente']).add_to(m)
    st_folium(m, width="100%", height=300)

    st.info("⚠️ Segna le visite fatte direttamente sul tuo Google Sheets per aggiornare l'elenco.")

    for i, p in enumerate(percorso):
        with st.expander(f"🚩 {i+1}: {p['Cliente']}", expanded=True):
            st.write(f"🏠 {p['Indirizzo']} - {p['Comune']}")
            addr_query = f"{p['Indirizzo']}, {p['Comune']}, Italy".replace(' ', '+')
            url = f"https://www.google.com/maps/dir/?api=1&destination={addr_query}&travelmode=driving"
            st.link_button("🧭 AVVIA NAVIGATORE", url, use_container_width=True)

