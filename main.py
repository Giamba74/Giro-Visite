import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
from shworksheet import connect 

# --- CONFIGURAZIONE ---
SEDE_INDIRIZZO = "Via G. Ferrero 122, Strada in Chianti, FI, Italy"
SEDE_NOME = "UFFICIO"
# ASSICURATI DI INCOLLARE IL TUO LINK QUI SOTTO
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

st.set_page_config(page_title="Giro Visite Pro", layout="wide")

@st.cache_data(ttl=300) # Cache di 5 minuti per non rallentare il telefono
def get_coords(address):
    try:
        geolocator = Nominatim(user_agent="pixel9_pro_chianti_final")
        loc = geolocator.geocode(address, timeout=10)
        return (loc.latitude, loc.longitude) if loc else None
    except: return None

st.title("🚚 Pianificatore Visite Ottimizzato")

# Connessione al Cloud
try:
    conn = connect(URL_SHEET)
    df = conn.read()
    # Pulizia automatica dei dati
    df['CAP'] = df['CAP'].astype(str).str.replace('.0', '', regex=False).str.strip()
    df['Comune'] = df['Comune'].astype(str).str.upper().str.strip()
    df['Indirizzo'] = df['Indirizzo'].astype(str).str.strip()
    st.success(f"✅ Database pronto: {len(df)} clienti in memoria")
except Exception as e:
    st.error(f"❌ Errore: Controlla il link del foglio o le intestazioni delle colonne. {e}")
    st.stop()

# --- FILTRI ---
st.subheader("Seleziona la zona di oggi")
col1, col2 = st.columns(2)
with col1:
    lista_comuni = sorted(df['Comune'].unique())
    comuni_sel = st.multiselect("📍 Comune:", lista_comuni)
with col2:
    lista_cap = sorted(df['CAP'].unique())
    cap_sel = st.multiselect("📮 CAP:", lista_cap)

# Logica di filtraggio
mask = (df['Visitato'] != 'Sì')
if comuni_sel:
    mask &= (df['Comune'].isin(comuni_sel))
if cap_sel:
    mask &= (df['CAP'].isin(cap_sel))

da_visitare = df[mask].copy()

if st.button("🚀 GENERA GIRO (MAX 10)"):
    if da_visitare.empty:
        st.warning("⚠️ Nessun cliente disponibile per questi filtri.")
    else:
        with st.status("Calcolo percorso ottimale...", expanded=True) as status:
            sede_coords = (43.6558, 11.3103)
            
            # Geocodifica sulla colonna "Indirizzo" che hai creato
            da_visitare['coords'] = da_visitare['Indirizzo'].apply(get_coords)
            da_visitare = da_visitare.dropna(subset=['coords'])
            
            # Algoritmo di prossimità
            clienti_lista = da_visitare.to_dict('records')
            percorso = []
            pos_attuale = sede_coords
            
            while len(percorso) < 10 and clienti_lista:
                prossimo = min(clienti_lista, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                percorso.append(prossimo)
                pos_attuale = prossimo['coords']
                clienti_lista.remove(prossimo)
            
            st.session_state.giro = percorso
            status.update(label="Giro calcolato con successo!", state="complete")

# --- LISTA E NAVIGAZIONE ---
if 'giro' in st.session_state:
    percorso = st.session_state.giro
    
    # Mappa piccola per risparmiare spazio su mobile
    m = folium.Map(location=[43.6558, 11.3103], zoom_start=11)
    for i, p in enumerate(percorso):
        folium.Marker(p['coords'], popup=p['Cliente']).add_to(m)
    st_folium(m, width="100%", height=300)

    for i, p in enumerate(percorso):
        with st.expander(f"🚩 {i+1}: {p['Cliente']}", expanded=True):
            c1, c2 = st.columns([2, 1])
            c1.write(f"{p['Indirizzo']}\n({p['Comune']})")
            
            # Bottone Fatto
            if c2.button("✅ FATTO", key=f"ok_{i}"):
                conn.update_cell(p['Cliente'], 'Visitato', 'Sì', col_chiave='Cliente')
                st.toast(f"Aggiornato!")
                st.session_state.giro.pop(i)
                st.rerun()
            
            # Bottone Navigatore (ottimizzato per Google Maps App)
            # Inseriamo anche il Comune per essere più precisi
            addr_query = f"{p['Indirizzo']}, {p['Comune']}, Italy"
            maps_url = f"https://www.google.com/maps/dir/?api=1&destination={addr_query.replace(' ', '+')}&travelmode=driving"
            st.link_button("🧭 NAVIGA", maps_url, use_container_width=True)

