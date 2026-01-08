import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
from shworksheet import connect 

# --- CONFIGURAZIONE FISSA ---
SEDE_INDIRIZZO = "Via G. Ferrero 122, Strada in Chianti, FI, Italy"
SEDE_NOME = "UFFICIO"
URL_SHEET = "INCOLLA_QUI_IL_TUO_LINK_DI_GOOGLE_SHEETS"

st.set_page_config(page_title="Giro Visite Smart", layout="wide", initial_sidebar_state="collapsed")

@st.cache_data(ttl=600)
def get_coords(address):
    try:
        geolocator = Nominatim(user_agent="pixel9_pro_chianti_nav")
        loc = geolocator.geocode(address, timeout=10)
        return (loc.latitude, loc.longitude) if loc else None
    except: return None

st.title("🚚 Pianificatore per Comune e CAP")

# Connessione al Cloud
try:
    conn = connect(URL_SHEET)
    df = conn.read()
    # Pulizia dati per evitare errori di formattazione
    df['CAP'] = df['CAP'].astype(str).str.replace('.0', '', regex=False)
    df['Comune'] = df['Comune'].astype(str).str.upper().str.strip()
    st.success(f"✅ Database sincronizzato ({len(df)} clienti)")
except Exception as e:
    st.error(f"❌ Errore connessione: {e}")
    st.stop()

# --- FILTRI ---
st.subheader("Filtra la zona di oggi")
col_f1, col_f2 = st.columns(2)

with col_f1:
    lista_comuni = sorted(df['Comune'].unique())
    comuni_sel = st.multiselect("📍 Seleziona Comuni:", lista_comuni)

with col_f2:
    lista_cap = sorted(df['CAP'].unique())
    cap_sel = st.multiselect("📮 Seleziona CAP:", lista_cap)

# Logica di filtraggio
mask = (df['Visitato'] != 'Sì')
if comuni_sel:
    mask &= (df['Comune'].isin(comuni_sel))
if cap_sel:
    mask &= (df['CAP'].isin(cap_sel))

da_visitare = df[mask].copy()

if st.button("🚀 GENERA GIRO OTTIMIZZATO (MAX 10)"):
    if da_visitare.empty:
        st.warning("⚠️ Nessun cliente trovato con questi filtri che non sia già stato visitato.")
    else:
        with st.status("Calcolo percorso ottimale...", expanded=True) as status:
            sede_coords = (43.6558, 11.3103)
            
            # Geocodifica dinamica
            da_visitare['coords'] = da_visitare['Indirizzo'].apply(get_coords)
            da_visitare = da_visitare.dropna(subset=['coords'])
            
            # Algoritmo di prossimità
            clienti_lista = da_visitare.to_dict('records')
            percorso = []
            pos_attuale = sede_coords
            
            # Se abbiamo più di 10 clienti, prendiamo i 10 più vicini alla sede/tappa precedente
            while len(percorso) < 10 and clienti_lista:
                prossimo = min(clienti_lista, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                percorso.append(prossimo)
                pos_attuale = prossimo['coords']
                clienti_lista.remove(prossimo)
            
            st.session_state.giro = percorso
            status.update(label="Percorso pronto!", state="complete")

# --- VISUALIZZAZIONE E NAVIGAZIONE ---
if 'giro' in st.session_state:
    percorso = st.session_state.giro
    
    # Mappa interattiva
    m = folium.Map(location=sede_coords, zoom_start=12)
    punti_mappa = [sede_coords] + [p['coords'] for p in percorso] + [sede_coords]
    folium.PolyLine(punti_mappa, color="#3498db", weight=5, opacity=0.8).add_to(m)
    
    for i, p in enumerate(percorso):
        folium.Marker(p['coords'], popup=f"{i+1}. {p['Cliente']}", icon=folium.Icon(color='blue')).add_to(m)
    
    st_folium(m, width="100%", height=350)

    st.subheader("Lista Tappe (Sincronizzata)")
    for i, p in enumerate(percorso):
        with st.expander(f"🚩 {i+1}: {p['Cliente']} ({p['Comune']})", expanded=True):
            c1, c2 = st.columns([2, 1])
            c1.write(f"🏠 {p['Indirizzo']}")
            
            # Tasto FATTO: scrive su Google Sheets
            if c2.button("✅ FATTO", key=f"check_{i}"):
                conn.update_cell(p['Cliente'], 'Visitato', 'Sì', col_chiave='Cliente')
                st.toast(f"Aggiornato: {p['Cliente']} segnato come visitato.")
                # Rimuoviamo dalla sessione temporanea per aggiornare la lista
                st.session_state.giro.pop(i)
                st.rerun()
            
            # Tasto NAVIGA: apre Google Maps
            maps_url = f"https://www.google.com/maps/dir/?api=1&destination={p['coords'][0]},{p['coords'][1]}&travelmode=driving"
            st.link_button("🧭 NAVIGATORE", maps_url, use_container_width=True)
