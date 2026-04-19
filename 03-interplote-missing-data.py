"""
Purpose: 
This script uses the coefficients from the interpolation regression to interpolate missing information in the own consumption data. 
This outputs a completed panel for own consumption data.
"""

# Dependencies
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
import statsmodels.api as sm
from sklearn.metrics import r2_score
import re
import unicodedata


def normalize_country_name(name):
    if pd.isna(name):
        return ""
    normalized = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode('ascii')
    normalized = normalized.lower().strip().replace('&', ' and ')
    normalized = re.sub(r'[^a-z0-9]+', ' ', normalized)
    return re.sub(r'\s+', ' ', normalized).strip()


COUNTRY_ALIASES = {
    "United Republic of Tanzania": "Tanzania, United Republic of",
}


def add_iso_codes(df):
    """Attach ISO3 using normalized country names and aliasing."""
    iso = pd.read_csv('input/ISO-3-codes.csv', delimiter=',', encoding='utf-8')
    iso = iso[['name', 'alpha-3']].copy()
    iso['country_key'] = iso['name'].apply(normalize_country_name)

    df = df.copy()
    df['country_iso_name'] = df['Country'].replace(COUNTRY_ALIASES)
    df['country_key'] = df['country_iso_name'].apply(normalize_country_name)
    df = pd.merge(df, iso[['country_key', 'alpha-3']], on='country_key', how='left', suffixes=('', '_iso'))

    if 'alpha-3_iso' in df.columns:
        df['alpha-3'] = df['alpha-3'].combine_first(df['alpha-3_iso'])
        df = df.drop(columns=['alpha-3_iso'])
    df = df.drop(columns=['country_iso_name', 'country_key'])
    return df

# TODO: Using the results, fill in the missing values for 
    # missing own consumption for country/year = point estimate (0.0193) * FAO value for a country/year

# Two countries with missing FAO commerical data: Uganda and Gutemala

# CHECK: Using formula to predict for own consumption values we have. What is the difference (e.g., what is the error)


# CHECK: What is the value per hectacre in each country? Do we have outliers?
#Regressions: This script uses the own consumption data and the commerical data to determine a loose relationship between the two. 
#The coefficient then determines how we can interpolate missing information in the own consumption data given information we have 
#from the commerical data.

# TODO: Building the connection between 01 and 02
# TODO: Marta manually changed the names of countries between WB and FAO. Especially CĂ´te d'Ivoire. We need to automate that. 

# Input data from FAO on own consumption
df1 = pd.read_csv('./intermediates/data-own-consumption.csv', delimiter=',', encoding='utf-8')
df2 = pd.read_csv('input/gross_prod_FAO_USD.csv', delimiter=',', encoding='utf-8')
df3 = pd.read_csv('input/WITS-Country-Timeseries.csv', delimiter=';', encoding='utf-8')
# Merge df1 and df2 on 'year' and 'country'
df2 = df2[['Country', 'Year', 'Value']].rename(columns={'Value': 'Value_gross_prof'})
merged_df = pd.merge(df1, df2, on=['Year', 'Country'], how='left')


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
merged_df = pd.merge(merged_df, df3_melted, on=['Year', 'Country'], how='left')

# Display the final merged DataFrame
print("Final Merged DataFrame:", merged_df.head(), sep="\n")

# Print column names as a list
print("Column names as a list:", merged_df.columns.tolist())


# Define dependent and independent variables
# Dependent variable: 'own_con'
y = merged_df['own_con']  

# Independent variable(s): Use 'Agricultural Production per Area (USD_PPP/ha)' as an example
X = merged_df[['Value_gross_prof', 'GDP_capita']]


# Sample main dataset with 'Country', 'Year', and 'own_con'
# Ensure 'merged_df' is loaded as your main data

# Create a complete set of years (2004–2021) for each country
all_years = pd.DataFrame({'Year': np.arange(2004, 2022)})
df_complete = df1[['Country']].dropna().drop_duplicates().merge(all_years, how='cross')

