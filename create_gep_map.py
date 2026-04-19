"""
Create a choropleth map of 2019 GEP levels by country
"""

import json
import sys

try:
    import geopandas as gpd
    import folium
    from folium import plugins
    import pandas as pd
except ImportError:
    print("geopandas or folium not found. Attempting to install...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "geopandas", "folium"])
    import geopandas as gpd
    import folium
    from folium import plugins
    import pandas as pd

import os
os.chdir(r'e:\GEP\gep_own_consumption')

# Load 2019 GEP data
with open('output/gep_2019_map_data.json', 'r') as f:
    gep_data = json.load(f)

# Create a dataframe from the data
df_data = []
for iso3, info in gep_data.items():
    df_data.append({
        'iso_a3': iso3,
        'country': info['country'],
        'gep_2019': info['gep_2019']
    })

df_gep = pd.DataFrame(df_data)

print("Loaded GEP data for countries:", len(df_gep))
print("\nTop 10 by 2019 GEP:")
print(df_gep.nlargest(10, 'gep_2019')[['country', 'gep_2019']])

# Load world geodata
try:
    world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
except:
    print("Downloading world map data...")
    world = gpd.read_file('https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip')

# Merge GEP data with world map
world_merged = world.merge(df_gep, left_on='iso_a3', right_on='iso_a3', how='left')

# Create a folium map centered on Africa
map_center = [0, 20]
m = folium.Map(
    location=map_center,
    zoom_start=3,
    tiles='OpenStreetMap'
)

# Add choropleth
# Prepare data for choropleth
choropleth_data = {}
for idx, row in world_merged.iterrows():
    if pd.notna(row['gep_2019']):
        choropleth_data[row['iso_a3']] = row['gep_2019']

# Create the choropleth layer
folium.Choropleth(
    geo_data=world.__geo_interface__,
    name='2019 Subsistence GEP (USD)',
    data=df_gep,
    columns=['iso_a3', 'gep_2019'],
    key_on='feature.properties.iso_a3',
    fill_color='YlGn',
    fill_opacity=0.7,
    line_opacity=0.2,
    legend_name='Subsistence GEP Value (2019 USD)',
    nan_fill_color='white'
).add_to(m)

# Add country labels and popups
for idx, row in world_merged.iterrows():
    if pd.notna(row['gep_2019']):
        folium.CircleMarker(
            location=[row.geometry.centroid.y, row.geometry.centroid.x],
            radius=max(3, min(15, row['gep_2019'] / 500000000)),
            popup=f"{row['country']}<br>GEP 2019: USD {row['gep_2019']:,.0f}",
            tooltip=f"{row['country']}: ${row['gep_2019']/1e9:.2f}B",
            color='darkgreen',
            fill=True,
            fillColor='green',
            fillOpacity=0.4
        ).add_to(m)

# Save map
map_file = 'output/gep_2019_map.html'
m.save(map_file)
print(f"\nMap saved to: {map_file}")
print("Open this HTML file in a web browser to view the interactive map")
