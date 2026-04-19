"""Create summary figures for the subsistence-crop GEP panel."""

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def billions_formatter(value, _position):
    return f"{value:.1f}"


data = pd.read_csv(ROOT / 'output' / 'agr_subsitence_CWON.csv')
annual_gep = data.groupby('Year', as_index=False)['gep_value'].sum()
annual_gep['gep_billion_2019usd'] = annual_gep['gep_value'] / 1_000_000_000

fig, ax = plt.subplots(figsize=(11, 5.5))
ax.plot(
    annual_gep['Year'],
    annual_gep['gep_billion_2019usd'],
    color='#1b7837',
    linewidth=2.5,
    marker='o',
    markersize=5,
)
ax.set_title('Global Subsistence-Crop GEP Over Time', fontsize=15)
ax.set_xlabel('Year', fontsize=12)
ax.set_ylabel('Global GEP (billion 2019 USD)', fontsize=12)
ax.yaxis.set_major_formatter(FuncFormatter(billions_formatter))
ax.set_xlim(annual_gep['Year'].min(), annual_gep['Year'].max())
ax.grid(axis='y', color='#d9d9d9', linewidth=0.8)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

fig.tight_layout()
fig.savefig(ROOT / 'output' / 'global_gep_annual_levels.png', dpi=300)
fig.savefig(ROOT / 'output' / 'global_gep_annual_levels.pdf')
plt.close(fig)



# Import GEP: Commerical



# Summary statistics


# Map for average gep across the time period

# Lists top countries for own consumption



# As a 2nd half to the script, we compare the own consumption measures to the commercial FAO data on these countries. 
# Porportionally are they in line (e.g., a quality check). 


# comparision with commerical