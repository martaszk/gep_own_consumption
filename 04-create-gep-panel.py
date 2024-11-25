"""
Purpose: 
This script uses the panel data for own consumption (by year and country) to generate the GEP value for 
own consumption ecosystem service value. 
This outputs the panel of gep value which will be used by the larger GEP team. 
"""

# Dependencies
import numpy as np
import pandas as pd

# TODO: Bring in the extrapolated data when done 
    # NOTE: Currently the interpolated
df = pd.read_csv('./intermediates/data-own-consumption-interpolation.csv', delimiter=',', encoding='utf-8')
print(df)
df = df[['Country', 'Year', 'own_con2']]
df.rename(columns={'own_con2': 'gep-agriculture-subsistence'}, inplace=True)

df1 = pd.read_csv('./input/CWON2024_crop_coef.csv', delimiter=';', encoding='utf-8')
print(df1)
# TODO: Upscale by the number of farms (or number of people) in each country...
    # Maybe static over time, but changing over time.
    # Would like to do this but no information. 
# NOTE: We upscale in 01-construct using hectares of farm land. 
# NOTE: This is static over time. That is strong assumption given consolidation by large farmers >> smallholder hectares are likely decreasing over time.


# Adjustment for nature's contribution (agricultural resource rent = land)
df['gep-agriculture-subsistence'] = df['gep-agriculture-subsistence'] * 0.33


    # TODO: Replace the 0.33 with CWON numbers 2024 Marta: I only apply the CWON2024 coeficient for non-irrigated crops.
    # NOTE: Need to do this for commerical as well. Marta: for commercial agg we actually need to distinguish between crop, rainfed and pasture (Cwon2024)
    # NOTE: Need to get the data from Marta

# Discounting using a base year (PPP adjustments)
    # TODO: Need to get the data from Raahil

# Export the gep value panel as csv
df.to_csv('./output/data-gep-agriculture-subsistence.csv', index=False)