# Merge this complete set with your main 'merged_df' to preserve all 'Country'-'Year' combinations
df = df_complete.merge(merged_df, on=['Country', 'Year'], how='left')
# Merge GDP data
df = pd.merge(df, df3_melted, on=['Country', 'Year'], how='left', suffixes=('', '_gdp'))

# Check if the merging worked as expected
print("Merged DataFrame with GDP and Gross Production:")
print(df.head())

# Drop rows with NaNs in any of the predictor columns
df = df.dropna(subset=['Year', 'GDP_capita', 'Value_gross_prof'])


# Define the polynomial interpolation function
def interpolate_multivariate_polynomial(group, degree=2):
    # Drop rows with NaNs in 'own_con' to fit the model
    known_points = group.dropna(subset=['own_con'])
    
    # Check if there are enough data points to fit the model
    if len(known_points) == 0:
        return group

    # Fallback for sparse countries (e.g., only one observed point):
    # scale commercial production with the observed own-consumption ratio.
    if len(known_points) <= degree:
        ratio_series = (known_points['own_con'] / known_points['Value_gross_prof']).replace([np.inf, -np.inf], np.nan).dropna()
        group['own_con2'] = group['own_con']
        if not ratio_series.empty:
            fallback_ratio = ratio_series.median()
            missing_mask = group['own_con2'].isna() & group['Value_gross_prof'].notna()
            group.loc[missing_mask, 'own_con2'] = group.loc[missing_mask, 'Value_gross_prof'] * fallback_ratio
        else:
            constant_value = known_points['own_con'].iloc[0]
            group['own_con2'] = group['own_con2'].fillna(constant_value)
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
    print(f"R-squared for {group.name}: {r_squared}  -  {len(known_points) }")
    
    # Prepare features for all data points in the group
    X_all = group[['Year', 'GDP_capita', 'Value_gross_prof']].values
    X_poly_all = poly.transform(X_all)
    
    # Predict 'own_con' values for all years in the group
    group['own_con_interpolated'] = model.predict(X_poly_all)
    

    #print(f'{group['Country'].iloc[0]} {len(known_points)}  r_sqr value: {r2_score(y_true, y_pred)}, {adjusted_r_squared}')


    # Keep observed values and fill gaps with interpolated predictions.
    group['own_con2'] = group['own_con']
    missing_mask = group['own_con2'].isna()
    group.loc[missing_mask, 'own_con2'] = group.loc[missing_mask, 'own_con_interpolated']
    group['fit'] = model
    return group.drop(columns='own_con_interpolated')  # Drop the helper column after interpolation

# Apply the interpolation function by country
df_interpolated = df.groupby('Country').apply(interpolate_multivariate_polynomial, degree=1)

# Reset index for a clean DataFrame — in pandas 3.x groupby key becomes index level 0
df_interpolated = df_interpolated.reset_index(level=0).reset_index(drop=True)

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

# Select the specified columns and save to CSV. own_con2 = own con interpolated
print(filtered_df[['Country', 'Year', 'alpha-3', 'own_con', 'own_con2']])

# TODO: Filter only necessary varibles
filtered_df = filtered_df[['Country', 'Year','alpha-3','own_con', 'own_con2']]
filtered_df = add_iso_codes(filtered_df)

# Output clean own consumption datset
filtered_df.to_csv('./intermediates/data-own-consumption-interpolation.csv', index=False)


# Save a second copy with explicit ISO naming for downstream scripts.
filtered_df.to_csv('./intermediates/data-own-consumption-interpolation-ISO.csv', index=False)

missing_alpha3 = filtered_df[filtered_df['alpha-3'].isnull()]
if not missing_alpha3.empty:
    print("Warning: Missing alpha-3 codes for the following countries:")
    print(missing_alpha3['Country'].unique())
else:
    print("All alpha-3 codes mapped successfully.")