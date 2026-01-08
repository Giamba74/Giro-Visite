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
        # Uniamo indirizzo e comune per maggiore precisione
        full_address = f"{address}, {comune}, Italy"
        geolocator = Nominatim(user_agent="pixel9_pro_final_tester")
        # Aumentato il timeout a 10 secondi per evitare blocchi
        loc = geolocator.geocode(full_address, timeout=10)
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
    
    # Uniformiamo nomi colonne
    rename_dict = {col: col.capitalize() for col in df.columns if col.lower() in ['cliente', 'indirizzo', 'cap', 'comune', 'visitato']}
    df = df.rename(columns=rename_dict)

    if 'Visitato' not in df.columns: df['Visitato'] = 'No'
    df['Comune'] = df['Comune'].astype(str).str.upper().str.strip()
    df['CAP'] = df['CAP'].astype(str).str.replace('.0', '', regex=False).str.strip()

    st.success(f"✅ Database pronto: {len(df)} clienti")

    # --- FILTRI ---
    c1, c2 = st.columns(2)
    with c1:
        sel_comuni = st.multiselect("📍 Comuni:", sorted(df['Comune'].unique()))
    with c2:
        sel_caps = st.multiselect("📮 CAP:", sorted(df['CAP'].unique()))

    # Logica filtro
    mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI'])
    if sel_comuni: mask &= (df['Comune'].isin(sel_comuni))
    if sel_caps: mask &= (df['CAP'].isin(sel_caps))
    
    da_visitare = df[mask].copy()

    if st.button("🚀 GENERA GIRO", use_container_width=True):
        if da_visitare.empty:
            st.warning("Nessun cliente trovato con questi filtri.")
        else:
            percorso = []
            lista_clienti = da_visitare.to_dict('records')
            
            with st.status("Ricerca posizioni sulla mappa...", expanded=True) as status:
                clienti_con_coords = []
                for p in lista_clienti:
                    st.write(f"Cerco: {p['Cliente']} ({p['Indirizzo']})...")
                    coords = get_coords(p['Indirizzo'], p['Comune'])
                    if coords:
                        p['coords'] = coords
                        clienti_con_coords.append(p)
                        st.write(f"✅ Trovato!")
                    else:
                        st.write(f"❌ Non trovato. Controlla l'indirizzo!")
                    time.sleep(1) # Rispetta i limiti del servizio gratuito
                
                if not clienti_con_coords:
                    status.update(label="Errore: Nessun indirizzo trovato!", state="error")
                else:
                    status.update(label="Ottimizzazione percorso...", state="running")
                    # Algoritmo calcolo
                    pos_attuale = SEDE_COORDS
                    while len(percorso) < 10 and clienti_con_coords:
                        prossimo = min(clienti_con_coords, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                        percorso.append(prossimo)
                        pos_attuale = prossimo['coords']
                        clienti_con_coords.remove(prossimo)
                    
                    st.session_state.giro = percorso
                    status.update(label="Giro generato!", state="complete")

    # --- VISUALIZZAZIONE ---
    if 'giro' in st.session_state and st.session_state.giro:
        giro = st.session_state.giro
        st.subheader(f"Giro Ottimizzato: {len(giro)} tappe")
        
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        for i, p in enumerate(giro):
            folium.Marker(p['coords'], popup=p['Cliente']).add_to(m)
        st_folium(m, width="100%", height=300)

        for i, p in enumerate(giro):
            with st.expander(f"🚩 {i+1}: {p['Cliente']}", expanded=True):
                col_a, col_b = st.columns([2,1])
                col_a.write(f"{p['Indirizzo']} - {p['Comune']}")
                q = f"{p['Indirizzo']}, {p['Comune']}, Italy".replace(' ', '+')
                col_b.link_button("🧭 NAVIGA", f"https://www.google.com/maps/dir/?api=1&destination={q}&travelmode=driving")




