"""
Create a static PNG map visualization of 2019 GEP levels by country
Uses country coordinates to create a scatter plot on a world map background
"""

import pandas as pd
import os
import sys

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import Rectangle
    import numpy as np
except ImportError:
    print("Installing matplotlib...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "matplotlib", "numpy"])
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import Rectangle
    import numpy as np

os.chdir(r'e:\GEP\gep_own_consumption')

# Load 2019 average GEP data
df_avg = pd.read_csv('results/gep-average-by-country.csv')

# Country coordinates (approximate center points)
country_coords = {
    'India': (20, 78),
    'China': (35, 105),
    'Nigeria': (9, 8),
    'Kazakhstan': (48, 68),
    'Sudan': (15, 30),
    'Indonesia': (-2, 113),
    'Ukraine': (49, 32),
    'Pakistan': (30, 69),
    'Ethiopia': (9, 40),
    'Brazil': (-10, -55),
    'Thailand': (15, 100),
    'Viet Nam': (16, 106),
    'Belarus': (54, 28),
    'Myanmar': (22, 98),
    'United Republic of Tanzania': (-6, 35),
    'Algeria': (28, 2),
    'Bangladesh': (24, 90),
    'South Sudan': (6, 31),
    'Niger': (17, 8),
    'Morocco': (32, -6),
    'Ghana': (7.5, -2),
    'Philippines': (12, 122),
    'Uganda': (1, 32),
    'Romania': (46, 25),
    'Kenya': (-1, 37),
    'Côte d\'Ivoire': (7, -5),
    'Syrian Arab Republic': (35, 38),
    'Angola': (-11, 17),
    'Malawi': (-13.5, 34.3),
    'Cameroon': (4, 12),
    'Tunisia': (34, 9),
    'Mozambique': (-18, 35),
    'Afghanistan': (33, 67),
    'Guinea': (10, -10),
    'Iraq': (33, 44),
    'Burkina Faso': (12, -1.5),
    'Mali': (17, -4),
    'Uzbekistan': (41, 64),
    'Chad': (15, 19),
    'Cambodia': (13, 105),
    'Madagascar': (-19, 47),
    'Zambia': (-13, 28),
    'Bulgaria': (43, 25),
    'Cuba': (21.5, -77.5),
    'Senegal': (14.5, -14),
    'Benin': (9.5, 2),
    'Peru': (-12, -75),
    'Nepal': (28, 84),
    'Bolivia (Plurinational State of)': (-17, -63),
    'Paraguay': (-23, -56),
    'Colombia': (4, -74),
    'Togo': (7, 1),
    'Guatemala': (15, -90),
    'Sierra Leone': (8.5, -11.5),
    'Ecuador': (-1, -77.5),
    'Sri Lanka': (7, 81),
    'Central African Republic': (7, 21),
    'Albania': (41, 20),
    'Mongolia': (46, 103),
    'Nicaragua': (12, -86),
    'Georgia': (42, 43.5),
    'Armenia': (40, 45),
    'Kyrgyzstan': (42, 77),
    'Bosnia and Herzegovina': (44, 18),
    'Azerbaijan': (40, 47),
    'Eswatini': (-26, 31),
    'Eritrea': (15, 39),
    'El Salvador': (13.5, -89),
    'Dominican Republic': (19, -70),
}

# Create figure
fig, ax = plt.subplots(figsize=(24, 14), dpi=150)

# Set map background
ax.set_facecolor('#e6f2ff')  # Light blue background
ax.set_xlim(-180, 180)
ax.set_ylim(-90, 90)

# Add grid
ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)

# Add continent backgrounds (light gray rectangles)
# These are approximate continent bounds
continents = [
    # North America
    Rectangle((-170, 15), 100, 75, facecolor='#f0f0f0', edgecolor='none', alpha=0.3, zorder=0),
    # South America
    Rectangle((-85, -55), 55, 75, facecolor='#f0f0f0', edgecolor='none', alpha=0.3, zorder=0),
    # Europe
    Rectangle((-15, 35), 50, 35, facecolor='#f0f0f0', edgecolor='none', alpha=0.3, zorder=0),
    # Africa
    Rectangle((-20, -35), 55, 70, facecolor='#f0f0f0', edgecolor='none', alpha=0.3, zorder=0),
    # Asia
    Rectangle((40, 0), 140, 80, facecolor='#f0f0f0', edgecolor='none', alpha=0.3, zorder=0),
]

for continent in continents:
    ax.add_patch(continent)

# Get GEP values and create color mapping
gep_values = df_avg['avg_gep_2019usd'].values
gep_log = np.log10(gep_values + 1)
gep_norm = (gep_log - gep_log.min()) / (gep_log.max() - gep_log.min())

# Color map
cmap = plt.cm.YlGn  # Yellow to Green
colors_list = cmap(gep_norm)

# Plot each country
sizes_list = []
for idx, row in df_avg.iterrows():
    country = row['Country']
    gep = row['avg_gep_2019usd']
    
    if country in country_coords:
        lat, lon = country_coords[country]
        
        # Size based on GEP value
        size = 50 + (gep / gep_values.max()) * 500
        sizes_list.append(size)
        
        # Color based on normalized GEP
        color = colors_list[idx]
        
        # Plot point
        ax.scatter(lon, lat, s=size, c=[color], edgecolors='black', linewidth=1, 
                  alpha=0.7, zorder=5, marker='o')
        
        # Add country label for top 15
        if idx < 15:
            ax.text(lon, lat-3, country, fontsize=7, ha='center', fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7, edgecolor='none'))

# Add title
plt.title('Global Subsistence-Crop Gross Ecosystem Product by Country (2019)\nValue in 2019 USD', 
         fontsize=18, fontweight='bold', pad=20)

# Add legend
legend_elements = [
    mpatches.Patch(facecolor='#ffffcc', edgecolor='black', label='Low GEP (<$10M)'),
    mpatches.Patch(facecolor='#c2e699', edgecolor='black', label='Medium GEP ($10M-$100M)'),
    mpatches.Patch(facecolor='#78c679', edgecolor='black', label='High GEP ($100M-$1B)'),
    mpatches.Patch(facecolor='#238b45', edgecolor='black', label='Very High GEP (>$1B)'),
]
ax.legend(handles=legend_elements, loc='lower left', fontsize=11, framealpha=0.95)

# Add labels
ax.set_xlabel('Longitude', fontsize=12, fontweight='bold')
ax.set_ylabel('Latitude', fontsize=12, fontweight='bold')

# Add note
fig.text(0.5, 0.02, f'Map displays {len(df_avg)} countries with 2019 GEP observations. Circle size and color intensity represent GEP magnitude.',
        ha='center', fontsize=10, style='italic')

# Adjust layout
plt.tight_layout(rect=[0, 0.03, 1, 0.97])

# Save PNG
output_file = 'output/gep_2019_map.png'
plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
print(f"PNG map saved to: {output_file}")

# Get file size
file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
print(f"File size: {file_size_mb:.2f} MB")
print(f"Map includes {len(df_avg)} countries")

plt.close()
