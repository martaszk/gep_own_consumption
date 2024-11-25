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


# Adjustment for nature's contribution (agricultural resource rent = land)

#  Replace the 0.33 with CWON numbers 2024

    # NOTE: Need to do this for commerical as well. 
    # NOTE: Need to get the data from Marta

# Discounting using a base year (PPP adjustments)
    # TODO: Need to get the data from Raahil

# Export the gep value panel as csv
#df.to_csv('./output/data-gep-agriculture-subsistence.csv', index=False)



