"""
Generate all paper tables and figures as reproducible outputs from the authoritative dataset.

This script reads the output of 05-create-gep-panel.py (agr_subsitence_CWON.csv)
and generates all tables and figures as .tex, .csv, or image files for embedding in the report.

Everything in the paper flows from this single authoritative source.
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

# ============================================================================
# LOAD AUTHORITATIVE DATA
# ============================================================================
print("Loading authoritative data from 05-create-gep-panel.py output...")
df = pd.read_csv("output/agr_subsitence_CWON.csv")

print(f"Data loaded: {len(df)} observations across {df['Country'].nunique()} countries")
print(f"Years covered: {df['Year'].min()}-{df['Year'].max()}")

# ============================================================================
# TABLE 1: KEY STATISTICS FOR RESULTS SECTION
# ============================================================================
print("\nGenerating Table 1: Key Statistics...")

n_countries = df['Country'].nunique()
n_obs = len(df)
gep_2019 = df[df['Year'] == 2019]['gep_value'].sum()
gep_2019_billion = gep_2019 / 1e9

# Generate a simple statistics table
stats = {
    'Metric': [
        'Number of countries',
        'Total observations (country-years)',
        'Years covered',
        '2019 Global GEP (billions 2019 USD)',
        'Average annual global GEP (billions 2019 USD)',
    ],
    'Value': [
        str(n_countries),
        str(n_obs),
        f"{df['Year'].min()}-{df['Year'].max()}",
        f"${gep_2019_billion:.2f}",
        f"${df.groupby('Year')['gep_value'].sum().mean() / 1e9:.2f}",
    ]
}

df_stats = pd.DataFrame(stats)
df_stats.to_csv('output/table_01_key_statistics.csv', index=False)

print(f"  2019 Global GEP: ${gep_2019_billion:.2f}B")
print(f"  Countries: {n_countries}")

# ============================================================================
# TABLE 2: TOP 10 COUNTRIES BY 2019 GEP
# ============================================================================
print("\nGenerating Table 2: Top 10 Countries by 2019 GEP...")

df_2019 = df[df['Year'] == 2019].copy()
top_10 = df_2019.nlargest(10, 'gep_value')[['Country', 'gep_value']].reset_index(drop=True)
top_10.columns = ['Country', '2019 GEP (2019 USD)']
top_10['Rank'] = range(1, len(top_10) + 1)
top_10 = top_10[['Rank', 'Country', '2019 GEP (2019 USD)']]
top_10['2019 GEP (billions 2019 USD)'] = top_10['2019 GEP (2019 USD)'] / 1e9

# Create LaTeX version
top_10_tex = top_10[['Rank', 'Country', '2019 GEP (billions 2019 USD)']].copy()
top_10_tex['2019 GEP (billions 2019 USD)'] = top_10_tex['2019 GEP (billions 2019 USD)'].apply(lambda x: f"${x:.2f}")
top_10_tex.to_csv('output/table_02_top_10_countries_2019.csv', index=False)

print("  Saved to: output/table_02_top_10_countries_2019.csv")

# ============================================================================
# TABLE 3: APPENDIX - ALL COUNTRIES WITH TEMPORAL RANGE
# ============================================================================
print("\nGenerating Table 3 (Appendix): All Countries with First/Last Years and % Change...")

appendix_data = []
for country in sorted(df['Country'].unique()):
    country_data = df[df['Country'] == country].sort_values('Year')
    # Only include countries with non-NaN gep_value
    country_data = country_data[country_data['gep_value'].notna()]
    
    if len(country_data) > 0:
        first_year = country_data['Year'].iloc[0]
        first_gep = country_data['gep_value'].iloc[0]
        last_year = country_data['Year'].iloc[-1]
        last_gep = country_data['gep_value'].iloc[-1]
        
        if first_gep > 0:
            pct_change = ((last_gep - first_gep) / first_gep) * 100
        else:
            pct_change = 0 if last_gep == 0 else np.inf
        
        appendix_data.append({
            'Country': country,
            'First Year': int(first_year),
            'First GEP (2019 USD)': int(round(first_gep)),
            'Last Year': int(last_year),
            'Last GEP (2019 USD)': int(round(last_gep)),
            'Percent Change': pct_change,
        })

df_appendix = pd.DataFrame(appendix_data)
df_appendix = df_appendix.sort_values('Country').reset_index(drop=True)
df_appendix.to_csv('output/table_03_appendix_all_countries.csv', index=False)

print(f"  {len(df_appendix)} countries saved to: output/table_03_appendix_all_countries.csv")

# ============================================================================
# FIGURE STATISTICS - Global Annual GEP Time Series
# ============================================================================
print("\nGenerating Figure: Global Annual GEP Time Series...")

annual_gep = df.groupby('Year')['gep_value'].sum() / 1e9

fig, ax = plt.subplots(figsize=(11, 5.5))
ax.plot(
    annual_gep.index,
    annual_gep.values,
    color='#1b7837',
    linewidth=2.5,
    marker='o',
    markersize=5,
)
ax.set_title('Global Subsistence-Crop GEP Over Time', fontsize=15)
ax.set_xlabel('Year', fontsize=12)
ax.set_ylabel('Global GEP (billion 2019 USD)', fontsize=12)
ax.set_xlim(annual_gep.index.min(), annual_gep.index.max())
ax.grid(axis='y', color='#d9d9d9', linewidth=0.8)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

fig.tight_layout()
fig.savefig('output/figure_05_global_gep_annual_levels.png', dpi=300)
fig.savefig('output/figure_05_global_gep_annual_levels.pdf')
plt.close(fig)

print("  Saved to: output/figure_05_global_gep_annual_levels.png and .pdf")

# ============================================================================
# COUNTRY COVERAGE STATISTICS
# ============================================================================
print("\nCalculating country coverage statistics...")

# Count years of data per country
country_years = df.groupby('Country')['Year'].nunique()
countries_by_coverage = {
    'single_year': (country_years == 1).sum(),
    'two_years': (country_years == 2).sum(),
    'three_plus_years': (country_years >= 3).sum(),
}

coverage_stats = f"""
Country Coverage:
- Countries with 1 year of data: {countries_by_coverage['single_year']}
- Countries with 2 years of data: {countries_by_coverage['two_years']}
- Countries with 3+ years of data: {countries_by_coverage['three_plus_years']}
- Total countries: {n_countries}
"""

print(coverage_stats)

# Save coverage stats
with open('output/coverage_statistics.txt', 'w') as f:
    f.write(coverage_stats)

# ============================================================================
# CREATE A SUMMARY REPORT
# ============================================================================
print("\nGenerating summary report...")

summary_report = f"""
===============================================================================
REPRODUCIBLE PAPER OUTPUTS SUMMARY
Generated from: output/agr_subsitence_CWON.csv
===============================================================================

