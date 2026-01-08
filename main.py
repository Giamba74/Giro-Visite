import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium

# --- CONFIGURAZIONE FISSA ---
SEDE_INDIRIZZO = "Via G. Ferrero 122, Strada in Chianti, FI, Italy"
SEDE_COORDS = (43.6558, 11.3103)

# SOSTITUISCI IL LINK QUI SOTTO
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

st.set_page_config(
    page_title="Giro Visite Pro", 
    page_icon="🚚", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

@st.cache_data(ttl=600)
def get_coords(address):
    try:
        geolocator = Nominatim(user_agent="pixel9_pro_chianti_final_v3")
        loc = geolocator.geocode(address, timeout=10)
        return (loc.latitude, loc.longitude) if loc else None
    except:
        return None

def load_data(url):
    try:
        path = url.split("/edit")[0] + "/export?format=csv"
        return pd.read_csv(path)
    except Exception as e:
        st.error(f"Errore caricamento: {e}")
        return None

st.title("🚚 Pianificatore Visite")

raw_df = load_data(URL_SHEET)

if raw_df is not None:
    df = raw_df.copy()
    df.columns = df.columns.astype(str).str.strip()
    
    # Uniformiamo i nomi delle colonne
    rename_dict = {}
    for col in df.columns:
        c_low = col.lower()
        if c_low == 'cliente': rename_dict[col] = 'Cliente'
        elif c_low == 'indirizzo': rename_dict[col] = 'Indirizzo'
        elif c_low == 'cap': rename_dict[col] = 'CAP'
        elif c_low == 'comune': rename_dict[col] = 'Comune'
        elif c_low == 'visitato': rename_dict[col] = 'Visitato'
    df = df.rename(columns=rename_dict)

    # Pulizia dati
    if 'CAP' in df.columns:
        df['CAP'] = df['CAP'].astype(str).str.replace('.0', '', regex=False).str.strip()
    if 'Comune' in df.columns:
        df['Comune'] = df['Comune'].astype(str).str.upper().str.strip()
    if 'Visitato' not in df.columns:
        df['Visitato'] = 'No'

    st.success(f"✅ Sincronizzato: {len(df)} clienti")

    # Filtri
    st.subheader("Filtra Zona")
    c1, c2 = st.columns(2)
    with c1:
        comuni_lista = sorted(df['Comune'].unique()) if 'Comune' in df.columns else []
        sel_comuni = st.multiselect("📍 Comuni:", comuni_lista)
    with c2:
        caps_lista = sorted(df['CAP'].unique()) if 'CAP' in df.columns else []
        sel_caps = st.multiselect("📮 CAP:", caps_lista)

    # Logica Filtro
    mask_visitato = df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI'])
    mask = ~mask_visitato
    if sel_comuni: mask &= (df['Comune'].isin(sel_comuni))
    if sel_caps: mask &= (df['CAP'].isin(sel_caps))

    da_visitare = df[mask].copy()

    if st.button("🚀 GENERA GIRO (MAX 10 TAPPE)", use_container_width=True):
        if da_visitare.empty:
            st.warning("Nessun cliente trovato.")
        else:
            with st.spinner('Calcolo...'):
                da_visitare['coords'] = da_visitare['Indirizzo'].apply(get_coords)
                da_visitare = da_visitare.dropna(subset=['coords'])
                
                clienti_list = da_visitare.to_dict('records')
                percorso = []
                pos_attuale = SEDE_COORDS
                
                while len(percorso) < 10 and clienti_list:
                    prossimo = min(clienti_list, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                    percorso.append(prossimo)
                    pos_attuale = prossimo['coords']
                    clienti_list.remove(prossimo)
                st.session_state.giro = percorso

    if 'giro' in st.session_state and st.session_state.giro:
        giro = st.session_state.giro
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        for i, p in enumerate(giro):
            folium.Marker(p['coords'], popup=p['Cliente']).add_to(m)
        st_folium(m, width="100%", height=300)

        for i, p in enumerate(giro):
            with st.expander(f"🚩 {i+1}: {p['Cliente']}", expanded=True):
                st.write(f"🏠 {p['Indirizzo']} - {p['Comune']}")
                query = f"{p['Indirizzo']}, {p['Comune']}, Italy".replace(' ', '+')
                url = f"https://www.google.com/maps/dir/?api=1&destination={query}&travelmode=driving"
                st.link_button("🧭 NAVIGA", url, use_container_width=True)
else:
    st.info("Incolla il link del foglio Google nel codice.")


