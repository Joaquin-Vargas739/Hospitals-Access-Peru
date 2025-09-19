import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(page_title="Hospitals in Peru", layout="wide")

# Cargar datos con rutas relativas
# -----------------------------
@st.cache_data
def load_data():
    hospitals = pd.read_csv("IPRESS.csv", encoding="latin1")  # ajustar si da error
    districts = gpd.read_file("shape_file/DISTRITOS.shp").to_crs(epsg=4326)
    pop_centers = gpd.read_file("CCPP_0/CCPP_IGN100K.shp").to_crs(epsg=4326)
    return hospitals, districts, pop_centers

hospitals, districts, pop_centers = load_data()

districts = districts[districts.geometry.notnull()].copy()

# -----------------------------
# Normalizar nombres de columnas
# -----------------------------
hospitals.columns = hospitals.columns.str.strip().str.upper().str.replace(" ", "_")
pop_centers.columns = pop_centers.columns.str.strip().str.upper().str.replace(" ", "_")
districts.columns = districts.columns.str.strip().str.upper().str.replace(" ", "_")

# Identificar columna del nombre del hospital (cualquiera que contenga "ESTABLECIMIENTO")
hospital_name_col = [c for c in hospitals.columns if "ESTABLECIMIENTO" in c][0]

# -----------------------------
# Filtrar hospitales operativos y crear GeoDataFrame
# -----------------------------
hospitals_operational = hospitals[hospitals['CONDICIÓN'] == "EN FUNCIONAMIENTO"].copy()

# Asegurar coordenadas numéricas
hospitals_operational['NORTE'] = pd.to_numeric(hospitals_operational['NORTE'], errors='coerce')
hospitals_operational['ESTE'] = pd.to_numeric(hospitals_operational['ESTE'], errors='coerce')
hospitals_operational = hospitals_operational.dropna(subset=['NORTE','ESTE'])

# Filtro por clasificación e institución
if "CLASIFICACIÓN" in hospitals_operational.columns and "INSTITUCIÓN" in hospitals_operational.columns:
    hospitals_operational = hospitals_operational[
        ((hospitals_operational['CLASIFICACIÓN'] == "HOSPITALES O CLINICAS DE ATENCION GENERAL") |
         (hospitals_operational['CLASIFICACIÓN'] == "HOSPITALES O CLINICAS DE ATENCION ESPECIALIZADA") |
         (hospitals_operational['CLASIFICACIÓN'] == "INSTITUTOS DE SALUD ESPECIALIZADOS")) &
        (hospitals_operational['INSTITUCIÓN'] != "PRIVADO")
    ].copy()

# Convertir a GeoDataFrame
geometry = gpd.points_from_xy(hospitals_operational['ESTE'], hospitals_operational['NORTE'])
hospitals_gdf = gpd.GeoDataFrame(hospitals_operational, geometry=geometry, crs="EPSG:4326")

# Tabs de la app

tabs = st.tabs([
    "🗂️ Data Description", 
    "🗺️ Static Maps & Department Analysis", 
    "🌍 Dynamic Maps"
])

# TAB 1: Data Description

with tabs[0]:
    st.header("📊 Data Description")
    st.write("Unit of analysis: Operational public hospitals in Peru")
    st.write("Data sources: MINSA – IPRESS (operational subset), Population Centers")
    st.write("Filtering rules: Only operational hospitals with valid lat/long")
    st.write("Number of operational hospitals:", len(hospitals_gdf))

    cols_to_show = [c for c in ["INSTITUCIÓN", hospital_name_col, "DEPARTAMENTO", "PROVINCIA", "DISTRITO"] if c in hospitals_gdf.columns]
    st.dataframe(hospitals_gdf[cols_to_show].head())

# ---------------------------------
# TAB 2: Static Maps & Analysis
# ---------------------------------
with tabs[1]:
    st.header("🗺️ Static Maps & Department Analysis")

    # Copiar distritos
    districts_copy = districts.copy()

    # Calcular conteo de hospitales por distrito
    hosp_count = hospitals_gdf.groupby("DISTRITO").size().reset_index(name="N_HOSPITALS")

    # Merge conservando geometría
    if "geometry" in districts_copy.columns:
        geom_col = "geometry"
    elif "GEOMETRY" in districts_copy.columns:
        geom_col = "GEOMETRY"
    else:
        st.error("❌ No geometry column found in districts shapefile")
        st.stop()

    districts_copy = districts_copy.merge(hosp_count, on="DISTRITO", how="left")
    districts_copy["N_HOSPITALS"] = districts_copy["N_HOSPITALS"].fillna(0)

    districts_copy = gpd.GeoDataFrame(districts_copy, geometry=geom_col, crs="EPSG:4326")

    # --- Choropleth ---
    fig, ax = plt.subplots(1,1, figsize=(10,10))
    districts_copy.plot(column="N_HOSPITALS", cmap="OrRd", legend=True, ax=ax)
    ax.set_title("Total Operational Hospitals per District")
    ax.axis("off")
    st.pyplot(fig)

    # --- Distritos con 0 hospitales ---
    zero_hosp = districts_copy[districts_copy["N_HOSPITALS"] == 0]
    st.subheader("Districts with 0 Hospitals")
    st.dataframe(zero_hosp[["DEPARTAMEN","PROVINCIA","DISTRITO"]].head(10))

    # --- Tabla de departamentos ---
    dept_summary = districts_copy.dissolve(by="DEPARTAMEN", aggfunc="sum")
    dept_summary = dept_summary.sort_values("N_HOSPITALS", ascending=False)

    st.subheader("Department Summary Table")
    st.dataframe(dept_summary[["N_HOSPITALS"]])

    # --- Top 10 distritos ---
    top10 = districts_copy.sort_values("N_HOSPITALS", ascending=False).head(10)
    st.subheader("Top 10 Districts with Most Hospitals")
    st.dataframe(top10[["DEPARTAMEN","PROVINCIA","DISTRITO","N_HOSPITALS"]])

    # --- Gráfico de barras ---
    fig2, ax2 = plt.subplots(figsize=(12,6))
    sns.barplot(x=dept_summary.index, y=dept_summary["N_HOSPITALS"], palette="viridis", ax=ax2)
    plt.xticks(rotation=45)
    plt.ylabel("Number of Hospitals")
    plt.xlabel("Department")
    plt.title("Operational Hospitals per Department")
    st.pyplot(fig2)

# ---------------------------------
# TAB 3: Dynamic Maps
# ---------------------------------
with tabs[2]:
    st.header("🌍 Dynamic Maps")

    # --- Mapa nacional con choropleth y marcadores ---
    st.subheader("National Choropleth + Hospital Markers")
    m = folium.Map(location=[-9.2, -75], zoom_start=5)

    folium.Choropleth(
        geo_data=districts_copy,
        data=districts_copy,
        columns=["DISTRITO","N_HOSPITALS"],
        key_on="feature.properties.DISTRITO",
        fill_color="OrRd",
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name="Number of Hospitals"
    ).add_to(m)

    for idx, row in hospitals_gdf.iterrows():
        folium.Marker(
            location=[row.geometry.y, row.geometry.x],
            popup=str(row[hospital_name_col]),
            icon=folium.Icon(color="blue", icon="plus")
        ).add_to(m)

    st_folium(m, width=700, height=500)

   