import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Brightstar Visite", page_icon="⭐", layout="wide")

# --- CSS CUSTOM ---
st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    h1 { color: #FFD700 !important; text-align: center; border-bottom: 2px solid #FFD700; padding-bottom: 10px; margin-bottom: 20px;}
    .header-box {
        background-color: #00122e;
        padding: 15px;
        border-radius: 15px;
        border: 1px solid #FFD700;
        margin-bottom: 20px;
    }
    label { color: #FFD700 !important; font-weight: bold; }
    
    /* Bottoni Generali */
    .stButton>button { 
        width: 100%; 
        border-radius: 12px; 
        background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); 
        color: #002D72 !important; 
        font-weight: bold; 
        border: none;
    }
    
    /* Card Tappe */
    .tappa-card { 
        padding: 12px; 
        border-radius: 10px; 
        background-color: #002D72; 
        border-left: 6px solid #FFD700; 
        margin-bottom: 5px; 
    }

    /* Tasto Completato (Verde) */
    .btn-done button {
        background: linear-gradient(135deg, #28a745 0%, #1e7e34 100%) !important;
        color: white !important;
        border: none !important;
        font-size: 0.8em !important;
    }

    /* Tasto Elimina (Rosso) */
    .btn-del button {
        background: #ff4b4b !important;
        color: white !important;
        border: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- DATI E COORD ---
SEDE_COORDS = (43.661888, 11.305728)
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

@st.cache_data(ttl=3600)
def get_coords(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="brightstar_work_v25")
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
        df['Comune'] = df['Comune'].fillna("N/D").astype(str).str.upper()
        df['CAP'] = df['CAP'].fillna("N/D").astype(str)
        return df
    except: return None

# --- LOGICA DI SESSIONE ---
if 'visitati_oggi' not in st.session_state:
    st.session_state.visitati_oggi = []

def segna_completato(indice, nome_cliente):
    # Lo rimuoviamo dal giro attuale
    st.session_state.giro_igt.pop(indice)
    # Lo aggiungiamo alla lista nera della sessione (non apparirà più fino al refresh)
    st.session_state.visitati_oggi.append(nome_cliente)
    st.toast(f"✅ {nome_cliente} segnato come visitato!")

# --- INTERFACCIA ---
st.markdown("<div style='text-align: center;'><img src='https://www.brightstarlottery.co.uk/wp-content/uploads/2021/05/brightstar-logo-white.png' width='200'></div>", unsafe_allow_html=True)
st.title("⭐ BRIGHTSTAR VISITE")

df = load_data(URL_SHEET)

if df is not None:
    # Escludiamo i clienti già visitati in questa sessione
    df = df[~df['Cliente'].isin(st.session_state.visitati_oggi)]
    
    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            comuni_list = sorted(df['Comune'].unique().tolist())
            sel_comuni = st.multiselect("📍 Comuni:", comuni_list)
        with col2:
            caps_list = sorted(df['CAP'].unique().tolist())
            sel_caps = st.multiselect("📮 CAP:", caps_list)
        
        forzati = st.multiselect("📌 Priorità:", sorted(df['Cliente'].unique().tolist()))
        
        if st.button("🚀 GENERA NUOVO PIANO"):
            with st.status("Ottimizzazione percorso..."):
                giro = []
                # 1. Forzati
                selezionati = df[df['Cliente'].isin(forzati)].to_dict('records')
                for r in selezionati:
                    c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                    if c: r['coords'] = c; giro.append(r)
                
                # 2. Riempimento
                mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
                mask &= ~df['Cliente'].isin([x['Cliente'] for x in giro])
                if sel_comuni: mask &= (df['Comune'].isin(sel_comuni))
                if sel_caps: mask &= (df['CAP'].isin(sel_caps))
                
                extra = df[mask].head(15).to_dict('records')
                for r in extra:
                    if len(giro) >= 10: break
                    c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                    if c: r['coords'] = c; giro.append(r)
                
                # 3. Ordinamento
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
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        punti = [SEDE_COORDS] + [p['coords'] for p in st.session_state.giro_igt] + [SEDE_COORDS]
        folium.PolyLine(punti, color="#FFD700", weight=5).add_to(m)
        st_folium(m, width="100%", height=300, key="map_final")

        st.write(f"### 📋 Tappe rimanenti: {len(st.session_state.giro_igt)}")
        
        for i, p in enumerate(st.session_state.giro_igt):
            with st.container():
                st.markdown(f"""<div class="tappa-card"><b>{i+1}. {p['Cliente']}</b><br><small>{p['Indirizzo']}</small></div>""", unsafe_allow_html=True)
                
                c1, c2, c3 = st.columns([2, 2, 1])
                with c1:
                    addr_url = f"https://waze.com/ul?q={p['Indirizzo'].replace(' ', '%20')}%20{p['Comune']}&navigate=yes"
                    st.link_button("🚙 NAVIGA", addr_url)
                with c2:
                    st.markdown('<div class="btn-done">', unsafe_allow_html=True)
                    if st.button("✅ FATTO", key=f"done_{p['Cliente']}"):
                        segna_completato(i, p['Cliente'])
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                with c3:
                    st.markdown('<div class="btn-del">', unsafe_allow_html=True)
                    if st.button("❌", key=f"del_{p['Cliente']}"):
                        st.session_state.giro_igt.pop(i)
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
            st.write("---")
