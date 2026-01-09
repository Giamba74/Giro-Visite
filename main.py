import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Brightstar Visite", page_icon="⭐", layout="wide")

# --- CSS CUSTOM PER FISSARE GLI ELEMENTI ---
st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    h1 { color: #FFD700 !important; text-align: center; border-bottom: 2px solid #FFD700; padding-bottom: 10px; margin-bottom: 20px;}
    
    /* Stile Sezione Comandi in alto */
    .header-box {
        background-color: #00122e;
        padding: 20px;
        border-radius: 15px;
        border: 1px solid #FFD700;
        margin-bottom: 20px;
    }
    
    label { color: #FFD700 !important; font-weight: bold; }
    
    /* Bottoni */
    .stButton>button { 
        width: 100%; 
        border-radius: 12px; 
        background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); 
        color: #002D72 !important; 
        font-weight: bold; 
        border: none;
        height: 3em;
    }
    
    /* Card Tappe */
    .tappa-card { 
        padding: 12px; 
        border-radius: 10px; 
        background-color: #002D72; 
        border-left: 6px solid #FFD700; 
        margin-bottom: 5px; 
    }
    
    /* Tasto Elimina Rosso */
    div[data-testid="column"] button {
        background: #ff4b4b !important;
        color: white !important;
        border: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONFIGURAZIONE DATI ---
SEDE_COORDS = (43.661888, 11.305728)
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

@st.cache_data(ttl=3600)
def get_coords(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="brightstar_final_v23")
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
        df = df.rename(columns=mappa)
        df['Comune'] = df['Comune'].fillna("N/D")
        df['CAP'] = df['CAP'].fillna("N/D").astype(str)
        return df
    except: return None

# --- LOGICA ELIMINAZIONE ---
def rimuovi_cliente(indice):
    if 'giro_igt' in st.session_state:
        st.session_state.giro_igt.pop(indice)
        st.toast("Cliente rimosso dal giro!")

# --- INTERFACCIA PRINCIPALE ---
st.markdown("<div style='text-align: center;'><img src='https://www.brightstarlottery.co.uk/wp-content/uploads/2021/05/brightstar-logo-white.png' width='200'></div>", unsafe_allow_html=True)
st.title("⭐ BRIGHTSTAR VISITE")

df = load_data(URL_SHEET)

if df is not None:
    st.session_state.df_all = df
    
    # --- BOX COMANDI FISSO SULLA PAGINA ---
    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            comuni = sorted(df['Comune'].unique().tolist())
            sel_comune = st.selectbox("📍 Comune:", ["Tutti"] + comuni)
        with col2:
            caps = sorted(df['CAP'].unique().tolist())
            sel_cap = st.selectbox("📮 CAP:", ["Tutti"] + caps)
            
        forzati = st.multiselect("📌 Forza clienti nel giro:", sorted(df['Cliente'].unique().tolist()))
        
        if st.button("🚀 GENERA / RESETTA GIRO"):
            with st.status("Ottimizzazione percorso..."):
                giro = []
                # 1. Aggiungi forzati
                selezionati = df[df['Cliente'].isin(forzati)].to_dict('records')
                for r in selezionati:
                    c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                    if c: r['coords'] = c; giro.append(r)
                
                # 2. Riempi fino a 10
                mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
                mask &= ~df['Cliente'].isin([x['Cliente'] for x in giro])
                if sel_comune != "Tutti": mask &= (df['Comune'] == sel_comune)
                if sel_cap != "Tutti": mask &= (df['CAP'] == sel_cap)
                
                extra = df[mask].head(20).to_dict('records')
                for r in extra:
                    if len(giro) >= 10: break
                    c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                    if c: r['coords'] = c; giro.append(r)
                
                # 3. Ordina per distanza
                giro_opt = []
                pos = SEDE_COORDS
                while giro:
                    prox = min(giro, key=lambda x: geodesic(pos, x['coords']).km)
                    giro_opt.append(prox)
                    pos = prox['coords']
                    giro.remove(prox)
                st.session_state.giro_igt = giro_opt
        st.markdown("</div>", unsafe_allow_html=True)

    # --- RISULTATI ---
    if 'giro_igt' in st.session_state and st.session_state.giro_igt:
        # Mappa
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        punti = [SEDE_COORDS] + [p['coords'] for p in st.session_state.giro_igt] + [SEDE_COORDS]
        folium.PolyLine(punti, color="#FFD700", weight=5).add_to(m)
        st_folium(m, width="100%", height=350, key="map_view")

        st.write("### 📋 Elenco Visite del Giorno")
        
        # Lista dinamica con eliminazione
        for i, p in enumerate(st.session_state.giro_igt):
            col_info, col_del = st.columns([4, 1])
            with col_info:
                st.markdown(f"""<div class="tappa-card"><b>{i+1}. {p['Cliente']}</b><br><small>{p['Indirizzo']} ({p['Comune']})</small></div>""", unsafe_allow_html=True)
                addr_url = f"https://waze.com/ul?q={p['Indirizzo'].replace(' ', '%20')}%20{p['Comune']}&navigate=yes"
                st.link_button(f"🚙 WAZE", addr_url)
            with col_del:
                # Tasto eliminazione corretto
                if st.button("❌", key=f"btn_del_{i}_{p['Cliente']}"):
                    rimuovi_cliente(i)
                    st.rerun()
            st.write("---")
    elif 'giro_igt' in st.session_state:
        st.warning("Giro vuoto. Seleziona altri parametri o clienti.")

else:
    st.error("Errore nel caricamento del file Google Sheets.")
