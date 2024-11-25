"""
Purpose: 
This script uses the panel data for own consumption (by year and country) to generate the GEP value for 
own consumption ecosystem service value. 
This outputs the panel of gep value which will be used by the larger GEP team. 
"""

# Dependencies

# TODO: Bring in the extrapolated data when done 
    # NOTE: Currently the interpolated

import pandas as pd
import numpy as np

############################################################################
# Adjustment for nature's contribution (agricultural resource rent = land)
#   CWON 2024 cost shares of land
    # NOTE: Need to do this for commerical as well. 
    # NOTE: Need to get the data from Marta
############################################################################

# Load own consumption data
df = pd.read_csv('./intermediates/data-own-consumption-interpolation-ISO.csv', delimiter=',', encoding='utf-8')

# Load crop coefficients
df1 = pd.read_csv('./input/CWON2024_crop_coef.csv', delimiter=';', encoding='utf-8')

# Rename columns for consistency
df1.rename(columns={"ISO3": "alpha-3"}, inplace=True)

# Reshape the decade columns into rows
df1_melted = df1.melt(
    id_vars=["Order", "FAO", "alpha-3", "Country/territory"],
    var_name="Decade",
    value_name="rental_rate"
)

# Extract the starting year of each decade
df1_melted['Decade_start'] = df1_melted['Decade'].str.extract(r'(\d{4})').astype(int)

# Match each year in the own consumption data to the corresponding decade
df = pd.merge(
    df, 
    df1_melted, 
    on="alpha-3", 
    how="left"
)
df = df[df['Year'] >= df['Decade_start']]  # Filter to ensure year falls within the decade
df = df.sort_values(['alpha-3', 'Year', 'Decade_start']).drop_duplicates(['alpha-3', 'Year'], keep='last')

# Calculate GEP value
df['gep_value'] = df['own_con2'] * df['rental_rate']

# Select only the required columns for the output
output_columns = ['Country', 'Year', 'alpha-3', 'own_con', 'own_con2', 'rental_rate', 'gep_value']
df = df[output_columns]

# Save the resulting panel
output_path = './output/agr_subsitence_CWON.csv'
df.to_csv(output_path, index=False, encoding='utf-8')

print(f"GEP subsitence agri with CWON ecosystem contribution saved to: {output_path}")


# TODO: Upscale by the number of farms (or number of people) in each country...
    # Maybe static over time, but changing over time.
    # Would like to do this but no information. 
# NOTE: We upscale in 01-construct using hectares of farm land. 
# NOTE: This is static over time. That is strong assumption given consolidation by large farmers >> smallholder hectares are likely decreasing over time.


#################################################
# CPI preparation 
#################################################

import pandas as pd
import numpy as np

# Load inflation data
inflation_data = pd.read_csv('./input/CPI_WB.csv', delimiter=';', encoding='utf-8')

# Reshape data into long format
metadata_cols = ['Series Name', 'Series Code', 'Country Name', 'Country Code']
inflation_long = inflation_data.melt(id_vars=metadata_cols, var_name='Year', value_name='Inflation_Rate')

# Clean Year column
inflation_long['Year'] = inflation_long['Year'].str.extract(r'(\d{4})')  # Extract 4-digit year
inflation_long['Year'] = pd.to_numeric(inflation_long['Year'], errors='coerce')  # Convert to numeric
inflation_long = inflation_long.dropna(subset=['Year'])  # Drop rows where Year is NaN
inflation_long['Year'] = inflation_long['Year'].astype(int)  # Convert to integer

# Convert Inflation_Rate to numeric
inflation_long['Inflation_Rate'] = pd.to_numeric(inflation_long['Inflation_Rate'], errors='coerce')
inflation_long['Inflation_Rate'] = inflation_long['Inflation_Rate'].fillna(0)  # Fill missing with 0

# Debugging: Inspect the reshaped data
print("Inflation data after preprocessing:")
print(inflation_long.head())

# Initialize an empty list for storing results
cpi_data = []

# Group by country and process each group
for country, group in inflation_long.groupby('Country Code'):
    if group.empty or len(group) < 2:  # Skip groups with insufficient data
        print(f"Skipping {country}: Not enough data.")
        continue

    group = group.sort_values('Year').reset_index(drop=True)
    group['CPI'] = np.nan  # Initialize the CPI column

    # Check if all inflation rates are zero
    if group['Inflation_Rate'].sum() == 0:
        print(f"Flat inflation for {country}, setting CPI = 100 for all years.")
        group['CPI'] = 100
        cpi_data.append(group)
        continue

    # Find the index of the base year (2020)
    base_year_idx = group[group['Year'] == 2020].index
    if len(base_year_idx) > 0:
        base_year_idx = base_year_idx[0]
        group.loc[base_year_idx, 'CPI'] = 100  # Set CPI for the base year

        # Calculate CPI forward (2021 and beyond)
        for i in range(base_year_idx + 1, len(group)):
            group.loc[i, 'CPI'] = group.loc[i - 1, 'CPI'] * (1 + group.loc[i, 'Inflation_Rate'] / 100)

        # Calculate CPI backward (2019 and earlier)
        for i in range(base_year_idx - 1, -1, -1):
            group.loc[i, 'CPI'] = group.loc[i + 1, 'CPI'] / (1 + group.loc[i + 1, 'Inflation_Rate'] / 100)
    else:
        print(f"Base year 2020 not found for {country}. Skipping CPI calculation.")

    # Append processed group to the result list
    cpi_data.append(group)

# Check if any valid data was processed
if len(cpi_data) > 0:
    cpi_long = pd.concat(cpi_data)
else:
    raise ValueError("No valid data to process for CPI calculation.")

# Save CPI data
output_path = './intermediates/CPI_WorldBank.csv'
cpi_long.to_csv(output_path, index=False, quoting=1)  # quoting=1 avoids unnecessary quotes
print(f"CPI data saved to '{output_path}'")

#################################################
# CPI adjustment for constant 2020 USD 
#################################################

import pandas as pd

# Load GEP data
gep_data = pd.read_csv('./output/agr_subsitence_CWON.csv', delimiter=',', encoding='utf-8')

# Load CPI data
cpi_data = pd.read_csv('./intermediates/CPI_WorldBank.csv', delimiter=',', encoding='utf-8')

# Select relevant columns from CPI data
cpi_data = cpi_data[['Country Code', 'Year', 'CPI']]

# Rename columns to match GEP data (if necessary)
cpi_data.rename(columns={'Country Code': 'alpha-3'}, inplace=True)

# Get the CPI for the base year (2020)
cpi_2020 = cpi_data[cpi_data['Year'] == 2020][['alpha-3', 'CPI']].rename(columns={'CPI': 'CPI_2020'})

# Merge GEP data with CPI data on 'alpha-3' and 'Year'
merged_df = pd.merge(gep_data, cpi_data, on=['alpha-3', 'Year'], how='left')

# Merge CPI_2020 values into the dataset
merged_df = pd.merge(merged_df, cpi_2020, on='alpha-3', how='left')

# Adjust GEP values to 2020 USD
merged_df['gep_value_2020'] = merged_df['gep_value'] * (merged_df['CPI_2020'] / merged_df['CPI'])

# Save the adjusted results
output_path = './output/agr_subsistence_adjusted_2020.csv'
merged_df.to_csv(output_path, index=False, encoding='utf-8')

print(f"GEP values adjusted to 2020 USD saved to: {output_path}")

