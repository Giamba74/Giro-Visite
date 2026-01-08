import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time

# --- CONFIGURAZIONE E STILE ---
# initial_sidebar_state="expanded" forza la barra ad aprirsi subito
st.set_page_config(
    page_title="Brightstar Fixed", 
    page_icon="⭐", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# CSS per forzare la visibilità e lo stile Brightstar
st.markdown("""
    <style>
    /* Colori Sfondo */
    .stApp { background-color: #001a41; }
    
    /* Forza la sidebar a non nascondersi su schermi piccoli (Pixel) */
    [data-testid="stSidebar"] {
        background-color: #00122e;
        border-right: 2px solid #FFD700;
        min-width: 250px !important;
    }
    
    /* Titoli e Testi */
    h1 { color: #FFD700 !important; text-align: center; border-bottom: 3px solid #FFD700; }
    label { color: #FFD700 !important; font-weight: bold; }
    
    /* Card Clienti e Bottoni */
    .stButton>button { width: 100%; border-radius: 12px; background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); color: #002D72 !important; font-weight: bold; }
    .tappa-card { padding: 12px; border-radius: 10px; background-color: #002D72; border-left: 6px solid #FFD700; margin-bottom: 5px; }
    
    /* Stile tasto elimina */
    .stButton>button[kind="secondary"] {
        background: #ff4b4b !important;
        color: white !important;
        border: none;
        height: 45px;
    }
    </style>
    """, unsafe_allow_html=True)

SEDE_COORDS = (43.661888, 11.305728)
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

# --- FUNZIONI CORE ---
@st.cache_data(ttl=3600)
def get_coords(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="brightstar_fixed_v22")
    try:
        loc = geolocator.geocode(f"{indirizzo}, {cap}, {comune}, Italy", timeout=8)
        return (loc.latitude, loc.longitude) if loc else None
    except: return None

def load_data(url):
    try:
        path = url.split("/edit")[0] + "/export?format=csv"
        df = pd.read_csv(path)
        df.columns = [str(c).strip().upper() for c in df.columns]
        mappa = {c: "Cliente" if "CLIENTE" in c else "Indirizzo" if "INDIRIZZO" in c else "CAP" if "CAP" in c else "Comune" if "COMUNE" in c else "Visitato" if "VISITATO" in c else c for c in df.columns}
        return df.rename(columns=mappa)
    except: return None

# --- LOGICA DI SOSTITUZIONE ---
def sostituisci_cliente(idx):
    giro = st.session_state.giro_igt
    giro.pop(idx)
    
    nomi_presenti = [p['Cliente'] for p in giro]
    mask = ~st.session_state.df_all['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
    mask &= ~st.session_state.df_all['Cliente'].isin(nomi_presenti)
    
    if st.session_state.sel_comune != "Tutti":
        mask &= (st.session_state.df_all['Comune'] == st.session_state.sel_comune)
        
    sostituti = st.session_state.df_all[mask].head(10).to_dict('records')
    pos_rif = giro[-1]['coords'] if giro else SEDE_COORDS
    
    for s in sostituti:
        coords = get_coords(s['Indirizzo'], s['Comune'], s['CAP'])
        if coords:
            s['coords'] = coords
            giro.append(s)
            st.session_state.giro_igt = giro
            return
    st.warning("Nessun sostituto trovato.")

# --- INTERFACCIA ---
df = load_data(URL_SHEET)

if df is not None:
    st.session_state.df_all = df
    
    # BARRA LATERALE FISSA (Sidebar)
    with st.sidebar:
        st.image("https://www.brightstarlottery.co.uk/wp-content/uploads/2021/05/brightstar-logo-white.png", use_container_width=True)
        st.write("### 🛠️ CONFIGURAZIONE")
        
        comuni = sorted(df['Comune'].fillna("N/D").unique().tolist())
        st.session_state.sel_comune = st.selectbox("Filtra Zona:", ["Tutti"] + comuni)
        
        forzati = st.multiselect("Clienti Obbligatori:", sorted(df['Cliente'].unique().tolist()))
        
        st.divider()
        gen_button = st.button("🚀 GENERA GIRO")

    # --- CORPO CENTRALE ---
    st.title("⭐ BRIGHTSTAR VISITE")

    if gen_button:
        with st.status("Calcolo percorso ottimale..."):
            giro = []
            selezionati = df[df['Cliente'].isin(forzati)].to_dict('records')
            for r in selezionati:
                c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                if c: r['coords'] = c; giro.append(r)
            
            mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
            mask &= ~df['Cliente'].isin([x['Cliente'] for x in giro])
            if st.session_state.sel_comune != "Tutti": mask &= (df['Comune'] == st.session_state.sel_comune)
            
            extra = df[mask].head(20).to_dict('records')
            for r in extra:
                if len(giro) >= 10: break
                c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                if c: r['coords'] = c; giro.append(r)
            
            # Ordinamento Vicino più Prossimo
            giro_opt = []
            pos = SEDE_COORDS
            while giro:
                prox = min(giro, key=lambda x: geodesic(pos, x['coords']).km)
                giro_opt.append(prox)
                pos = prox['coords']
                giro.remove(prox)
            st.session_state.giro_igt = giro_opt

    # Visualizzazione Risultati
    if 'giro_igt' in st.session_state:
        # Mappa
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        punti = [SEDE_COORDS] + [p['coords'] for p in st.session_state.giro_igt] + [SEDE_COORDS]
        folium.PolyLine(punti, color="#FFD700", weight=5).add_to(m)
        st_folium(m, width="100%", height=300, key="map_fixed")

        st.write("---")
        
        for i, p in enumerate(st.session_state.giro_igt):
            col_txt, col_nav, col_del = st.columns([3, 2, 1])
            with col_txt:
                st.markdown(f"""<div class="tappa-card"><b>{i+1}. {p['Cliente']}</b><br><small>{p['Indirizzo']}</small></div>""", unsafe_allow_html=True)
            with col_nav:
                addr = f"{p['Indirizzo']} {p['Comune']}".replace(' ', '%20')
                st.link_button("🚙 WAZE", f"https://waze.com/ul?q={addr}&navigate=yes")
            with col_del:
                if st.button("❌", key=f"del_{i}"):
                    sostituisci_cliente(i)
                    st.rerun()
