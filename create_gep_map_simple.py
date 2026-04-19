"""
Create a choropleth map of 2019 GEP levels using folium
Simpler version without geopandas
"""

import json
import os
import sys

# Try to import folium, install if needed
try:
    import folium
    from folium import plugins
except ImportError:
    print("Installing folium...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "folium"])
    import folium
    from folium import plugins

os.chdir(r'e:\GEP\gep_own_consumption')

# Load 2019 GEP data
with open('output/gep_2019_map_data.json', 'r') as f:
    gep_data = json.load(f)

# ISO code to approximate coordinates (major countries)
country_coords = {
    'IND': (20, 78, 'India'),
    'NGA': (9, 8, 'Nigeria'),
    'TZA': (-6, 35, 'Tanzania'),
    'GHA': (7.5, -2, 'Ghana'),
    'MWI': (-13.5, 34.3, 'Malawi'),
    'BFA': (12, -1.5, 'Burkina Faso'),
    'NER': (17, 8, 'Niger'),
    'CIV': (7, -5, 'Côte d\'Ivoire'),
    'SEN': (14.5, -14, 'Senegal'),
    'MLI': (17, -4, 'Mali'),
    'SLE': (8.5, -11.5, 'Sierra Leone'),
    'MNG': (46, 103, 'Mongolia'),
    'IRQ': (33, 44, 'Iraq'),
    'PER': (-12, -75, 'Peru'),
    'ECU': (-1, -77.5, 'Ecuador'),
    'ARM': (40, 45, 'Armenia'),
}

# Get value ranges for color scaling
values = [v['gep_2019'] for v in gep_data.values()]
max_val = max(values)
min_val = min(values)

print(f"GEP 2019 Value Range:")
print(f"  Min: USD {min_val:,.0f}")
print(f"  Max: USD {max_val:,.0f}")
print(f"  Countries with 2019 data: {len(gep_data)}")

# Create base map centered on Africa
m = folium.Map(
    location=[0, 20],
    zoom_start=4,
    tiles='OpenStreetMap'
)

# Add title
title_html = '''
             <div style="position: fixed; 
                     top: 10px; left: 50px; width: 400px; height: 80px; 
                     background-color: white; border:2px solid grey; z-index:9999; 
                     font-size:16px; font-weight: bold;
                     padding: 10px">
             <b>Global Subsistence-Crop GEP (2019)</b><br>
             All values in 2019 USD<br>
             <i>Data covers 16 countries with available subsistence agriculture data</i>
             </div>
             '''
m.get_root().html.add_child(folium.Element(title_html))

# Add country markers
for iso3, info in sorted(gep_data.items()):
    if iso3 in country_coords:
        lat, lon, country_name = country_coords[iso3]
        gep_val = info['gep_2019']
        
        # Color based on value
        if gep_val > max_val * 0.5:
            color = 'darkgreen'
        elif gep_val > max_val * 0.2:
            color = 'green'
        elif gep_val > max_val * 0.05:
            color = 'orange'
        else:
            color = 'red'
        
        # Size based on value
        radius = 5 + (gep_val / max_val) * 20
        
        folium.CircleMarker(
            location=[lat, lon],
            radius=radius,
            popup=f"<b>{country_name}</b><br>2019 Subsistence GEP<br>USD {gep_val:,.0f}",
            tooltip=f"{country_name}: ${gep_val/1e6:.1f}M",
            color=color,
            fill=True,
            fillColor=color,
            fillOpacity=0.6,
            weight=2
        ).add_to(m)

# Add legend
legend_html = '''
     <div style="position: fixed; 
                     bottom: 50px; right: 50px; width: 250px; height: auto;
                     background-color: white; border:2px solid grey; z-index:9999; 
                     font-size:12px; padding: 10px">
     <p style="margin: 0 0 10px 0; font-weight: bold;">2019 GEP Value Ranges</p>
     <p><i class="fa fa-circle" style="color:darkgreen"></i> > 50M USD</p>
     <p><i class="fa fa-circle" style="color:green"></i> 10-50M USD</p>
     <p><i class="fa fa-circle" style="color:orange"></i> 1-10M USD</p>
     <p><i class="fa fa-circle" style="color:red"></i> < 1M USD</p>
     <p style="margin-top: 10px; font-size: 11px; color: gray;">Circle size represents relative value</p>
     </div>
     '''
m.get_root().html.add_child(folium.Element(legend_html))

# Save map
map_file = 'output/gep_2019_map.html'
m.save(map_file)
print(f"\nInteractive map saved to: output/gep_2019_map.html")
print("You can open this file in a web browser to view the map")

# Also save as static image if we can
try:
    print("\nAttempting to generate static PNG version...")
    import subprocess
    # This requires selenium and geckodriver/chromedriver - skip for now
    print("(Static image generation requires additional dependencies)")
except:
    pass
