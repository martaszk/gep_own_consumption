"""
Purpose: 
This script uses the original own consumption and the interpolated own consumption (or comparison) to create, 
extrapolated values for counties outside the FAO sample but meet food insecurity criteria. 
This exports an final data set on own consumption for all qualifying countries. 
"""

# Dependencies
import numpy as np
import pandas as pd
import statsmodels.api as sm

# TODO: For merging, we will want to use ISO-3 alpha codes to make our life easier...

# Command: Limit sample years 
def limit_years(data):
    year_columns = [col for col in data.columns if col.isdigit() and 2004 <= int(col) <= 2021]
    return(year_columns)


# Bring in list of eligible countries
df_cntry = pd.read_csv('./input/WBHIST.csv', delimiter=';', encoding='utf-8')
# Limit to eligible countries for extrapolation 
    # NOTE: Based on WB income group category (L or LM) as of baseline for own consumption (2004)
# Keep only year 2004 - 2021
year_columns = limit_years(df_cntry)
df_cntry = df_cntry[['Country'] + year_columns]

# Melt df_cntry as a long format of country-year pairs.
df_cntry = df_cntry.melt(id_vars=['Country'], var_name='Year', value_name='wb_income')

# Keep if lower or lower-middle income country
condition = (df_cntry["wb_income"] == "L") | (df_cntry["wb_income"] == "LM")
df_cntry = df_cntry[condition]


# Bring in the interpolated data 
df_int = pd.read_csv('./intermediates/data-own-consumption-interpolation.csv', delimiter=',', encoding='utf-8')

# Bring in Commerical Agriculture
df_com_agr = pd.read_csv('input/gross_prod_FAO_USD.csv', delimiter=',', encoding='utf-8')
# Bring in GDP measure
df_gdp = pd.read_csv('input/WITS-Country-Timeseries.csv', delimiter=';', encoding='utf-8')

# Clean GDP data to be in long format 
# Select 'country' and columns that are between 2004 and 2021
year_columns = limit_years(df_gdp)
df_gdp = df_gdp[['Country'] + year_columns]

# =Melt the filtered df_gdp to transform years from columns to rows
df_gdp = df_gdp.melt(id_vars=['Country'], var_name='Year', value_name='GDP_capita')
# Convert the 'year' column to integer, if it’s not already
df_gdp['Year'] = df_gdp['Year'].astype(int)

# Merge data own consumption data with measure used for extrapolation
df_merge = pd.merge(df_cntry, df_int, on=['Year', 'Country'], how='left')
df_merge = pd.merge(df_merge, df_gdp, on=['Year', 'Country'], how='left')
df_merge = pd.merge(df_merge, df_com_agr, on=['Year', 'Country'], how='left')

# TODO: Use regression or ML to extrapolate (big task)
    # Variables to extrapolate at country level: GDP_pc, commerical agriculture, some food insecurity measure, size of agricultural sector, rural, population density, hectacres of 
    # NOTE: https://www.sciencedirect.com/science/article/pii/S0959378020307536
    # NOTE: Countries to extrapolate over are 2004 - 2021

# Define dependent and independent variables
# Dependent variable: 'own_con'
y = df_merge['own_con2']  

# Independent variable(s): 
X = df_merge[['Value', 'GDP_capita']]

# Models to Run and Compare: 
    # Three classes of models: 
    # (1) Time Series 
    #     Moving Average, Autoregressive model, ARMA
    # (2) OLS with covariates
        # Simple OLS
        # Try year FE
        # Try with a time trend
        # Polynomial Regression 
    # (3) Machine learning predictions
        # Lasso Regression 
            # https://machinelearningmastery.com/lasso-regression-with-python/
        # Random Forest

# TODO: Can use formatting from interpolation. Would make functions for general format and if condition for type of regression so you can quickly run each. 
# TODO: Need some output table that show the comparision of variables selected, coefficient values, and model fit. 

# TODO: Export results as a data set
#df_ext.to_csv('./intermediates/data-own-consumption-extrapolation.csv', index=False)
