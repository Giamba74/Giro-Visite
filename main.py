import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
import io

SEDE_INDIRIZZO = "Via G. Ferrero 122, Strada in Chianti, FI, Italy"
SEDE_NOME = "UFFICIO"

st.set_page_config(page_title="Giro Visite Intelligente", layout="wide")

st.title("🚚 Ottimizzatore Giro Visite Dinamico")

def get_coords(address):
    try:
        geolocator = Nominatim(user_agent="ottimizzatore_smart_chianti")
        location = geolocator.geocode(address, timeout=10)
        return (location.latitude, location.longitude) if location else None
    except: return None

uploaded_file = st.file_uploader("Carica Portafoglio Clienti", type=["xlsx", "xls", "csv"])

if uploaded_file:
    df_full = pd.read_excel(uploaded_file)
    
    c1, c2, c3 = st.columns(3)
    with c1: col_n = st.selectbox("Nome Cliente:", df_full.columns)
    with c2: col_a = st.selectbox("Indirizzo:", df_full.columns)
    with c3: col_cap = st.selectbox("Colonna CAP:", df_full.columns)
    
    lista_cap = sorted(df_full[col_cap].unique().astype(str))
    cap_selezionati = st.multiselect("Seleziona CAP prioritari:", lista_cap)
    
    if st.button("🚀 GENERA GIRO (10 VISITE)"):
        with st.spinner('Geolocalizzazione e calcolo vicinanza...'):
            sede_coords = get_coords(SEDE_INDIRIZZO)
            
            # 1. Geocodifica tutto il portafoglio (solo la prima volta è lento)
            df_full['coords'] = df_full[col_a].apply(get_coords)
            df_full = df_full.dropna(subset=['coords'])
            
            # 2. Dividiamo in prioritari (CAP scelti) e potenziali (altri)
            prioritari = df_full[df_full[col_cap].astype(str).isin(cap_selezionati)].to_dict('records')
            altri = df_full[~df_full[col_cap].astype(str).isin(cap_selezionati)].to_dict('records')
            
            percorso = []
            pos_attuale = sede_coords
            
            # 3. Prendiamo prima i prioritari (più vicini alla posizione attuale man mano)
            while prioritari and len(percorso) < 10:
                prossimo = min(prioritari, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                percorso.append(prossimo)
                pos_attuale = prossimo['coords']
                prioritari.remove(prossimo)
            
            # 4. Se mancano tappe, peschiamo dagli "altri" più vicini all'ultima tappa
            while len(percorso) < 10 and altri:
                prossimo = min(altri, key=lambda x: geodesic(pos_attuale, x['coords']).km)
                percorso.append(prossimo)
                pos_attuale = prossimo['coords']
                altri.remove(prossimo)
            
            # 5. Costruzione giro finale
            tappe = [{"T": "START", "L": SEDE_NOME, "A": SEDE_INDIRIZZO, "c": sede_coords}]
            for i, p in enumerate(percorso):
                tappe.append({"T": i+1, "L": p[col_n], "A": p[col_a], "c": p['coords']})
            tappe.append({"T": "HOME", "L": SEDE_NOME, "A": SEDE_INDIRIZZO, "c": sede_coords})
            
            # --- Visualizzazione ---
            m = folium.Map(location=sede_coords, zoom_start=11)
            folium.PolyLine([t['c'] for t in tappe], color="#2C3E50", weight=4, opacity=0.7).add_to(m)
            
            for t in tappe:
                is_sede = t['L'] == SEDE_NOME
                folium.Marker(t['c'], 
                              popup=f"{t['T']}: {t['L']}", 
                              icon=folium.Icon(color='red' if is_sede else 'blue', icon='play' if is_sede else 'user')).add_to(m)
            
            st_folium(m, width="100%", height=400)
            
            st.subheader("Tabella di Marcia")
            for t in tappe:
                with st.expander(f"📍 Tappa {t['T']}: {t['L']}", expanded=True):
                    col_info, col_nav = st.columns([3, 1])
                    col_info.write(f"{t['A']}")
                    url = f"https://www.google.com/maps/dir/?api=1&destination={t['c'][0]},{t['c'][1]}"
                    col_nav.link_button("🧭 NAVIGA", url)

