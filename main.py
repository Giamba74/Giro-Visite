import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time

# --- CONFIGURAZIONE ---
SEDE_COORDS = (43.661888, 11.305728) # Strada in Chianti
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

st.set_page_config(page_title="Giro Visite Pro", page_icon="🚚", layout="wide")

@st.cache_data(ttl=3600)
def get_coords_v3(via_civico, comune):
    geolocator = Nominatim(user_agent="pixel9_pro_final_v6")
    # Puliamo l'indirizzo da eventuali virgole residue o spazi doppi
    indirizzo_pulito = str(via_civico).replace(",", " ").strip()
    comune_pulito = str(comune).strip()
    
    # Tentativo 1: Indirizzo completo (Via Civico, Comune, Italia)
    query1 = f"{indirizzo_pulito}, {comune_pulito}, Italy"
    try:
        loc = geolocator.geocode(query1, timeout=10)
        if loc: return (loc.latitude, loc.longitude)
        
        # Tentativo 2: Solo Via e Comune (senza civico, se il civico è il problema)
        via_solo = " ".join(indirizzo_pulito.split()[:-1])
        query2 = f"{via_solo}, {comune_pulito}, Italy"
        loc = geolocator.geocode(query2, timeout=10)
        if loc: return (loc.latitude, loc.longitude)

        # Tentativo 3: Solo Comune (Punto di appoggio)
        query3 = f"{comune_pulito}, Italy"
        loc = geolocator.geocode(query3, timeout=10)
        if loc: return (loc.latitude, loc.longitude)
    except:
        return None
    return None

def load_data(url):
    try:
        path = url.split("/edit")[0] + "/export?format=csv"
        return pd.read_csv(path)
    except Exception as e:
        st.error(f"Errore caricamento Google Sheets: {e}")
        return None

st.title("🚚 Pianificatore Visite")

raw_df = load_data(URL_SHEET)

if raw_df is not None:
    df = raw_df.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    # Mappatura Colonne
    mappa = {}
    for col in df.columns:
        if "CLIENTE" in col: mappa[col] = "Cliente"
        elif "INDIRIZZO" in col: mappa[col] = "Indirizzo"
        elif "CAP" in col: mappa[col] = "CAP"
        elif "COMUNE" in col: mappa[col] = "Comune"
        elif "VISITATO" in col: mappa[col] = "Visitato"
    df = df.rename(columns=mappa)

    # Pulizia Base
    df["Comune"] = df["Comune"].fillna("").astype(str)
    df["Indirizzo"] = df["Indirizzo"].fillna("").astype(str)
    if "Visitato" not in df.columns: df["Visitato"] = "No"

    st.success(f"✅ Database pronto ({len(df)} clienti)")

    # Filtri
    sel_comuni = st.multiselect("📍 Seleziona Comuni:", sorted(df['Comune'].unique().tolist()))

    mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
    if sel_comuni: mask &= (df['Comune'].isin(sel_comuni))
    
    da_visitare = df[mask].copy()

    if st.button("🚀 GENERA GIRO OTTIMIZZATO", use_container_width=True):
        if da_visitare.empty:
            st.warning("Nessun cliente da visitare trovato.")
        else:
            clienti_validi = []
            with st.status("Ricerca posizioni...", expanded=True) as status:
                for row in da_visitare.to_dict('records'):
                    st.write(f"🌍 Cerco: {row['Cliente']}...")
                    coords = get_coords_v3(row['Indirizzo'], row['Comune'])
                    if coords:
                        row['coords'] = coords
                        clienti_validi.append(row)
                    time.sleep(1.2) # Indispensabile per non essere bloccati dal server

                if clienti_validi:
                    # Algoritmo Prossimità
                    percorso = []
                    pos_attuale = SEDE_COORDS
                    while len(percorso) < 10 and clienti_validi:
                        prossimo = min(clienti_validi, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                        percorso.append(prossimo)
                        pos_attuale = prossimo['coords']
                        clienti_validi.remove(prossimo)
                    
                    st.session_state.giro = percorso
                    status.update(label="Giro generato!", state="complete")
                else:
                    status.update(label="Errore: Nessun indirizzo trovato!", state="error")

    if 'giro' in st.session_state and st.session_state.giro:
        giro = st.session_state.giro
        
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        for i, p in enumerate(giro):
            folium.Marker(p['coords'], popup=p['Cliente']).add_to(m)
        st_folium(m, width="100%", height=350)

        for i, p in enumerate(giro):
            with st.expander(f"🚩 TAPPA {i+1}: {p['Cliente']}", expanded=True):
                st.write(f"🏠 {p['Indirizzo']} ({p['Comune']})")
                # Link Navigazione
                dest = f"{p['Indirizzo']} {p['Comune']} Italy".replace(' ', '+')
                st.link_button("🧭 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={dest}&travelmode=driving", use_container_width=True)
