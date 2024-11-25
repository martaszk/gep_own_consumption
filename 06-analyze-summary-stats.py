"""
Purpose:
This script analyzes the own consumption data panel. 
It produces summary statistics. 
It also compares the own consumption values to the commerical agricultural values. 
"""
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Import GEP: Subsistence 

# Load data
data = pd.read_csv('./output/agr_subsistence_adjusted_2020.csv')

# Calculate year-over-year absolute change for gep_value_2020
data['gep_value_change'] = data.groupby('Country')['gep_value_2020'].diff()


# Plot Year-over-Year Absolute Change
plt.figure(figsize=(12, 6))
sns.lineplot(
    data=data, 
    x='Year', 
    y='gep_value_change', 
    hue='Country', 
    marker='o', 
    palette='tab10'
)
plt.title('Year-over-Year Change in GEP Value (2020 USD)', fontsize=16)
plt.xlabel('Year', fontsize=14)
plt.ylabel('Change in GEP Value (2020 USD)', fontsize=14)
plt.axhline(0, color='gray', linestyle='--', linewidth=1)  # Add a horizontal line at 0
plt.legend(title='Country')
plt.grid()
plt.show()

plt.savefig('./output/yoy_change_subsistence_value.png', dpi=300)



# Import GEP: Commerical



# Summary statistics


# Map for average gep across the time period

# Lists top countries for own consumption



# As a 2nd half to the script, we compare the own consumption measures to the commercial FAO data on these countries. 
# Porportionally are they in line (e.g., a quality check). 


# comparision with commerical