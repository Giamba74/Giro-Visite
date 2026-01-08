import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time

# --- CONFIGURAZIONE CASA / PARTENZA ---
SEDE_NOME = "CASA (Strada in Chianti)"
SEDE_COORDS = (43.661888, 11.305728) 
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

st.set_page_config(page_title="Giro Visite Pro", page_icon="🚚", layout="wide")

@st.cache_data(ttl=3600)
def get_coords_smart(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="pixel9_pro_final_v9")
    # Pulizia dati
    ind = str(indirizzo).strip()
    com = str(comune).strip()
    cp = str(cap).replace(".0", "").strip()
    
    # Query super precisa: Via, CAP, Comune
    queries = [
        f"{ind}, {cp}, {com}, Italy",
        f"{ind}, {com}, Italy",
        f"{com}, Italy"
    ]
    
    for q in queries:
        try:
            loc = geolocator.geocode(q, timeout=7)
            if loc: return (loc.latitude, loc.longitude)
        except: continue
    return None

def load_data(url):
    try:
        if "/edit" in url:
            url = url.split("/edit")[0] + "/export?format=csv"
        df = pd.read_csv(url)
        # Pulizia nomi colonne
        df.columns = [str(c).strip().upper() for c in df.columns]
        mappa = {}
        for c in df.columns:
            if "CLIENTE" in c: mappa[c] = "Cliente"
            elif "INDIRIZZO" in c: mappa[c] = "Indirizzo"
            elif "COMUNE" in c: mappa[c] = "Comune"
            elif "CAP" in c: mappa[c] = "CAP"
            elif "VISITATO" in c: mappa[c] = "Visitato"
        return df.rename(columns=mappa)
    except: return None

st.title("🚚 Giro Visite Ottimizzato")

df = load_data(URL_SHEET)

if df is not None:
    # Pulizia dati colonne
    for col in ['Cliente', 'Indirizzo', 'Comune', 'CAP']:
        if col in df.columns: df[col] = df[col].fillna("").astype(str)
    if 'Visitato' not in df.columns: df['Visitato'] = 'No'

    # --- FILTRI ---
    st.subheader("Seleziona Zona")
    c1, c2 = st.columns(2)
    with c1:
        comuni = sorted(df['Comune'].unique().tolist())
        sel_comune = st.selectbox("📍 Comune:", ["Tutti"] + comuni)
    with c2:
        caps = sorted(df['CAP'].unique().tolist())
        sel_cap = st.selectbox("📮 CAP:", ["Tutti"] + caps)

    # Applichiamo filtri
    mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
    if sel_comune != "Tutti": mask &= (df['Comune'] == sel_comune)
    if sel_cap != "Tutti": mask &= (df['CAP'] == sel_cap)
    
    da_visitare = df[mask].copy()

    if st.button("🚀 GENERA GIRO 10 TAPPE (DA CASA)", use_container_width=True):
        clienti_localizzati = []
        with st.status("Localizzazione e Ottimizzazione...", expanded=True) as status:
            # Prendiamo un campione più ampio per estrarre i 10 migliori
            campione = da_visitare.head(20).to_dict('records')
            
            for row in campione:
                st.write(f"🌍 Analizzo: {row['Cliente']} ({row['CAP']})...")
                coords = get_coords_smart(row['Indirizzo'], row['Comune'], row['CAP'])
                if coords:
                    row['coords'] = coords
                    clienti_localizzati.append(row)
                    st.write("✅ OK")
                time.sleep(1)

            if clienti_localizzati:
                # --- ALGORITMO GIRO OTTIMIZZATO ---
                giro_ottimizzato = []
                posizione_attuale = SEDE_COORDS
                
                while len(giro_ottimizzato) < 10 and clienti_localizzati:
                    # Trova il più vicino alla posizione attuale
                    prossimo = min(clienti_localizzati, key=lambda x: geodesic(posizione_attuale, x['coords']).km)
                    giro_ottimizzato.append(prossimo)
                    posizione_attuale = prossimo['coords']
                    clienti_localizzati.remove(prossimo)
                
                st.session_state.giro = giro_ottimizzato
                status.update(label="Giro Ottimizzato Generato!", state="complete")
            else:
                status.update(label="Nessun indirizzo trovato!", state="error")

    # --- VISUALIZZAZIONE RISULTATI ---
    if 'giro' in st.session_state:
        giro = st.session_state.giro
        
        # Mappa con linea del percorso
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        
        # Aggiungiamo CASA
        folium.Marker(SEDE_COORDS, popup=SEDE_NOME, icon=folium.Icon(color='green', icon='home')).add_to(m)
        
        # Punti del percorso per la linea blu
        punti_percorso = [SEDE_COORDS]
        for p in giro:
            punti_percorso.append(p['coords'])
            folium.Marker(p['coords'], popup=p['Cliente'], icon=folium.Icon(color='blue')).add_to(m)
        punti_percorso.append(SEDE_COORDS) # Ritorno a casa
        
        folium.PolyLine(punti_percorso, color="blue", weight=2.5, opacity=1).add_to(m)
        
        st_folium(m, width="100%", height=400)

        st.subheader("Elenco Tappe in ordine:")
        for i, p in enumerate(giro):
            with st.expander(f"🚩 TAPPA {i+1}: {p['Cliente']}"):
                st.write(f"📮 CAP: {p['CAP']} | 🏠 {p['Indirizzo']} ({p['Comune']})")
                q = f"{p['Indirizzo']} {p['CAP']} {p['Comune']} Italy".replace(' ', '+')
                st.link_button(f"🧭 NAVIGA VERSO TAPPA {i+1}", f"https://www.google.com/maps/dir/?api=1&destination={q}&travelmode=driving", use_container_width=True)
        
        st.success(f"🏁 Dopo l'ultima tappa, rientro a: {SEDE_NOME}")

else:
    st.error("Impossibile caricare il database. Controlla il link Google Sheets.")
