import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time

# --- TEMA COLORI BRIGHTSTAR (IGT STYLE) ---
# Blu Istituzionale: #002D72 | Oro: #FFD700 | Bianco: #FFFFFF
st.set_page_config(page_title="Brightstar Visite", page_icon="⭐", layout="wide")

st.markdown("""
    <style>
    /* Sfondo principale Blu Profondo */
    .stApp {
        background-color: #001a41;
    }
    
    /* Header Brightstar Oro */
    h1 {
        color: #FFD700 !important;
        text-align: center;
        font-family: 'Helvetica Neue', sans-serif;
        text-shadow: 2px 2px 4px #000000;
        border-bottom: 3px solid #FFD700;
        padding-bottom: 15px;
        margin-bottom: 30px;
    }
    
    /* Pulsanti Oro con Gradiente */
    .stButton>button {
        width: 100%;
        border-radius: 12px;
        height: 3.5em;
        background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%);
        color: #002D72 !important;
        font-weight: bold;
        font-size: 18px;
        border: 1px solid #FFFFFF;
        box-shadow: 0px 4px 10px rgba(255, 215, 0, 0.3);
        transition: 0.3s;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0px 6px 15px rgba(255, 215, 0, 0.5);
        color: #000000 !important;
    }
    
    /* Card Clienti in stile IGT */
    .tappa-card {
        padding: 20px;
        border-radius: 12px;
        background-color: #002D72;
        border-left: 8px solid #FFD700;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .tappa-header {
        color: #FFD700;
        font-weight: bold;
        font-size: 1.3em;
        margin-bottom: 5px;
    }
    .tappa-info {
        color: #FFFFFF;
        font-size: 1em;
        opacity: 0.9;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #00122e;
        border-right: 1px solid #FFD700;
    }
    .sidebar-text { color: #FFD700; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- DATI E LOGICA ---
SEDE_COORDS = (43.661888, 11.305728) # Strada in Chianti
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

@st.cache_data(ttl=3600)
def get_coords_smart(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="brightstar_igt_navigator")
    query = f"{str(indirizzo)}, {str(cap)}, {str(comune)}, Italy"
    try:
        loc = geolocator.geocode(query, timeout=8)
        if not loc:
            loc = geolocator.geocode(f"{str(indirizzo)}, {str(comune)}, Italy", timeout=8)
        return (loc.latitude, loc.longitude) if loc else None
    except: return None

def load_data(url):
    try:
        path = url.split("/edit")[0] + "/export?format=csv"
        df = pd.read_csv(path)
        df.columns = [str(c).strip().upper() for c in df.columns]
        mappa = {}
        for c in df.columns:
            if "CLIENTE" in c: mappa[c] = "Cliente"
            elif "INDIRIZZO" in c: mappa[c] = "Indirizzo"
            elif "CAP" in c: mappa[c] = "CAP"
            elif "COMUNE" in c: mappa[c] = "Comune"
            elif "VISITATO" in c: mappa[c] = "Visitato"
        df = df.rename(columns=mappa)
        # Assicura colonne esistenti
        for col in ["Cliente", "Indirizzo", "CAP", "Comune", "Visitato"]:
            if col not in df.columns: df[col] = "N/D" if col != "Visitato" else "No"
        return df
    except: return None

# --- UI ---
st.title("⭐ BRIGHTSTAR VISITE")

df = load_data(URL_SHEET)

if df is not None:
    with st.sidebar:
        st.markdown("<p class='sidebar-text'>FILTRI DI ZONA</p>", unsafe_allow_html=True)
        comuni = sorted(df['Comune'].unique().tolist())
        sel_comune = st.selectbox("Seleziona Comune:", ["Tutti"] + comuni)
        
        caps = sorted(df['CAP'].astype(str).unique().tolist())
        sel_cap = st.selectbox("Seleziona CAP:", ["Tutti"] + caps)

    mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
    if sel_comune != "Tutti": mask &= (df['Comune'] == sel_comune)
    if sel_cap != "Tutti": mask &= (df['CAP'].astype(str) == sel_cap)
    
    da_visitare = df[mask].copy()

    if st.button("🚀 GENERA GIRO OTTIMIZZATO"):
        clienti_localizzati = []
        with st.status("🌟 Calcolo percorso Brightstar...", expanded=True) as status:
            campione = da_visitare.head(15).to_dict('records')
            for row in campione:
                coords = get_coords_smart(row['Indirizzo'], row['Comune'], row['CAP'])
                if coords:
                    row['coords'] = coords
                    clienti_localizzati.append(row)
                time.sleep(1)

            if clienti_localizzati:
                # Algoritmo Prossimità
                giro = []
                pos = SEDE_COORDS
                while len(giro) < 10 and clienti_localizzati:
                    prossimo = min(clienti_localizzati, key=lambda x: geodesic(pos, x['coords']).km)
                    giro.append(prossimo)
                    pos = prossimo['coords']
                    clienti_localizzati.remove(prossimo)
                st.session_state.giro_bs = giro
                status.update(label="✨ Percorso Calcolato!", state="complete")
            else:
                status.update(label="⚠️ Nessun indirizzo trovato.", state="error")

    if 'giro_bs' in st.session_state:
        giro = st.session_state.giro_bs
        
        # Mappa Custom
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        folium.Marker(SEDE_COORDS, popup="START", icon=folium.Icon(color='darkblue', icon='star')).add_to(m)
        punti = [SEDE_COORDS] + [p['coords'] for p in giro] + [SEDE_COORDS]
        folium.PolyLine(punti, color="#FFD700", weight=5, opacity=0.8).add_to(m)
        
        for i, p in enumerate(giro):
            folium.Marker(p['coords'], popup=p['Cliente'], icon=folium.Icon(color='orange')).add_to(m)
        
        st_folium(m, width="100%", height=400)

        # Elenco Tappe
        st.markdown("### 📋 ORDINE DELLE VISITE")
        for i, p in enumerate(giro):
            st.markdown(f"""
            <div class="tappa-card">
                <div class="tappa-header">Tappa {i+1}: {p['Cliente']}</div>
                <div class="tappa-info">📍 {p['Indirizzo']}, {p['CAP']} {p['Comune']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            q = f"{p['Indirizzo']} {p['Comune']} Italy".replace(' ', '+')
            st.link_button(f"🧭 NAVIGA ORA", f"https://www.google.com/maps/dir/?api=1&destination={q}&travelmode=driving")

else:
    st.error("❌ Errore sincronizzazione Google Sheets.")
