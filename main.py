import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time

# --- CONFIGURAZIONE E STILE BRIGHTSTAR ---
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
    label { color: #FFD700 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- CONFIGURAZIONE ---
SEDE_COORDS = (43.661888, 11.305728)
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

@st.cache_data(ttl=3600)
def get_coords_smart(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="brightstar_final_v20")
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

# --- UI PRINCIPALE ---
st.title("⭐ BRIGHTSTAR VISITE PRO")
df = load_data(URL_SHEET)

if df is not None:
    # Pulizia dati per i filtri
    df['Comune'] = df['Comune'].fillna("N/D")
    df['CAP'] = df['CAP'].fillna("N/D").astype(str)
    
    with st.sidebar:
        st.image("https://www.brightstarlottery.co.uk/wp-content/uploads/2021/05/brightstar-logo-white.png", width=180)
        st.divider()
        
        st.markdown("### 🛠️ OPZIONI GIRO")
        # Filtri zona
        comuni = sorted(df['Comune'].unique().tolist())
        sel_comune = st.selectbox("1. Filtra per Comune:", ["Tutti"] + comuni)
        
        # Filtro per selezione manuale (IL MENU A TENDINA)
        st.divider()
        st.markdown("### 📌 CLIENTI FORZATI")
        clienti_disponibili = sorted(df['Cliente'].unique().tolist())
        forzati_manuali = st.multiselect("Scegli i clienti obbligatori di oggi:", clienti_disponibili)
        
    # --- LOGICA DI GENERAZIONE ---
    if st.button("🚀 GENERA PERCORSO OTTIMIZZATO"):
        with st.status("🌟 Elaborazione itinerario veloce...", expanded=True) as status:
            giro_finale = []
            
            # 1. Carichiamo prima i forzati manuali
            df_forzati = df[df['Cliente'].isin(forzati_manuali)].to_dict('records')
            for row in df_forzati:
                coords = get_coords_smart(row['Indirizzo'], row['Comune'], row['CAP'])
                if coords:
                    row['coords'] = coords
                    giro_finale.append(row)
            
            # 2. Se mancano tappe (per arrivare a 10), cerchiamo le migliori nella zona scelta
            posti_residui = 10 - len(giro_finale)
            if posti_residui > 0:
                mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
                mask &= ~df['Cliente'].isin(forzati_manuali) # Escludi quelli già scelti
                if sel_comune != "Tutti": mask &= (df['Comune'] == sel_comune)
                
                potenziali = df[mask].head(20).to_dict('records')
                clienti_extra = []
                for row in potenziali:
                    coords = get_coords_smart(row['Indirizzo'], row['Comune'], row['CAP'])
                    if coords:
                        row['coords'] = coords
                        clienti_extra.append(row)
                    if len(clienti_extra) >= posti_residui: break
                
                # Uniamo tutto
                tutti_i_selezionati = giro_finale + clienti_extra
            else:
                tutti_i_selezionati = giro_finale

            # 3. OTTIMIZZAZIONE PERCORSO (Nearest Neighbor)
            itinerario_ordinato = []
            pos_attuale = SEDE_COORDS
            distanza_totale = 0
            
            while tutti_i_selezionati:
                prossimo = min(tutti_i_selezionati, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                distanza_totale += geodesic(pos_attuale, prossimo['coords']).km
                itinerario_ordinato.append(prossimo)
                pos_attuale = prossimo['coords']
                tutti_i_selezionati.remove(prossimo)
            
            # Rientro a casa
            distanza_totale += geodesic(pos_attuale, SEDE_COORDS).km
            
            st.session_state.giro_igt = itinerario_ordinato
            st.session_state.km_igt = round(distanza_totale, 1)
            status.update(label=f"✅ Itinerario di {st.session_state.km_igt} km pronto!", state="complete")

    # --- MAPPA E LISTA WAZE ---
    if 'giro_igt' in st.session_state:
        st.info(f"🛣️ Percorso ottimizzato inclusi clienti scelti: **{st.session_state.km_igt} km**")
        
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        punti = [SEDE_COORDS] + [p['coords'] for p in st.session_state.giro_igt] + [SEDE_COORDS]
        folium.PolyLine(punti, color="#FFD700", weight=5).add_to(m)
        folium.Marker(SEDE_COORDS, icon=folium.Icon(color='darkblue', icon='star')).add_to(m)
        
        for i, p in enumerate(st.session_state.giro_igt):
            folium.Marker(p['coords'], popup=p['Cliente']).add_to(m)
        
        st_folium(m, width="100%", height=400)

        for i, p in enumerate(st.session_state.giro_igt):
            st.markdown(f"""<div class="tappa-card"><div class="tappa-header">TAPPA {i+1}: {p['Cliente']}</div>
                        <div class="tappa-info">📍 {p['Indirizzo']} ({p['Comune']})</div></div>""", unsafe_allow_html=True)
            addr_waze = f"{p['Indirizzo']} {p['Comune']}".replace(' ', '%20')
            st.link_button(f"🚙 NAVIGA CON WAZE", f"https://waze.com/ul?q={addr_waze}&navigate=yes", use_container_width=True)
else:
    st.error("Connessione ai dati fallita.")
