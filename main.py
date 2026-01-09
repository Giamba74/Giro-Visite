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
    
    /* Colori bottoni specifici */
    div.stButton > button[key^="f_"] { background: #28a745 !important; color: white !important; } /* Verde Fatto */
    div.stButton > button[key^="d_"] { background: #ff4b4b !important; color: white !important; } /* Rosso Elimina */
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNZIONI AGENTE AI (VOCE E COORD) ---
def parla(testo):
    """Sintesi vocale per Pixel 9 Pro"""
    componente_audio = f"""<script>var msg = new SpeechSynthesisUtterance('{testo}'); msg.lang = 'it-IT'; window.speechSynthesis.speak(msg);</script>"""
    st.components.v1.html(componente_audio, height=0)

@st.cache_data(ttl=3600)
def get_coords(indirizzo, comune, cap):
    geolocator = Nominatim(user_agent="brightstar_final_ai_v26")
    try:
        loc = geolocator.geocode(f"{indirizzo}, {cap}, {comune}, Italy", timeout=8)
        if not loc:
            loc = geolocator.geocode(f"{indirizzo}, {comune}, Italy", timeout=8)
        return (loc.latitude, loc.longitude) if loc else None
    except: return None

def load_data(url):
    try:
        path = url.split("/edit")[0] + "/export?format=csv"
        df = pd.read_csv(path)
        df.columns = [str(c).strip().upper() for c in df.columns]
        # Mappatura flessibile delle colonne
        mappa = {}
        for c in df.columns:
            if "CLIENTE" in c or "RAGIONE" in c: mappa[c] = "Cliente"
            elif "INDIRIZZO" in c: mappa[c] = "Indirizzo"
            elif "CAP" in c: mappa[c] = "CAP"
            elif "COMUNE" in c: mappa[c] = "Comune"
            elif "CODICE" in c or "COD" in c: mappa[c] = "CODICE"
            elif "TELEFONO" in c or "TEL" in c: mappa[c] = "TELEFONO"
            elif "VISITATO" in c: mappa[c] = "Visitato"
        df = df.rename(columns=mappa)
        # Pulizia dati
        df['Comune'] = df['Comune'].fillna("N/D").astype(str).str.upper()
        df['CAP'] = df['CAP'].fillna("N/D").astype(str).str.replace(".0", "", regex=False)
        df['TELEFONO'] = df['TELEFONO'].fillna("").astype(str).str.replace(".0", "", regex=False)
        return df
    except Exception as e:
        st.error(f"Errore caricamento dati: {e}")
        return None

# --- 4. INIZIALIZZAZIONE SESSIONE ---
if 'giro_igt' not in st.session_state: st.session_state.giro_igt = []
if 'report_serale' not in st.session_state: st.session_state.report_serale = []

SEDE_COORDS = (43.661888, 11.305728) # Strada in Chianti
URL_SHEET = "https://docs.google.com/spreadsheets/d/1E9Fv9xOvGGumWGB7MjhAMbV5yzOqPtS1YRx-y4dypQ0/edit?usp=sharing"

# --- 5. INTERFACCIA PRINCIPALE ---
st.markdown("<div style='text-align: center;'><img src='https://www.brightstarlottery.co.uk/wp-content/uploads/2021/05/brightstar-logo-white.png' width='220'></div>", unsafe_allow_html=True)
st.title("⭐ BRIGHTSTAR VISITE AI")

df = load_data(URL_SHEET)

if df is not None:
    # --- BOX COMANDI FISSO ---
    with st.container():
        st.markdown("<div class='header-box'>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            sel_comuni = st.multiselect("📍 Comuni:", sorted(df['Comune'].unique().tolist()))
        with c2:
            sel_caps = st.multiselect("📮 CAP:", sorted(df['CAP'].unique().tolist()))
        
        forzati = st.multiselect("📌 Forza Clienti Specifici:", sorted(df['Cliente'].unique().tolist()))
        
        if st.button("🚀 GENERA PIANO OTTIMIZZATO"):
            with st.status("Ricerca indirizzi e ottimizzazione percorso..."):
                giro = []
                # 1. Aggiunta Forzati
                selezionati = df[df['Cliente'].isin(forzati)].to_dict('records')
                for r in selezionati:
                    c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                    if c: r['coords'] = c; giro.append(r)
                # 2. Riempimento fino a 10 tappe
                mask = ~df['Visitato'].astype(str).str.upper().str.strip().isin(['SÌ', 'SI', 'S'])
                mask &= ~df['Cliente'].isin([x['Cliente'] for x in giro])
                if sel_comuni: mask &= (df['Comune'].isin(sel_comuni))
                if sel_caps: mask &= (df['CAP'].isin(sel_caps))
                
                extra = df[mask].head(20).to_dict('records')
                for r in extra:
                    if len(giro) >= 10: break
                    c = get_coords(r['Indirizzo'], r['Comune'], r['CAP'])
                    if c: r['coords'] = c; giro.append(r)
                # 3. Algoritmo Vicino più Prossimo
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
        # Mappa interattiva
        m = folium.Map(location=SEDE_COORDS, zoom_start=11)
        punti = [SEDE_COORDS] + [p['coords'] for p in st.session_state.giro_igt] + [SEDE_COORDS]
        folium.PolyLine(punti, color="#FFD700", weight=5, opacity=0.8).add_to(m)
        folium.Marker(SEDE_COORDS, popup="CASA", icon=folium.Icon(color='darkblue', icon='star')).add_to(m)
        for i, p in enumerate(st.session_state.giro_igt):
            folium.Marker(p['coords'], popup=p['Cliente'], tooltip=f"Tappa {i+1}").add_to(m)
        st_folium(m, width="100%", height=300, key="map_igt")

        st.subheader("📋 Gestione Tappe Giornaliere")
        
        for i, p in enumerate(st.session_state.giro_igt):
            with st.container():
                # Card Cliente con Comune e Telefono
                st.markdown(f"""
                <div class="tappa-card">
                    <b style="font-size: 1.1em;">{i+1}. {p['Cliente']}</b><br>
                    <span style="color: #FFD700;">Cod: {p.get('CODICE','N/D')}</span> | 📍 {p['Comune']}<br>
                    <small>🏠 {p['Indirizzo']}</small><br>
                    📞 Tel: {p['TELEFONO'] if p['TELEFONO'] != "" else "N/D"}
                </div>
                """, unsafe_allow_html=True)
                
                # Area Note Vocali
                nota_v = st.text_area("Note / Problemi / Materiali da portare:", key=f"v_{i}", placeholder="Usa il microfono del Pixel...")
                
                col1, col2, col3, col4 = st.columns([1,1,1,1])
                with col1:
                    # Navigazione Waze
                    addr_url = f"https://waze.com/ul?q={p['Indirizzo'].replace(' ','%20')}%20{p['Comune']}&navigate=yes"
                    st.link_button("🚙 VAI", addr_url)
                with col2:
                    # Chiamata Diretta
                    if p['TELEFONO']:
                        st.link_button("📞 TEL", f"tel:{p['TELEFONO']}")
                    else:
                        st.button("📞 -", disabled=True)
                with col3:
                    # Tasto Fatto (Verde)
                    if st.button("✅ FATTO", key=f"f_{i}"):
                        st.session_state.report_serale.append({
                            "cod": p.get("CODICE","N/D"), 
                            "nome": p["Cliente"], 
                            "comune": p["Comune"],
                            "nota": nota_v if nota_v else "Visita regolare"
                        })
                        st.session_state.giro_igt.pop(i)
                        parla(f"Tappa completata. Ottimo lavoro.")
                        st.rerun()
                with col4:
                    # Tasto Elimina (Rosso)
                    if st.button("❌", key=f"d_{i}"):
                        st.session_state.giro_igt.pop(i)
                        st.rerun()
            st.write("---")

    # --- REPORT SERALE AUTOMATICO ---
    if st.session_state.report_serale:
        st.divider()
        data_s = datetime.now().strftime("%d/%m/%Y")
        st.subheader(f"✉️ Report Serale del {data_s}")
        
        # Costruzione corpo mail
        corpo = f"REPORT VISITE DEL {data_s} - GIAMBATTISTA GIACCHETTI\n"
        corpo += "===============================================\n\n"
        for r in st.session_state.report_serale:
            corpo += f"• {r['nome']} (COD: {r['cod']}) - {r['comune']}\n"
            corpo += f"  NOTA: {r['nota']}\n\n"
        
        st.text_area("Anteprima Email:", corpo, height=200)
        
        # Link Email
        dest = "giambattista.giacchetti@gmail.com"
        subj = f"REPORT VISITE DEL {data_s} - GIAMBATTISTA GIACCHETTI"
        mailto_link = f"mailto:{dest}?subject={urllib.parse.quote(subj)}&body={urllib.parse.quote(corpo)}"
        
        st.link_button("📧 INVIA REPORT FINALE A GIAMBATTISTA", mailto_link, use_container_width=True)
        
        if st.button("🗑️ AZZERA SESSIONE GIORNALIERA"):
            st.session_state.report_serale = []
            st.rerun()
else:
    st.error("Connessione al file Google Sheets fallita. Verifica il link.")
