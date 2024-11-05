"""
This script uses the coefficients from the interpolation regression to interpolate missing information in the own consumption data. 
This outputs a completed panel for own consumption data.
"""

# TODO: Using the results, fill in the missing values for 
    # missing own consumption for country/year = point estimate (0.0193) * FAO value for a country/year

# Two countries with missing FAO commerical data: Uganda and Gutemala

# CHECK: Using formula to predict for own consumption values we have. What is the difference (e.g., what is the error)


# CHECK: What is the value per hectacre in each country? Do we have outliers?
#Regressions: This script uses the own consumption data and the commerical data to determine a loose relationship between the two. 
#The coefficient then determines how we can interpolate missing information in the own consumption data given information we have 
#from the commerical data.

import pandas as pd
import statsmodels.api as sm
from linearmodels.panel import PanelOLS
import numpy as np

# Input data from FAO on own consumption
df1 = pd.read_csv('input/own_consumption_bez_HIC.csv', delimiter=';', encoding='utf-8')
df2 = pd.read_csv('input/gross_prod_FAO_USD.csv', delimiter=',', encoding='utf-8')
df3 = pd.read_csv('input/WITS-Country-Timeseries.csv', delimiter=';', encoding='utf-8')

# Merge df1 and df2 on 'year' and 'country'
merged_df = pd.merge(df1, df2, on=['Year', 'Country'], how='outer')


# Step 1: Filter df3 to only include 'country' and year columns (2004–2021)
# Select 'country' and columns that are between 2004 and 2021
year_columns = [col for col in df3.columns if col.isdigit() and 2004 <= int(col) <= 2021]
df3_filtered = df3[['Country'] + year_columns]

# Step 2: Melt the filtered df3 to transform years from columns to rows
df3_melted = df3_filtered.melt(id_vars=['Country'], var_name='Year', value_name='GDP_capita')
# Convert the 'year' column to integer, if it’s not already
df3_melted['Year'] = df3_melted['Year'].astype(int)

# Display the melted df3 to check transformation
print("Melted df3:", df3_melted.head(), sep="\n")



# Then merge the resulting DataFrame with df3_melted
merged_df = pd.merge(merged_df, df3_melted, on=['Year', 'Country'], how='inner')

# Display the final merged DataFrame
print("Final Merged DataFrame:", merged_df.head(), sep="\n")

# Print column names as a list
print("Column names as a list:", merged_df.columns.tolist())


# Define dependent and independent variables
# Dependent variable: 'own_con'
y = merged_df['own_con']  

# Independent variable(s): Use 'Agricultural Production per Area (USD_PPP/ha)' as an example
X = merged_df[['Value', 'GDP_capita']]



    # Run a simple OLS model
    #model = sm.OLS(Y, X).fit()
        # TODO: We can play with the regression. 
        # TODO: Add country FE
        # TODO: Add time trend
        # TODO: Add polynomial
        # TODO: Add gdp per capita by nation by year
        # TODO: Compare across the different regressions.
    #return model

import numpy as np
import pandas as pd

# Sample main dataset with 'Country', 'Year', and 'own_con'
# Ensure 'merged_df' is loaded as your main data

# Create a complete set of years (2004–2021) for each country
all_years = pd.DataFrame({'Year': np.arange(2004, 2022)})
df_complete = merged_df[['Country']].drop_duplicates().merge(all_years, how='cross')

# Merge this complete set with your main 'merged_df' to preserve all 'Country'-'Year' combinations
df = df_complete.merge(merged_df, on=['Country', 'Year'], how='left')
# Merge GDP data
df = pd.merge(df, df3_melted, on=['Country', 'Year'], how='left', suffixes=('', '_gdp'))

# Merge gross production data
df = pd.merge(df, df2, on=['Country', 'Year'], how='left', suffixes=('', '_gross_prof'))

# Check if the merging worked as expected
print("Merged DataFrame with GDP and Gross Production:")
print(df.head())

# Drop rows with NaNs in any of the predictor columns
df = df.dropna(subset=['Year', 'GDP_capita', 'Value_gross_prof'])


from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
import statsmodels.api as sm
from sklearn.metrics import r2_score

# Define the polynomial interpolation function
def interpolate_multivariate_polynomial(group, degree=2):
    # Drop rows with NaNs in 'own_con' to fit the model
    known_points = group.dropna(subset=['own_con'])
    
    # Check if there are enough data points to fit the model
    if len(known_points) <= degree:
        #print(f"Skipping {group['Country'].iloc[0]} due to insufficient data for interpolation.")
        return group
    
    # Prepare features (X) and target (y) for known points
    X_known = known_points[['Year', 'GDP_capita', 'Value_gross_prof']].values
    y_known = known_points['own_con'].values
    
    # Generate polynomial features for the specified degree
    poly = PolynomialFeatures(degree=degree, include_bias=False)
    X_poly_known = poly.fit_transform(X_known)
    
    # Fit polynomial regression model
    model = LinearRegression()
    model.fit(X_poly_known, y_known)
    

    #print dir(result)
    #print result.rsquared, result.rsquared_adj

    y_known_pred = model.predict(X_poly_known)
    r_squared = r2_score(y_known, y_known_pred)
    print(f"R-squared for {group['Country'].iloc[0]}: {r_squared}  -  {len(known_points) }")
    
    # Prepare features for all data points in the group
    X_all = group[['Year', 'GDP_capita', 'Value_gross_prof']].values
    X_poly_all = poly.transform(X_all)
    
    # Predict 'own_con' values for all years in the group
    group['own_con_interpolated'] = model.predict(X_poly_all)
    

    #print(f'{group['Country'].iloc[0]} {len(known_points)}  r_sqr value: {r2_score(y_true, y_pred)}, {adjusted_r_squared}')


    # Fill NaN values in 'own_con' with interpolated values
    group['own_con2'] = group['own_con_interpolated']#.combine_first(group['own_con_interpolated'])
    group['fit'] = model
    return group.drop(columns='own_con_interpolated')  # Drop the helper column after interpolation

# Apply the interpolation function by country
df_interpolated = df.groupby('Country').apply(interpolate_multivariate_polynomial, degree=1)

# Reset index for a clean DataFrame
df_interpolated = df_interpolated.reset_index(drop=True)

# Display a sample of the interpolated DataFrame
print("Interpolated DataFrame:")
#print(df_interpolated[!isnan(df_interpolated)['own_con']][['Country', 'Year', 'own_con']].head(200))
print(df_interpolated[df_interpolated['Country']=="Viet Nam"][['Country', 'Year', 'own_con', 'own_con2']].head(200))

#Filter  countries that have at least one non-NaN value in 'own_con2'
countries_with_positive_own_con2 = df_interpolated[(df_interpolated['own_con2'].notna()) & (df_interpolated['own_con2'] >= 0)]['Country'].unique()

# Filter the DataFrame to include only these countries
filtered_df = df_interpolated[
    (df_interpolated['Country'].isin(countries_with_positive_own_con2)) &
    (df_interpolated['own_con2'] >= 0)
]

# Select the specified columns and save to CSV
print(filtered_df[['Country', 'Year', 'own_con', 'own_con2']])
