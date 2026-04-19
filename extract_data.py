import csv
from collections import defaultdict

# Read the CSV and extract data
data_by_country = defaultdict(lambda: {'years': []})

with open('output/data-gep-agriculture-subsistence.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        country = row['Country']
        year = int(row['Year'])
        gep_value = float(row['own_con2']) if row['own_con2'] else None
        iso3 = row['alpha-3']
        
        if country not in data_by_country:
            data_by_country[country] = {'years': [], 'iso3': iso3}
        
        if gep_value is not None:
            data_by_country[country]['years'].append((year, gep_value))

# Extract 2019 data for the map
gep_2019 = {}
for country, data in data_by_country.items():
    for year, gep in data['years']:
        if year == 2019:
            gep_2019[country] = gep
            break

print("=== 2019 GEP DATA FOR MAP ===")
print(f"Total countries with 2019 data: {len(gep_2019)}")
print("\nTop 15 countries by 2019 GEP:")
for i, (country, gep) in enumerate(sorted(gep_2019.items(), key=lambda x: x[1], reverse=True)[:15], 1):
    print(f"{i:2d}. {country:30s}: USD {gep:>15,.0f}")

# Generate appendix data
print("\n\n=== APPENDIX TABLE DATA ===\n")
print("| Country | First Year | First GEP (2019 USD) | Last Year | Last GEP (2019 USD) | Percent Change |")
print("|---|---:|---:|---:|---:|---:|")

appendix_data = []
for country in sorted(data_by_country.keys()):
    data = data_by_country[country]
    years_sorted = sorted(data['years'], key=lambda x: x[0])
    
    if len(years_sorted) > 0:
        first_year, first_gep = years_sorted[0]
        last_year, last_gep = years_sorted[-1]
        
        if first_gep > 0:
            pct_change = ((last_gep - first_gep) / first_gep) * 100
        else:
            pct_change = 0
        
        appendix_data.append({
            'country': country,
            'first_year': first_year,
            'first_gep': first_gep,
            'last_year': last_year,
            'last_gep': last_gep,
            'pct_change': pct_change
        })
        
        print(f"| {country} | {first_year} | {first_gep:,.0f} | {last_year} | {last_gep:,.0f} | {pct_change:.2f}% |")

print(f"\n\nTotal countries in appendix: {len(appendix_data)}")
