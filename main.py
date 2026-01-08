import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time

# --- TEMA COLORI BRIGHTSTAR ---
# Blu: #002D72 | Oro: #FFD700 | Bianco: #FFFFFF
st.set_page_config(page_title="Brightstar Giro Visite", page_icon="⭐", layout="wide")

st.markdown("""
    <style>
    /* Sfondo Generale */
    .stApp {
        background-color: #001a41;
    }
    
    /* Intestazione */
    h1 {
        color: #FFD700 !important;
        text-align: center;
        font-family: 'Arial Black', sans-serif;
        text-shadow: 2px 2px 4px #000000;
        border-bottom: 2px solid #FFD700;
        padding-bottom: 10px;
    }
    
    /* Pulsanti */
    .stButton>button {
        width: 100%;
        border-radius: 50px;
        height: 3.5em;
        background: linear-gradient(145deg, #FFD700, #C5A000);
        color: #002D72 !important;
        font-weight: bold;
        font-size: 18px;
        border: 2px solid #FFFFFF;
        box-shadow: 0px 4px 15px rgba(255, 215, 0, 0.3);
        transition: 0.3s;
    }
    .stButton>button:hover {
        transform: scale(1.02);
        box-shadow: 0px 6px 20px rgba(255, 215, 0, 0.5);
        color: #000000 !important;
    }
    
    /* Card delle Tappe */
    .tappa-card {
        padding: 20px;
        border-radius: 15px;
        background-color: #002D72;
        border: 1px solid #FFD700;
        margin-bottom: 15px;
        box-shadow: 5px 5px 15px rgba(0,0,0,0.3);
    }
    .tappa-header {
        color: #FFD700;
        font-weight: bold;
        font-size: 1.2em;
        margin-bottom: 5px;
    }
    .tappa-info {
        color: #FFFFFF;
        font-size: 0.9em;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #00122e;
        border-right: 2px solid #FFD700;
    }
    label { color: #FFD700 !important; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- CONFIGURAZIONE DATI ---
SEDE_NOME = "⭐ SEDE BRIGHTSTAR"
SEDE_COORDS = (43.661888, 11.305728) 
URL_SHEET = "INCOLLA_QUI_IL_TUO_LINK_DI_GOOGLE_SHEETS"

@st.cache_data(ttl=3600)
def get_coords_smart(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="brightstar_nav_v11")
    ind, com, cp = str(indirizzo).strip(), str(comune).strip(), str(cap).replace(".0", "").strip()
    for q in [f"{ind}, {cp}, {com}, Italy", f"{ind}, {com}, Italy"]:
        try:
            loc = geolocator.geocode(q, timeout=7)
            if loc: return (loc.latitude, loc.longitude)
        except: continue
    return None

def load_data(url):
    try:
        if "/edit" in url: url = url.split("/edit")[0] + "/export?format=csv"
        df = pd.read_csv(url)
        df.columns = [str(c).strip().upper() for c in df.columns]
        mappa = {c: c.capitalize() for c in df.columns if c.lower() in ['cliente', 'indirizzo', 'cap', 'comune', 'visitato']}
        return df.rename(columns=mappa)
    except: return None

# --- UI ---
st.title("⭐ BRIGHTSTAR GIRO VISITE")

df = load_data(URL_SHEET)

if df is not None:
    with st.sidebar:
        st.image("https://www.brightstarlottery.co.uk/wp-content/uploads/2021/05/brightstar-logo-white.png", width=200) # Logo placeholder
        st.markdown("### 🔍 FILTRI RICERCA")
        comuni = sorted(df['Comune'].fillna("").unique().tolist())
        sel_comune = st.selectbox("📍 COMUNE:", ["Tutti"] + comuni)
        
        caps = sorted(df['CAP'].fillna("").astype(str).unique().tolist())
        sel_cap = st.selectbox("📮 CAP:", ["Tutti"] + caps)
        
    mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
    if sel_comune != "Tutti": mask &= (df['Comune'] == sel_comune)
    if sel_cap != "Tutti": mask &= (df['CAP'] == sel_cap)
    da_visitare = df[mask].copy()

    if st.button("🚀 GENERA IL GIRO FORTUNATO"):
        clienti_localizzati = []
        with st.status("🌟 Elaborazione percorso ottimale...", expanded=True) as status:
            campione = da_visitare.head(15).to_dict('records')
            for row in campione:
                coords = get_coords_smart(row['Indirizzo'], row['Comune'], row['CAP'])
                if coords:
                    row['coords'] = coords
                    clienti_localizzati.append(row)
                time.sleep(0.8)

            if clienti_localizzati:
                giro = []
                pos = SEDE_COORDS
                while len(giro) < 10 and clienti_localizzati:
                    prossimo = min(clienti_localizzati, key=lambda x: geodesic(pos, x['coords']).km)
                    giro.append(prossimo)
                    pos = prossimo['coords']
                    clienti_localizzati.remove(prossimo)
                st.session_state.giro = giro
                status.update(label="✨ Percorso pronto!", state="complete")
            else:
                status.update(label="❌ Nessun cliente trovato.", state="error")

    if 'giro' in st.session_state:
        giro = st.session_state.giro
        
        # Mappa Custom (Colori Brightstar)
        m = folium.Map(location=SEDE_COORDS, zoom_start=11, tiles="CartoDB voyager")
        punti = [SEDE_COORDS] + [p['coords'] for p in giro] + [SEDE_COORDS]
        folium.PolyLine(punti, color="#002D72", weight=5, opacity=0.8).add_to(m)
        folium.Marker(SEDE_COORDS, popup="START", icon=folium.Icon(color='blue', icon='star')).add_to(m)
        
        for i, p in enumerate(giro):
            folium.Marker(p['coords'], popup=p['Cliente'], icon=folium.Icon(color='orange', icon='location-arrow')).add_to(m)
        
        st_folium(m, width="100%", height=450)

        st.markdown("### 📋 ORDINE VISITE")
        for i, p in enumerate(giro):
            st.markdown(f"""
            <div class="tappa-card">
                <div class="tappa-header">🌟 Tappa {i+1}: {p['Cliente']}</div>
                <div class="tappa-info">🏠 {p['Indirizzo']}, {p['CAP']} {p['Comune']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            query = f"{p['Indirizzo']} {p['Comune']} Italy".replace(' ', '+')
            st.link_button(f"🧭 NAVIGA VERSO {p['Cliente']}", 
                          f"https://www.google.com/maps/dir/?api=1&destination={query}&travelmode=driving")
        
        st.success("🏁 Itinerario concluso. Buon lavoro!")
else:
    st.error("Errore nel collegamento dati. Controlla il link Google Sheets.")
