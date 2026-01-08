import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time

# --- CONFIGURAZIONE ---
SEDE_INDIRIZZO = "Via G. Ferrero 122, Strada in Chianti, FI, Italy"
SEDE_COORDS = (43.6558, 11.3103)
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

st.set_page_config(page_title="Giro Visite Pro", page_icon="🚚", layout="wide")

@st.cache_data(ttl=600)
def get_coords(address, comune):
    try:
        full_address = f"{address}, {comune}, Italy"
        geolocator = Nominatim(user_agent="pixel9_pro_final_v4")
        loc = geolocator.geocode(full_address, timeout=10)
        return (loc.latitude, loc.longitude) if loc else None
    except:
        return None

def load_data(url):
    try:
        path = url.split("/edit")[0] + "/export?format=csv"
        df = pd.read_csv(path)
        # Rimuove eventuali colonne completamente vuote o righe vuote
        df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
        return df
    except Exception as e:
        st.error(f"Errore caricamento: {e}")
        return None

st.title("🚚 Pianificatore Visite")

raw_df = load_data(URL_SHEET)

if raw_df is not None:
    # --- SISTEMA DI MAPPATURA COLONNE INTELLIGENTE ---
    df = raw_df.copy()
    
    # Pulizia nomi colonne (rimozione spazi e caratteri invisibili)
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    # Mappatura flessibile
    mappa = {}
    for col in df.columns:
        if "CLIENTE" in col: mappa[col] = "Cliente"
        elif "INDIRIZZO" in col: mappa[col] = "Indirizzo"
        elif "CAP" in col: mappa[col] = "CAP"
        elif "COMUNE" in col: mappa[col] = "Comune"
        elif "VISITATO" in col: mappa[col] = "Visitato"
    
    df = df.rename(columns=mappa)
    
    # Verifica colonne fondamentali
    fondamentali = ["Cliente", "Indirizzo", "CAP", "Comune"]
    mancanti = [c for c in fondamentali if c not in df.columns]
    
    if mancanti:
        st.error(f"❌ Non trovo le colonne: {mancanti}")
        st.write("Colonne trovate nel tuo file:", list(df.columns))
        st.stop()

    # Pulizia dati per evitare altri KeyError
    if "Visitato" not in df.columns: df["Visitato"] = "No"
    df["CAP"] = df["CAP"].astype(str).str.replace('.0', '', regex=False).str.strip()
    df["Comune"] = df["Comune"].astype(str).str.upper().str.strip()
    df["Indirizzo"] = df["Indirizzo"].astype(str).str.strip()

    st.success(f"✅ Database pronto: {len(df)} clienti")

    # --- FILTRI ---
    c1, c2 = st.columns(2)
    with c1:
        sel_comuni = st.multiselect("📍 Comuni:", sorted(df['Comune'].unique()))
    with c2:
        sel_caps = st.multiselect("📮 CAP:", sorted(df['CAP'].unique()))

    # Filtro Visite
    mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
    if sel_comuni: mask &= (df['Comune'].isin(sel_comuni))
    if sel_caps: mask &= (df['CAP'].isin(sel_caps))
    
    da_visitare = df[mask].copy()

    if st.button("🚀 GENERA GIRO", use_container_width=True):
        if da_visitare.empty:
            st.warning("Nessun cliente trovato.")
        else:
            percorso = []
            lista_clienti = da_visitare.to_dict('records')
            
            with st.status("Ricerca indirizzi...", expanded=True) as status:
                clienti_validi = []
                for p in lista_clienti:
                    st.write(f"Verifica: {p['Cliente']}...")
                    c = get_coords(p['Indirizzo'], p['Comune'])
                    if c:
                        p['coords'] = c
                        clienti_validi.append(p)
                    time.sleep(1) # Rispetto del server Nominatim
                
                if not clienti_validi:
                    status.update(label="Nessun indirizzo trovato sulla mappa!", state="error")
                else:
                    # Algoritmo TSP Semplice
                    pos_attuale = SEDE_COORDS
                    while len(percorso) < 10 and clienti_validi:
                        prossimo = min(clienti_validi, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                        percorso.append(prossimo)
                        pos_attuale = prossimo['coords']
                        clienti_validi.remove(prossimo)
                    
                    st.session_state.giro = percorso
                    status.update(label="Giro generato!", state="complete")

    # --- OUTPUT ---
    if 'giro' in st.session_state and st.session_state.giro:
        giro = st.session_state.giro
        
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        for i, p in enumerate(giro):
            folium.Marker(p['coords'], popup=p['Cliente']).add_to(m)
        st_folium(m, width="100%", height=300)

        for i, p in enumerate(giro):
            with st.expander(f"🚩 {i+1}: {p['Cliente']}", expanded=True):
                st.write(f"🏠 {p['Indirizzo']} - {p['Comune']}")
                q = f"{p['Indirizzo']}, {p['Comune']}, Italy".replace(' ', '+')
                st.link_button("🧭 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={q}&travelmode=driving", use_container_width=True)




