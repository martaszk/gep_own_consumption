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
df = df[['Country', 'Year', 'own_con2']]
df.rename(columns={'own_con2': 'gep-agriculture-subsistence'}, inplace=True)
print(df)
df1 = pd.read_csv('./input/CWON2024_crop_coef.csv', delimiter=';', encoding='utf-8')
df1.rename(columns={"ISO3":"alpha-3"}, inplace=True)
print(df1)
# TODO: Upscale by the number of farms (or number of people) in each country...
    # Maybe static over time, but changing over time.
    # Would like to do this but no information. 
# NOTE: We upscale in 01-construct using hectares of farm land. 
# NOTE: This is static over time. That is strong assumption given consolidation by large farmers >> smallholder hectares are likely decreasing over time.


# Adjustment for nature's contribution (agricultural resource rent = land)
rental_rate = 0.33
df['gep-agriculture-subsistence'] = df['gep-agriculture-subsistence'] * rental_rate

#  Replace the 0.33 with CWON numbers 2024

    # NOTE: Need to do this for commerical as well. 
    # NOTE: Need to get the data from Marta

# Discounting using a base year (PPP adjustments)
    # TODO: Need to get the data from Raahil

# Export the gep value panel as csv
df.to_csv('./output/data-gep-agriculture-subsistence.csv', index=False)

