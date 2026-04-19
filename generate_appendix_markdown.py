import pandas as pd

# Read the generated appendix table
df = pd.read_csv('output/table_03_appendix_all_countries.csv')

# Format for Markdown table
lines = []
lines.append('| Country | First Year | First GEP (2019 USD) | Last Year | Last GEP (2019 USD) | Percent Change |')
lines.append('|---|---:|---:|---:|---:|---:|')

for _, row in df.iterrows():
    country = row['Country']
    first_year = int(row['First Year'])
    first_gep = int(row['First GEP (2019 USD)'])
    last_year = int(row['Last Year'])
    last_gep = int(row['Last GEP (2019 USD)'])
    pct_change = row['Percent Change']
    
    # Format percent change
    if pct_change == 0:
        pct_str = '+0.00%'
    else:
        pct_str = f'{pct_change:+.2f}%'
    
    lines.append(f'| {country} | {first_year} | {first_gep:,} | {last_year} | {last_gep:,} | {pct_str} |')

# Write to file
with open('output/appendix_table_markdown.txt', 'w') as f:
    f.write('\n'.join(lines))

print("Appendix table generated successfully!")
print(f"Total countries: {len(df)}")
print(f"First few lines:\n")
for line in lines[:5]:
    print(line)
