import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time

# --- CONFIGURAZIONE E STILE BRIGHTSTAR ---
st.set_page_config(page_title="Brightstar Dynamic", page_icon="⭐", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    h1 { color: #FFD700 !important; text-align: center; border-bottom: 3px solid #FFD700; }
    .stButton>button { width: 100%; border-radius: 12px; background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); color: #002D72 !important; font-weight: bold; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #002D72; border-left: 8px solid #FFD700; margin-bottom: 5px; }
    .delete-btn button { background-color: #ff4b4b !important; color: white !important; height: 2em !important; font-size: 12px !important; }
    [data-testid="stSidebar"] { background-color: #00122e; border-right: 1px solid #FFD700; }
    </style>
    """, unsafe_allow_html=True)

SEDE_COORDS = (43.661888, 11.305728)
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

@st.cache_data(ttl=3600)
def get_coords(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="brightstar_dynamic_v21")
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
def elimina_e_sostituisci(index_to_remove):
    current_giro = st.session_state.giro_igt
    # Rimuoviamo il cliente
    current_giro.pop(index_to_remove)
    
    # Cerchiamo un sostituto tra i non visitati e non presenti nel giro
    nomi_nel_giro = [p['Cliente'] for p in current_giro]
    mask = ~st.session_state.df_all['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
    mask &= ~st.session_state.df_all['Cliente'].isin(nomi_nel_giro)
    
    potenziali = st.session_state.df_all[mask].head(10).to_dict('records')
    
    # Troviamo il più vicino all'ultima tappa rimasta o alla sede
    pos_rif = current_giro[-1]['coords'] if current_giro else SEDE_COORDS
    
    nuovo_cliente = None
    for p in potenziali:
        coords = get_coords(p['Indirizzo'], p['Comune'], p['CAP'])
        if coords:
            p['coords'] = coords
            nuovo_cliente = p
            break
            
    if nuovo_cliente:
        current_giro.append(nuovo_cliente)
        st.session_state.giro_igt = current_giro
        st.toast(f"✅ Sostituito con {nuovo_cliente['Cliente']}")
    else:
        st.warning("Nessun sostituto trovato nelle vicinanze.")

# --- UI ---
st.title("⭐ BRIGHTSTAR DYNAMIC")
df = load_data(URL_SHEET)

if df is not None:
    st.session_state.df_all = df
    with st.sidebar:
        st.image("https://www.brightstarlottery.co.uk/wp-content/uploads/2021/05/brightstar-logo-white.png", width=180)
        comuni = sorted(df['Comune'].fillna("N/D").unique().tolist())
        sel_comune = st.selectbox("Filtra Zona:", ["Tutti"] + comuni)
        forzati = st.multiselect("Clienti Obbligatori:", sorted(df['Cliente'].unique().tolist()))

    if st.button("🚀 GENERA GIRO INIZIALE"):
        # Logica generazione (uguale alla precedente ma salva in session_state)
        with st.status("Calcolo..."):
            giro = []
            selezionati = df[df['Cliente'].isin(forzati)].to_dict('records')
            for r in selezionati:
                c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                if c: r['coords'] = c; giro.append(r)
            
            posti = 10 - len(giro)
            if posti > 0:
                mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
                mask &= ~df['Cliente'].isin([x['Cliente'] for x in giro])
                if sel_comune != "Tutti": mask &= (df['Comune'] == sel_comune)
                extra = df[mask].head(15).to_dict('records')
                for r in extra:
                    if len(giro) >= 10: break
                    c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                    if c: r['coords'] = c; giro.append(r)
            
            # Ottimizzazione
            giro_opt = []
            pos = SEDE_COORDS
            while giro:
                prox = min(giro, key=lambda x: geodesic(pos, x['coords']).km)
                giro_opt.append(prox)
                pos = prox['coords']
                giro.remove(prox)
            st.session_state.giro_igt = giro_opt

    # --- DISPLAY DINAMICO ---
    if 'giro_igt' in st.session_state:
        # Mappa
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        punti = [SEDE_COORDS] + [p['coords'] for p in st.session_state.giro_igt] + [SEDE_COORDS]
        folium.PolyLine(punti, color="#FFD700", weight=4).add_to(m)
        st_folium(m, width="100%", height=300, key="map")

        st.markdown("### 📋 Gestione Tappe")
        for i, p in enumerate(st.session_state.giro_igt):
            col_info, col_del = st.columns([4, 1])
            with col_info:
                st.markdown(f"""<div class="tappa-card"><b>{i+1}. {p['Cliente']}</b><br><small>{p['Indirizzo']} ({p['Comune']})</small></div>""", unsafe_allow_html=True)
            with col_del:
                if st.button("❌", key=f"del_{i}"):
                    elimina_e_sostituisci(i)
                    st.rerun()
            
            # Navigazione
            addr = f"{p['Indirizzo']} {p['Comune']}".replace(' ', '%20')
            st.link_button(f"🚙 NAVIGA VERSO {p['Cliente']}", f"https://waze.com/ul?q={addr}&navigate=yes")
            st.write("---")