DATA SUMMARY:
  - Authoritative source: 05-create-gep-panel.py output
  - File: output/agr_subsitence_CWON.csv
  - Countries: {n_countries}
  - Observations: {n_obs}
  - Years: {df['Year'].min()}-{df['Year'].max()}

KEY STATISTICS FOR PAPER:
  - 2019 Global GEP: ${gep_2019_billion:.2f} billion (2019 USD)
  - Average annual global GEP: ${df.groupby('Year')['gep_value'].sum().mean() / 1e9:.2f} billion
  - Range: ${df.groupby('Year')['gep_value'].sum().min() / 1e9:.2f}B to ${df.groupby('Year')['gep_value'].sum().max() / 1e9:.2f}B

OUTPUTS GENERATED:
  Tables (as .csv):
    - output/table_01_key_statistics.csv
    - output/table_02_top_10_countries_2019.csv
    - output/table_03_appendix_all_countries.csv
  
  Figures:
    - output/figure_05_global_gep_annual_levels.png (300 DPI)
    - output/figure_05_global_gep_annual_levels.pdf
  
  Statistics:
    - output/coverage_statistics.txt

NEXT STEP:
  Update report.qmd to:
  1. Read tables from .csv files instead of hardcoding values
  2. Use figure_05 instead of the old time series figure
  3. Update text to reference statistics from this summary
  
This ensures complete reproducibility and consistency.
===============================================================================
"""

print(summary_report)

with open('output/REPRODUCIBLE_OUTPUTS_SUMMARY.txt', 'w') as f:
    f.write(summary_report)

print("\nAll outputs generated successfully!")
print("Summary saved to: output/REPRODUCIBLE_OUTPUTS_SUMMARY.txt")
