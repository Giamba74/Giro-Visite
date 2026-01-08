import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time

# --- CONFIGURAZIONE E STILE ---
st.set_page_config(page_title="Brightstar Visite", page_icon="⭐", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    h1 { color: #FFD700 !important; text-align: center; border-bottom: 3px solid #FFD700; padding-bottom: 10px; }
    .stButton>button {
        width: 100%; border-radius: 12px; height: 3.5em;
        background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%);
        color: #002D72 !important; font-weight: bold; border: 1px solid #FFFFFF;
    }
    .tappa-card {
        padding: 15px; border-radius: 12px; background-color: #002D72;
        border-left: 8px solid #FFD700; margin-bottom: 10px;
    }
    .tappa-header { color: #FFD700; font-weight: bold; }
    .tappa-info { color: #FFFFFF; font-size: 0.9em; }
    [data-testid="stSidebar"] { background-color: #00122e; border-right: 1px solid #FFD700; }
    </style>
    """, unsafe_allow_html=True)

# --- CONFIGURAZIONE ---
SEDE_COORDS = (43.661888, 11.305728) # Strada in Chianti
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

@st.cache_data(ttl=3600)
def get_coords_smart(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="brightstar_fast_navigator_v16")
    query = f"{str(indirizzo)}, {str(cap)}, {str(comune)}, Italy"
    try:
        loc = geolocator.geocode(query, timeout=8)
        if not loc: loc = geolocator.geocode(f"{str(indirizzo)}, {str(comune)}, Italy", timeout=8)
        return (loc.latitude, loc.longitude) if loc else None
    except: return None

def load_data(url):
    try:
        path = url.split("/edit")[0] + "/export?format=csv"
        df = pd.read_csv(path)
        df.columns = [str(c).strip().upper() for c in df.columns]
        mappa = {c: "Cliente" if "CLIENTE" in c else "Indirizzo" if "INDIRIZZO" in c else "CAP" if "CAP" in c else "Comune" if "COMUNE" in c else "Visitato" if "VISITATO" in c else c for c in df.columns}
        df = df.rename(columns=mappa)
        return df
    except: return None

# --- UI ---
st.title("⭐ BRIGHTSTAR VISITE")
df = load_data(URL_SHEET)

if df is not None:
    with st.sidebar:
        st.image("https://www.brightstarlottery.co.uk/wp-content/uploads/2021/05/brightstar-logo-white.png", width=180)
        st.divider()
        comuni = sorted(df['Comune'].dropna().unique().tolist())
        sel_comune = st.selectbox("Seleziona Comune:", ["Tutti"] + comuni)
        caps = sorted(df['CAP'].dropna().astype(str).unique().tolist())
        sel_cap = st.selectbox("Seleziona CAP:", ["Tutti"] + caps)

    # Filtro clienti non visitati
    mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
    if sel_comune != "Tutti": mask &= (df['Comune'] == sel_comune)
    if sel_cap != "Tutti": mask &= (df['CAP'].astype(str) == sel_cap)
    da_visitare_raw = df[mask].copy()

    if st.button("🚀 GENERA IL PERCORSO PIÙ VELOCE (10 TAPPE)"):
        clienti_potenziali = []
        with st.status("🔍 Ricerca posizioni e ottimizzazione...", expanded=True) as status:
            # Cerchiamo le coordinate per i primi 30 (per sceglierne i 10 più vicini)
            campione = da_visitare_raw.head(30).to_dict('records')
            for row in campione:
                coords = get_coords_smart(row['Indirizzo'], row['Comune'], row['CAP'])
                if coords:
                    row['coords'] = coords
                    clienti_potenziali.append(row)
                time.sleep(0.8)

            if clienti_potenziali:
                # --- ALGORITMO DI OTTIMIZZAZIONE ---
                giro_ottimizzato = []
                pos_attuale = SEDE_COORDS
                distanza_totale = 0
                
                while len(giro_ottimizzato) < 10 and clienti_potenziali:
                    # Trova il cliente più vicino alla posizione in cui ti trovi
                    prossimo = min(clienti_potenziali, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                    distanza_tappa = geodesic(pos_attuale, prossimo['coords']).km
                    distanza_totale += distanza_tappa
                    
                    giro_ottimizzato.append(prossimo)
                    pos_attuale = prossimo['coords']
                    clienti_potenziali.remove(prossimo)
                
                # Aggiungi ritorno a casa
                distanza_totale += geodesic(pos_attuale, SEDE_COORDS).km
                
                st.session_state.giro_final = giro_ottimizzato
                st.session_state.km_final = round(distanza_totale, 1)
                status.update(label=f"✅ Ottimizzato: {st.session_state.km_final} km totali", state="complete")
            else:
                status.update(label="❌ Nessun indirizzo trovato.", state="error")

    if 'giro_final' in st.session_state:
        st.info(f"🛣️ Percorso più veloce: **{st.session_state.km_final} km** (A/R inclusa)")
        
        # Mappa con linea del percorso
        m = folium.Map(location=SEDE_COORDS, zoom_start=10)
        punti_linea = [SEDE_COORDS]
        folium.Marker(SEDE_COORDS, popup="CASA", icon=folium.Icon(color='darkblue', icon='star')).add_to(m)
        
        for i, p in enumerate(st.session_state.giro_final):
            folium.Marker(p['coords'], popup=p['Cliente'], tooltip=f"Tappa {i+1}").add_to(m)
            punti_linea.append(p['coords'])
        
        punti_linea.append(SEDE_COORDS)
        folium.PolyLine(punti_linea, color="#FFD700", weight=5, opacity=0.8).add_to(m)
        st_folium(m, width="100%", height=400)

        for i, p in enumerate(st.session_state.giro_final):
            st.markdown(f"""<div class="tappa-card"><div class="tappa-header">TAPPA {i+1}: {p['Cliente']}</div>
                        <div class="tappa-info">📍 {p['Indirizzo']} ({p['Comune']})</div></div>""", unsafe_allow_html=True)
            
            addr_waze = f"{p['Indirizzo']} {p['Comune']}".replace(' ', '%20')
            st.link_button(f"🚙 NAVIGA CON WAZE", f"https://waze.com/ul?q={addr_waze}&navigate=yes", use_container_width=True)
