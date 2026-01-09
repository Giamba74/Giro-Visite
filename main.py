import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from datetime import datetime
import urllib.parse
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Brightstar Pro AI", page_icon="⭐", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #001a41; }
    .header-box { background-color: #00122e; padding: 15px; border-radius: 15px; border: 1px solid #FFD700; margin-bottom: 20px; border: 1px solid #FFD700; }
    .tappa-card { padding: 15px; border-radius: 12px; background-color: #00122e; border-left: 8px solid #FFD700; margin-bottom: 5px; color: white; border-bottom: 1px solid #333; }
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background: linear-gradient(135deg, #FFD700 0%, #C5A000 100%); color: #002D72 !important; font-weight: bold; border: none; }
    div.stButton > button[key^="f_"] { background: #28a745 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FUNZIONI CORE (STABILI) ---
def parla(testo):
    st.components.v1.html(f"""<script>var msg = new SpeechSynthesisUtterance('{testo}'); msg.lang = 'it-IT'; window.speechSynthesis.speak(msg);</script>""", height=0)

@st.cache_resource(show_spinner="Sincronizzazione con Google Database...")
def get_gsheet_client():
    """Connessione robusta che evita l'errore Response 200"""
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Errore inizializzazione API: {e}")
        return None

def carica_dati_fogli(client, nome_file):
    try:
        # Apre il file e carica il primo foglio
        sh = client.open(nome_file)
        ws = sh.get_worksheet(0)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        # Normalizza nomi colonne in MAIUSCOLO per evitare errori di battitura
        df.columns = [str(c).strip().upper() for c in df.columns]
        return ws, df
    except Exception as e:
        st.error(f"Impossibile leggere il file '{nome_file}': {e}")
        return None, None

def agente_meteo_decisione(tappe):
    """Agente che decide tra Zontes e Auto (Solo Lun-Ven)"""
    if datetime.now().weekday() >= 5: return None, None, None
    try:
        # Check su Firenze/Arezzo (centro zona)
        res = requests.get("https://api.open-meteo.com/v1/forecast?latitude=43.66&longitude=11.30&hourly=temperature_2m,precipitation_probability&timezone=Europe%2FRome&forecast_days=1").json()
        temp_min = res['hourly']['temperature_2m'][8] # ore 8:00
        pioggia_max = max(res['hourly']['precipitation_probability'][8:18]) # max prob giornata
        
        if temp_min < 3 or pioggia_max > 30:
            return "AUTO 🚗", f"Previsti {temp_min}°C e {pioggia_max}% pioggia. Prendi l'auto.", "#ff4b4b"
        return "ZONTES 350D 🛵", f"Meteo perfetto ({temp_min}°C). Vai di scooter!", "#28a745"
    except: return "INFO", "Meteo non disponibile", "#FFD700"

# --- 3. LOGICA APPLICATIVA ---
st.title("⭐ BRIGHTSTAR PRO NAVIGATOR")

# 1. Connessione
client = get_gsheet_client()
# MODIFICA QUI: Metti il nome esatto del tuo file Google Sheets
NOME_FILE_GS = "GiroVisite_Dati" 

if client:
    ws, df = carica_dati_fogli(client, NOME_FILE_GS)
    
    if df is not None:
        # Escludi i già visitati
        df_disponibili = df[~df['VISITATO'].astype(str).str.upper().str.contains('SI|SÌ', na=False)]

        # --- SEZIONE FILTRI ---
        with st.container():
            st.markdown("<div class='header-box'>", unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                comuni_list = sorted(df['COMUNE'].unique().tolist()) if 'COMUNE' in df.columns else []
                sel_comuni = st.multiselect("📍 Filtra per Comune:", comuni_list)
            with col2:
                forzati = st.multiselect("📌 Clienti Prioritari (Obbligatori):", sorted(df['CLIENTE'].unique().tolist()))
            
            if st.button("🚀 GENERA PIANO 10 TAPPE"):
                with st.spinner("Ottimizzazione percorso in corso..."):
                    # Selezione
                    giro = df[df['CLIENTE'].isin(forzati)].to_dict('records')
                    mask = df['CLIENTE'].isin(df_disponibili['CLIENTE']) & ~df['CLIENTE'].isin(forzati)
                    if sel_comuni: mask &= df['COMUNE'].isin(sel_comuni)
                    
                    extra = df[mask].head(10 - len(giro)).to_dict('records')
                    giro.extend(extra)
                    
                    # Geocoding veloce
                    geolocator = Nominatim(user_agent="bright_pro_nav")
                    for r in giro:
                        addr = f"{r.get('INDIRIZZO','')}, {r.get('COMUNE','')}, Italy"
                        try:
                            l = geolocator.geocode(addr, timeout=3)
                            r['coords'] = (l.latitude, l.longitude) if l else (43.66, 11.30)
                        except: r['coords'] = (43.66, 11.30)
                    
                    # Ordinamento chilometrico
                    opt = []
                    pos = (43.661888, 11.305728) # Sede Strada in Chianti
                    while giro:
                        prox = min(giro, key=lambda x: geodesic(pos, x['coords']).km)
                        opt.append(prox); pos = prox['coords']; giro.remove(prox)
                    
                    st.session_state.giro_igt = opt
                    parla(f"Giro generato con successo per {len(opt)} tappe.")
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        # --- SEZIONE TAPPE ---
        if 'giro_igt' in st.session_state and st.session_state.giro_igt:
            mezzo, sug, col_m = agente_meteo_decisione(st.session_state.giro_igt)
            if mezzo:
                st.markdown(f"<div style='border:2px solid {col_m}; padding:10px; border-radius:10px; text-align:center; color:white; margin-bottom:10px;'><b>{mezzo}</b>: {sug}</div>", unsafe_allow_html=True)

            for i, p in enumerate(st.session_state.giro_igt):
                with st.container():
                    st.markdown(f"""<div class="tappa-card"><b>{i+1}. {p['CLIENTE']}</b> (Cod: {p.get('CODICE','')})<br>📍 {p['COMUNE']} - {p['INDIRIZZO']}</div>""", unsafe_allow_html=True)
                    
                    nota = st.text_area(f"Note per {p['CLIENTE']}:", key=f"n_{i}", placeholder="Dettami eventuali problemi o materiali...")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.link_button("🚙 WAZE", f"https://waze.com/ul?q={p['INDIRIZZO'].replace(' ','%20')}%20{p['COMUNE']}&navigate=yes")
                    with c2:
                        tel = str(p.get('TELEFONO','')).replace(".0","")
                        if tel: st.link_button("📞 CHIAMA", f"tel:{tel}")
                    with c3:
                        if st.button("✅ FATTO", key=f"f_{i}"):
                            try:
                                # SCRITTURA SU GOOGLE SHEET
                                cella = ws.find(str(p['CLIENTE']))
                                headers = [h.upper() for h in ws.row_values(1)]
                                col_v = headers.index("VISITATO") + 1
                                ws.update_cell(cella.row, col_v, "SI")
                                
                                # Salva per report mail
                                if 'report_dati' not in st.session_state: st.session_state.report_dati = []
                                st.session_state.report_dati.append({"c": p['CLIENTE'], "cod": p.get('CODICE',''), "n": nota})
                                
                                st.session_state.giro_igt.pop(i)
                                parla("Tappa salvata sul database.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Errore aggiornamento: {e}")

        # --- REPORT FINALE ---
        if 'report_dati' in st.session_state and st.session_state.report_dati:
            st.divider()
            if st.button("📧 GENERA REPORT MAIL SERALE"):
                data_oggi = datetime.now().strftime("%d/%m/%Y")
                corpo = f"REPORT VISITE GIORNALIERO - {data_oggi}\n"
                corpo += "--------------------------------------\n\n"
                for r in st.session_state.report_dati:
                    corpo += f"📍 {r['c']} (Cod: {r['cod']})\nNOTE: {r['n']}\n\n"
                
                subj = f"REPORT VISITE DEL {data_oggi} - GIAMBATTISTA GIACCHETTI"
                link = f"mailto:giambattista.giacchetti@gmail.com?subject={urllib.parse.quote(subj)}&body={urllib.parse.quote(corpo)}"
                st.link_button("Invia Email a Giambattista", link)

