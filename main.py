import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import time
from datetime import datetime
import urllib.parse

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="Brightstar Pro Navigator",
    page_icon="⭐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- 2. STILE AZIENDALE BRIGHTSTAR / IGT ---
st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    h1 { color: #FFD700 !important; text-align: center; border-bottom: 3px solid #FFD700; padding-bottom: 10px; font-family: 'Arial Black', sans-serif; }
    .header-box { background-color: #00122e; padding: 15px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 20px; }
    label { color: #FFD700 !important; font-weight: bold; }
    .stButton>button { 
        width: 100%; border-radius: 12px; height: 3.5em; 
        background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); 
        color: #002D72 !important; font-weight: bold; border: none;
    }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #002D72; border-left: 8px solid #FFD700; margin-bottom: 5px; color: white; }
    .btn-waze button { background: #33ccff !important; color: white !important; }
    .btn-fatto button { background: #28a745 !important; color: white !important; }
    .btn-del button { background: #ff4b4b !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNZIONI AGENTE AI (VOCE E COORD) ---
def parla(testo):
    """Sintesi vocale per Pixel 9 Pro"""
    componente_audio = f"""<script>var msg = new SpeechSynthesisUtterance('{testo}'); msg.lang = 'it-IT'; window.speechSynthesis.speak(msg);</script>"""
    st.components.v1.html(componente_audio, height=0)

@st.cache_data(ttl=3600)
def get_coords(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="brightstar_final_ai")
    try:
        loc = geolocator.geocode(f"{indirizzo}, {cap}, {comune}, Italy", timeout=8)
        return (loc.latitude, loc.longitude) if loc else None
    except: return None

def load_data(url):
    try:
        path = url.split("/edit")[0] + "/export?format=csv"
        df = pd.read_csv(path)
        df.columns = [str(c).strip().upper() for c in df.columns]
        mappa = {c: "Cliente" if "CLIENTE" in c else "Indirizzo" if "INDIRIZZO" in c else "CAP" if "CAP" in c else "Comune" if "COMUNE" in c else "CODICE" if "COD" in c else "Visitato" if "VISITATO" in c else c for c in df.columns}
        df = df.rename(columns=mappa)
        df['Comune'] = df['Comune'].fillna("N/D").astype(str).str.upper()
        df['CAP'] = df['CAP'].fillna("N/D").astype(str)
        return df
    except: return None

# --- 4. INIZIALIZZAZIONE SESSIONE ---
if 'giro_igt' not in st.session_state: st.session_state.giro_igt = []
if 'report_serale' not in st.session_state: st.session_state.report_serale = []

SEDE_COORDS = (43.661888, 11.305728) # Strada in Chianti
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

# --- 5. INTERFACCIA ---
st.markdown("<div style='text-align: center;'><img src='https://www.brightstarlottery.co.uk/wp-content/uploads/2021/05/brightstar-logo-white.png' width='220'></div>", unsafe_allow_html=True)
st.title("⭐ BRIGHTSTAR VISITE AI")

df = load_data(URL_SHEET)

if df is not None:
    # --- BOX COMANDI ---
    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            sel_comuni = st.multiselect("📍 Comuni:", sorted(df['Comune'].unique().tolist()))
        with c2:
            sel_caps = st.multiselect("📮 CAP:", sorted(df['CAP'].unique().tolist()))
        
        forzati = st.multiselect("📌 Clienti Obbligatori:", sorted(df['Cliente'].unique().tolist()))
        
        if st.button("🚀 GENERA PIANO OTTIMIZZATO"):
            with st.status("Calcolo percorso più veloce..."):
                giro = []
                # Aggiunta Forzati
                selezionati = df[df['Cliente'].isin(forzati)].to_dict('records')
                for r in selezionati:
                    c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                    if c: r['coords'] = c; giro.append(r)
                # Riempimento
                mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
                mask &= ~df['Cliente'].isin([x['Cliente'] for x in giro])
                if sel_comuni: mask &= (df['Comune'].isin(sel_comuni))
                if sel_caps: mask &= (df['CAP'].isin(sel_caps))
                extra = df[mask].head(15).to_dict('records')
                for r in extra:
                    if len(giro) >= 10: break
                    c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                    if c: r['coords'] = c; giro.append(r)
                # Ottimizzazione km
                opt = []
                pos = SEDE_COORDS
                while giro:
                    prox = min(giro, key=lambda x: geodesic(pos, x['coords']).km)
                    opt.append(prox)
                    pos = prox['coords']
                    giro.remove(prox)
                st.session_state.giro_igt = opt
                parla(f"Giro generato. Hai {len(opt)} tappe da completare.")
        st.markdown("</div>", unsafe_allow_html=True)

    # --- RISULTATI E MAPPA ---
    if st.session_state.giro_igt:
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        punti = [SEDE_COORDS] + [p['coords'] for p in st.session_state.giro_igt] + [SEDE_COORDS]
        folium.PolyLine(punti, color="#FFD700", weight=5).add_to(m)
        st_folium(m, width="100%", height=300, key="map_final")

        st.subheader("📋 Gestione Tappe")
        for i, p in enumerate(st.session_state.giro_igt):
            with st.container():
                st.markdown(f'<div class="tappa-card"><b>{i+1}. {p["Cliente"]}</b> (Cod: {p.get("CODICE","N/D")})<br><small>{p["Indirizzo"]}</small></div>', unsafe_allow_html=True)
                
                nota_v = st.text_area("Note/Materiali:", key=f"v_{i}", placeholder="Dettami qui...")
                
                col1, col2, col3 = st.columns([1,1,1])
                with col1:
                    url = f"https://waze.com/ul?q={p['Indirizzo'].replace(' ','%20')}%20{p['Comune']}&navigate=yes"
                    st.link_button("🚙 WAZE", url)
                with col2:
                    if st.button("✅ FATTO", key=f"f_{i}"):
                        st.session_state.report_serale.append({"cod": p.get("CODICE","N/D"), "nome": p["Cliente"], "nota": nota_v if nota_v else "Visita OK"})
                        st.session_state.giro_igt.pop(i)
                        parla("Ottimo lavoro, tappa completata.")
                        st.rerun()
                with col3:
                    if st.button("❌", key=f"d_{i}"):
                        st.session_state.giro_igt.pop(i)
                        st.rerun()
            st.write("---")

    # --- REPORT SERALE ---
    if st.session_state.report_serale:
        st.divider()
        data_s = datetime.now().strftime("%d/%m/%Y")
        st.subheader(f"✉️ Report Serale {data_s}")
        
        corpo = f"REPORT VISITE DEL {data_s} - GIAMBATTISTA GIACCHETTI\n\n"
        for r in st.session_state.report_serale:
            corpo += f"• COD: {r['cod']} - {r['nome']}\n  NOTA: {r['nota']}\n\n"
        
        st.text_area("Anteprima:", corpo, height=200)
        
        subj = f"REPORT VISITE DEL {data_s} - GIAMBATTISTA GIACCHETTI"
        link = f"mailto:giambattista.giacchetti@gmail.com?subject={urllib.parse.quote(subj)}&body={urllib.parse.quote(corpo)}"
        
        st.link_button("📧 INVIA REPORT FINALE", link, use_container_width=True)
        
        if st.button("🗑️ AZZERA TUTTO"):
            st.session_state.report_serale = []
            st.rerun()
else:
    st.error("Collega il Google Sheets per iniziare.")
