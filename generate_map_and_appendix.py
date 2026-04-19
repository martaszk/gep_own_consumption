"""
Script to generate:
1. A choropleth map of 2019 GEP values by country
2. Data for appendix table with all countries (first year, last year, % change)
"""

import csv
import os
import json
from collections import defaultdict

os.chdir(r'e:\GEP\gep_own_consumption')

# Extract all temporal data for appendix
print("=" * 80)
print("EXTRACTING COUNTRY DATA FOR APPENDIX")
print("=" * 80)

data_by_country = defaultdict(lambda: {'years': [], 'iso3': None})

with open('output/data-gep-agriculture-subsistence.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        country = row['Country']
        year = int(row['Year'])
        gep_value = float(row['own_con2']) if row['own_con2'] else None
        iso3 = row['alpha-3']
        
        if iso3:
            data_by_country[country]['iso3'] = iso3
        
        if gep_value is not None and gep_value > 0:
            data_by_country[country]['years'].append((year, gep_value))

# Sort and process for appendix
appendix_data = []
for country in sorted(data_by_country.keys()):
    data = data_by_country[country]
    years_sorted = sorted(data['years'], key=lambda x: x[0])
    
    if len(years_sorted) >= 1:
        first_year, first_gep = years_sorted[0]
        last_year, last_gep = years_sorted[-1]
        
        if first_gep > 0:
            pct_change = ((last_gep - first_gep) / first_gep) * 100
        else:
            pct_change = 0
        
        appendix_data.append({
            'country': country,
            'iso3': data['iso3'],
            'first_year': first_year,
            'first_gep': first_gep,
            'last_year': last_year,
            'last_gep': last_gep,
            'pct_change': pct_change
        })

print(f"\nTotal countries with subsistence GEP data: {len(appendix_data)}")

# Save as JSON for map visualization
map_data_2019 = {}
for country, data in data_by_country.items():
    for year, gep in data['years']:
        if year == 2019:
            iso3 = data['iso3'] or 'UNKNOWN'
            map_data_2019[iso3] = {
                'country': country,
                'gep_2019': gep
            }

with open('output/gep_2019_map_data.json', 'w') as f:
    json.dump(map_data_2019, f, indent=2)

print(f"Countries with 2019 data for map: {len(map_data_2019)}")
print(f"Map data saved to: output/gep_2019_map_data.json")

# Output appendix table in markdown format
print("\n" + "=" * 80)
print("APPENDIX TABLE - All Countries Subsistence GEP (Alphabetical Order)")
print("=" * 80)
print("\n| Country | First Year | First GEP (2019 USD) | Last Year | Last GEP (2019 USD) | Percent Change |")
print("|---|---:|---:|---:|---:|---:|")

for item in appendix_data:
    print(f"| {item['country']} | {item['first_year']} | {item['first_gep']:,.0f} | {item['last_year']} | {item['last_gep']:,.0f} | {item['pct_change']:+.2f}% |")

print(f"\n\nTotal countries in appendix: {len(appendix_data)}")

# Also output 2019 GEP ranking for reference
print("\n" + "=" * 80)
print("2019 GEP LEVELS BY COUNTRY (For Map Reference)")
print("=" * 80 + "\n")

sorted_2019 = sorted(
    [(item['country'], item['first_gep'] if item['first_year'] <= 2019 <= item['last_year'] 
      else next((g for y, g in data_by_country[item['country']]['years'] if y == 2019), 0))
     for item in appendix_data],
    key=lambda x: x[1],
    reverse=True
)

for i, (country, gep) in enumerate(sorted_2019, 1):
    print(f"{i:2d}. {country:40s}: USD {gep:>15,.0f}")
