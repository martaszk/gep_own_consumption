"""
Purpose: 
Construct data: This script loads and transforms data from FAO Rulis (Value of crop used for own consumption, share of total value of crop production (%)) 
with FAO data on Agricultural Production per Area (USD_PPP/ha). Own consumption is calculated for value of production from cropland area of small holder farms (<2h) based on Lowder 2021 paper.
Own consumption is calculated for countries classified as low and lower-middle income countries by World Bank classification.

# Calculate own consumption with equation
    # GEP_subsistence_crops = (Agricultural Production per Area (USD_PPP/ha in a given country and year at the national level) 
    # * (Cropland area national 1000 ha * % of ha for smallholderfarms <2ha from Lowder 2021)  
    # * (Value of crop used for own consumption, share of total value of crop production (%) for questionanires)
"""

######################################################################
# Section: Dependencies and Commands
######################################################################

# Dependencies 
import pandas as pd

# Command: Load World Bank income classification data and clean
def load_WB_class():
    df = pd.read_csv('input/WBHIST.csv', delimiter=';') 
    
    # Reshape WB_class from wide to long format
    df = df.melt(id_vars=["Country"], var_name="Year", value_name="Income Classification")
    
    # Convert 'Year' from string to integer (excluding non-numeric data) and drop nans
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce');
    df = df.dropna(subset=['Year'])
    df['Year'] = df['Year'].astype(int)
    # Return data set
    return df

# Command: Load FAO own consumption data
def loadFAOData():
    df = pd.read_csv('input/FAO_data2.csv', delimiter=';', encoding='utf-8')  # Load FAOdata2 data
    df = df.drop(df.columns[df.columns.str.contains('unnamed', case = False)],axis = 1) # remove unnamed columns
    # do not read the indicator 1 Value of agricultural production sold at the market, share of total value of agricultural production (%)
    df = df[df["Indicator"] != 'Value of agricultural production sold at the market, share of total value of agricultural production (%)']
    return df

# Command: Load in World Bank regional income brackets
def load_region_income():
    # Bring in data
    df = pd.read_csv('input/WBincomegroup.csv', delimiter=';', encoding='utf-8')
    # Rename ISO-3 code 
    df.rename(columns={"Code":"alpha-3"}, inplace=True)
    # Return data set
    return df

# Command: Load in Info on farmers relative to agricultural land
def load_region_lowder_data():
    df = pd.read_csv('input/lowder_2021.csv', delimiter=';', encoding='utf-8')
    df = df[df['Number or share of farms / agricultural area'] == 'share of agricultural area (%)']
    return df

# Command: Load in commerical agricultural values
def load_gross_prod():
    df = pd.read_csv ('input/gross_prod.csv', delimiter=';', encoding='utf-8')
    df = df[['Country', 'Year', 'Value', 'Unit']]
    df = df[df['Unit'] == '1000 USD']
    return df

# Command: Load FAO value of agriculture land (land rentals)
def load_area_value():
    df = pd.read_csv('input/FAO_area_value.csv', delimiter=';', encoding='utf-8')
    df = df.rename(columns={'Area': 'Country'}) 
    return df

# Command: Estimate value of agricultural land
def production_area_data():
    df = load_area_value()
    df = df[df['Element'] == 'Value of agricultural production (Int. $) per Area']
    df = df[['Country', 'Year', 'Value']]
    df = df.rename(columns={'Value': 'Agricultural Production per Area (USD_PPP/ha)'})
    return df

# Command: Subset for cropland
def cropland():
    df = load_area_value()
    df = df[df['Item'] == 'Cropland'][['Item', 'Country', 'Year', 'Unit', 'Value']]
    return df

# Command: Fill in missing national data
def add_missing_national_data(df):
    national_data = df[df['Disaggregation'] == 'National']
    fao_countries = set(df['Country'].unique())
    fao_countries_with_national_data = set(national_data['Country'].unique())
    fao_countries_without_national_data = fao_countries - fao_countries_with_national_data

    missing_data = df[(df['Country'].isin(fao_countries_without_national_data)) & (df['Disaggregation'].isin(['Rural', 'Urban']))]

    aggregated_missing_national = missing_data.groupby(['Country', 'Year', 'Indicator'], as_index=False).agg({
        'Value': 'mean',  # Average 'Value' for each Indicator
        'Agricultural Production per Area (USD_PPP/ha)': 'mean',  # Average production per area
        'Standard Deviation': 'mean',  # Average standard deviation
        'Number of observations': 'sum',  # Sum of observations
        'Income Classification': 'first'  # Take the first available 'Income Classification'
    })

    # Add 'National' as the disaggregation level for the aggregated missing data and combine
    aggregated_missing_national['Disaggregation'] = 'National'
    combined_national_data = pd.concat([national_data, aggregated_missing_national], ignore_index=True)
    # Completed national data
    return combined_national_data

# Command: Estimate Own consumption
def calculate_own_consumption(df):
    # Convert the '< 1 ha' and '1–2 ha' columns to numeric, forcing errors to NaN if necessary
    df['< 1 ha'] = pd.to_numeric(df['< 1 ha'], errors='coerce')
    df['1–2 ha'] = pd.to_numeric(df['1–2 ha'], errors='coerce')
    
    # NOTE: Formula to Calculate own consumption
    # GEP_subsistence_crops = (Agricultural Production per Area (USD_PPP/ha in give country and year at the national level) 
    # * (Cropland area national 1000 ha * % of ha for smallholderfarms <2ha from Lowder 2021)  
    # * (Value of crop used for own consumption, share of total value of crop production (%) for questionanires)
    df['own_con'] = (
        (df['Value_x'] * (df['< 1 ha'] + df['1–2 ha']) * df['Agricultural Production per Area (USD_PPP/ha)'] * df['Value of crop used for own consumption, share of total value of crop production (%)'] / 100) 
        ) 
    # Return data set with own consumption
    return df

######################################################################
# Section: Load and Merge Data
######################################################################

# Combine FAO and WB data
df = pd.merge(loadFAOData(), load_WB_class(), how="left", on=["Country", "Year"])
# Merge in value of agricultural land
df = pd.merge(df, production_area_data(), on=['Country', 'Year'], how='left')
# Fill in missing data
df = add_missing_national_data(df)

# Pivot the data so that each indicator becomes a column
df = df.pivot_table(index=['Country', 'Year','Agricultural Production per Area (USD_PPP/ha)'], columns='Indicator', values='Value', aggfunc='first').reset_index()

# Merge in necessary covariates
df = pd.merge(df, cropland(), on=['Country', 'Year'], how='left')
df = pd.merge(df, load_region_income(), on=['Country'], how='left')
df = pd.merge(df, load_region_lowder_data(), on='Region', how='left')
df = pd.merge(df, load_gross_prod(), on=['Country', 'Year'], how='left')

######################################################################
# Section: Estimate Own Consumption
######################################################################

# Estimate own consumption
df = calculate_own_consumption(df)

# Select the desired columns to keep
columns_to_keep = [
    'Country',
    'Year',
    'alpha-3',
    'Region',
    'Income group',
    'own_con'  # Assuming this is an existing column or one to rename
]
# Reduce the dataset to the specified columns
df = df[columns_to_keep]

# Rename variables 
#df = df.rename(columns = {'Country': 'country', 'Year': 'year', 'Region': 'region','Income group': 'income-group'})

# Output the initial own consumption datset
df.to_csv('./intermediates/data-own-consumption.csv', index=False)
