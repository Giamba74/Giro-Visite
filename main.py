import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium

# Configurazione Sede
SEDE_INDIRIZZO = "Via G. Ferrero 122, Strada in Chianti, FI, Italy"
SEDE_NOME = "UFFICIO"

st.set_page_config(page_title="Giro Visite Fast", layout="wide")

# Funzione con CACHE per evitare blocchi e lentezza
@st.cache_data(show_spinner=False)
def get_coords_cached(address):
    try:
        geolocator = Nominatim(user_agent="ottimizzatore_pixel9_pro_user")
        location = geolocator.geocode(address, timeout=10)
        if location:
            return (location.latitude, location.longitude)
    except:
        return None
    return None

st.title("🚀 Giro Visite Ottimizzato")

uploaded_file = st.file_uploader("Carica Excel", type=["xlsx", "xls"])

if uploaded_file:
    df_full = pd.read_excel(uploaded_file)
    
    col1, col2, col3 = st.columns(3)
    with col1: col_n = st.selectbox("Nome Cliente:", df_full.columns)
    with col2: col_a = st.selectbox("Indirizzo:", df_full.columns)
    with col3: col_cap = st.selectbox("CAP:", df_full.columns)
    
    lista_cap = sorted(df_full[col_cap].unique().astype(str))
    cap_selezionati = st.multiselect("Seleziona CAP prioritari:", lista_cap)
    
    if st.button("🚀 GENERA GIRO (10 VISITE)"):
        # 1. Coordinate Sede (fisse)
        sede_coords = (43.6558, 11.3103) # Coordinate approssimative di Strada in Chianti per velocizzare
        
        with st.status("Elaborazione geografica...", expanded=True) as status:
            st.write("🌍 Geocodifica indirizzi in corso (solo i nuovi)...")
            
            # Filtriamo subito per non geocodificare TUTTO il file se è enorme
            # Prendiamo i prioritari + un campione di altri per sicurezza
            df_prioritari = df_full[df_full[col_cap].astype(str).isin(cap_selezionati)].copy()
            df_altri = df_full[~df_full[col_cap].astype(str).isin(cap_selezionati)].sample(min(30, len(df_full))) if len(df_full) > 30 else df_full[~df_full[col_cap].astype(str).isin(cap_selezionati)].copy()
            
            df_lavoro = pd.concat([df_prioritari, df_altri]).drop_duplicates(subset=[col_a])
            
            # Geocodifica con Cache
            df_lavoro['coords'] = df_lavoro[col_a].apply(get_coords_cached)
            df_lavoro = df_lavoro.dropna(subset=['coords'])
            
            st.write("🔄 Calcolo percorso ottimale...")
            
            prioritari = df_lavoro[df_lavoro[col_cap].astype(str).isin(cap_selezionati)].to_dict('records')
            altri = df_lavoro[~df_lavoro[col_cap].astype(str).isin(cap_selezionati)].to_dict('records')
            
            percorso = []
            pos_attuale = sede_coords
            
            # Selezione 10 tappe
            while (prioritari) and len(percorso) < 10:
                prossimo = min(prioritari, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                percorso.append(prossimo)
                pos_attuale = prossimo['coords']
                prioritari.remove(prossimo)
                
            while len(percorso) < 10 and altri:
                prossimo = min(altri, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                percorso.append(prossimo)
                pos_attuale = prossimo['coords']
                altri.remove(prossimo)
            
            status.update(label="Completato!", state="complete", expanded=False)

        # Visualizzazione Risultati
        if percorso:
            tappe = [{"T": "PARTENZA", "L": SEDE_NOME, "A": SEDE_INDIRIZZO, "c": sede_coords}]
            for i, p in enumerate(percorso):
                tappe.append({"T": i+1, "L": p[col_n], "A": p[col_a], "c": p['coords']})
            tappe.append({"T": "RITORNO", "L": SEDE_NOME, "A": SEDE_INDIRIZZO, "c": sede_coords})

            # Mappa
            m = folium.Map(location=sede_coords, zoom_start=11)
            folium.PolyLine([t['c'] for t in tappe], color="blue", weight=3).add_to(m)
            for t in tappe:
                folium.Marker(t['c'], popup=str(t['L'])).add_to(m)
            st_folium(m, width="100%", height=400)

            # Elenco per Smartphone
            for t in tappe:
                with st.expander(f"📍 {t['T']} - {t['L']}", expanded=True):
                    c1, c2 = st.columns([3, 1])
                    c1.write(t['A'])
                    url = f"https://www.google.com/maps/dir/?api=1&destination={t['c'][0]},{t['c'][1]}"
                    c2.link_button("🧭 NAVIGA", url)
