import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import io

# Configurazione Fissa
SEDE_INDIRIZZO = "Via G. Ferrero 122, Strada in Chianti, FI, Italy"
SEDE_NOME = "UFFICIO"

st.set_page_config(page_title="Giro Visite Pro", layout="wide")

st.title("🚚 Ottimizzatore Giro Visite")

def get_coords(address):
    try:
        geolocator = Nominatim(user_agent="my_chianti_app_2024")
        location = geolocator.geocode(address, timeout=10)
        return (location.latitude, location.longitude) if location else None
    except: return None

uploaded_file = st.file_uploader("Carica Excel", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    col_n = st.selectbox("Colonna Nome:", df.columns)
    col_a = st.selectbox("Colonna Indirizzo:", df.columns)
    
    if st.button("CALCOLA PERCORSO"):
        with st.spinner('Elaborazione...'):
            sede_coords = get_coords(SEDE_INDIRIZZO)
            df['coords'] = df[col_a].apply(get_coords)
            df = df.dropna(subset=['coords'])
            
            punti = df.to_dict('records')
            percorso = []
            pos_attuale = sede_coords
            
            while punti:
                prossimo = min(punti, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                percorso.append(prossimo)
                pos_attuale = prossimo['coords']
                punti.remove(prossimo)
            
            # Creazione Lista Tappe
            tappe = [{"Tappa": "PARTENZA", "Nome": SEDE_NOME, "Indirizzo": SEDE_INDIRIZZO, "coords": sede_coords}]
            for i, p in enumerate(percorso):
                tappe.append({"Tappa": i+1, "Nome": p[col_n], "Indirizzo": p[col_a], "coords": p['coords']})
            tappe.append({"Tappa": "RITORNO", "Nome": SEDE_NOME, "Indirizzo": SEDE_INDIRIZZO, "coords": sede_coords})
            
            # Visualizzazione per Mobile
            for t in tappe:
                with st.container():
                    c1, c2 = st.columns([3, 1])
                    c1.markdown(f"**{t['Tappa']}: {t['Nome']}**\n{t['Indirizzo']}")
                    # Tasto Navigatore per Android
                    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={t['coords'][0]},{t['coords'][1]}"
                    c2.link_button("🧭 VIA", maps_url)
                    st.divider()
