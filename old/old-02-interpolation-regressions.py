"""
Regressions: This script uses the own consumption data and the commerical data to determine a loose relationship between the two. 
The coefficient then determines how we can interpolate missing information in the own consumption data given information we have 
from the commerical data.
"""

import pandas as pd
import statsmodels.api as sm

# Function: Regressing commerical agriculture on own consumption
def own_consumption_gross_prod_model(df_own_consuption, df_gross_prod):
    df_merged = pd.merge(df_own_consuption, df_gross_prod, on=['Country', 'Year'], how='left')
    df_filtered = df_merged[df_merged['Unit'] != '1000 SLC']
    df_filtered.to_csv('../data/own_consumption/regression_input.csv', index=False)
    
    # Define Regressor: commerical value of agr.
    X = df_filtered['Value']
    X = sm.add_constant(X).dropna()
    
    # Define Outcome: own consumption
    Y = df_filtered['Value_of_Own_Consumption']
    Y = Y.loc[X.index]

    # Run a simple OLS model
    model = sm.OLS(Y, X).fit()
        # TODO: We can play with the regression. 
        # TODO: Add country FE
        # TODO: Add time trend
        # TODO: Add polynomial
        # TODO: Add gdp per capita by nation by year
        # TODO: Compare across the different regressions.
    return model


# Input data from FAO on own consumption
df = pd.read_csv('../data/own_consumption/FAO_data2.csv', delimiter=';', encoding='utf-8')

# TODO: Unclear function...
own_consumption = oc.calculate_own_consumption(df, 
        # Reason: TODO: Go to manuscript
        countries_to_exclude= ['Albania', 'Mexico', 'Bulgaria', 'Panama', 'South Africa'],
        # Reason: TODO: Go to manuscript
        observations_to_exclude=[
            {'Country': 'Mali', 'Year': 2019},
            {'Country': 'Nigeria', 'Year': 2013},
            {'Country': 'Niger', 'Year': 2019},
            {'Country': 'Burkina Faso', 'Year': 2019},
    ])

# FAO commerical agriculture data
df_gross_prod = pd.read_csv('../data/own_consumption/gross_prod.csv', delimiter=';', encoding='utf-8')

# Regression estimating linear trends in own consumption relationship to commerical agriculture
model = oc.own_consumption_gross_prod_model(own_consumption, df_gross_prod)

# Results of model
print(model.summary())