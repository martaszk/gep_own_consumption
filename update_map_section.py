"""
Update the map section in report.qmd to reference PNG instead of HTML
"""

import re

file_path = r'e:\GEP\gep_own_consumption\report\report.qmd'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the map section
old_map_section = """### 2019 Global GEP Choropleth Map

Figure 4 presents an interactive choropleth map displaying 2019 subsistence-crop GEP levels across all countries in the dataset (see supplementary materials: `output/gep_2019_map.html`). The map uses circle markers scaled by value, with color gradients indicating relative magnitude of ecosystem service contributions to subsistence agriculture. Countries with darker green shading indicate larger GEP values, while orange and red indicate smaller values. The interactive map allows users to zoom, pan, and hover over countries to view exact 2019 GEP values. This visualization reveals geographic clustering of subsistence GEP in sub-Saharan Africa and South Asia, reflecting both the concentration of smallholder subsistence farming in these regions and the extent of ecosystem dependence for agricultural provisioning.

**Figure 4. Interactive Global Subsistence-Crop GEP Map (2019)**

*Note: An interactive HTML version of this map is available in the supplementary materials folder (output/gep_2019_map.html). The map displays 16 countries with available subsistence GEP data, with circle size and color intensity representing GEP magnitude.*"""

new_map_section = """### 2019 Global GEP Choropleth Map

Figure 4 presents a choropleth map displaying 2019 subsistence-crop GEP levels across all 97 countries in the dataset. The map uses circle markers sized according to GEP value, with color gradients (yellow to dark green) indicating relative magnitude of ecosystem service contributions to subsistence agriculture. Larger, darker green circles represent countries with higher GEP values, while smaller, lighter yellow circles represent countries with lower values. This visualization reveals geographic clustering of subsistence GEP in sub-Saharan Africa and South Asia, reflecting both the concentration of smallholder subsistence farming in these regions and the extent of ecosystem dependence for agricultural provisioning.

![](../output/gep_2019_map.png)

**Figure 4. Global Subsistence-Crop GEP by Country (2019, 2019 USD)**"""

if old_map_section in content:
    content = content.replace(old_map_section, new_map_section)
    print("✓ Map section updated successfully")
else:
    print("✗ Old map section not found - trying alternative...")
    # Try a more flexible search
    pattern = r"### 2019 Global GEP Choropleth Map\s+Figure 4 presents an interactive choropleth map.*?\*\*Figure 4\. Interactive.*?\*\*\s+\*Note:.*?\*"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.start()] + new_map_section + content[match.end():]
        print("✓ Map section updated using regex pattern")
    else:
        print("✗ Could not find map section to update")

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\nFile updated: {file_path}")
