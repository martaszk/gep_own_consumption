import pandas as pd

def load_WB_class():
    df = pd.read_csv('input_data/WBHIST.csv', delimiter=';') 
    
    # Reshape WB_class from wide to long format
    df = df.melt(id_vars=["Country"], var_name="Year", value_name="Income Classification")
    
    # Convert 'Year' from string to integer (excluding non-numeric data) and drop nans
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce');
    df = df.dropna(subset=['Year'])
    df['Year'] = df['Year'].astype(int)
    return df

def loadFAOData():
    df = pd.read_csv('input_data/FAO_data2.csv', delimiter=';', encoding='utf-8')  # Load FAOdata2 data
    df = df.drop(df.columns[df.columns.str.contains('unnamed', case = False)],axis = 1) # remove unnamed columns
    return df

def load_area_value():
    df = pd.read_csv('input_data/FAO_area_value.csv', delimiter=';', encoding='utf-8')
    df = df.rename(columns={'Area': 'Country'}) 
    return df

def load_region_income():
    return pd.read_csv('input_data/WBincomegroup.csv', delimiter=';', encoding='utf-8')

def load_region_lowder_data():
    df = pd.read_csv('input_data/lowder_2021.csv', delimiter=';', encoding='utf-8')
    df = df[df['Number or share of farms / agricultural area'] == 'share of agricultural area (%)']
    return df

def load_gross_prod():
    df = pd.read_csv ('input_data/gross_prod.csv', delimiter=';', encoding='utf-8')
    df = df[['Country', 'Year', 'Value', 'Unit']]
    df = df[df['Unit'] == '1000 USD']
    return df

def production_area_data():
    area_data_df = load_area_value()
    df = area_data_df[area_data_df['Element'] == 'Value of agricultural production (Int. $) per Area']
    df = df[['Country', 'Year', 'Value']]
    df = df.rename(columns={'Value': 'Agricultural Production per Area (USD_PPP/ha)'})
    return df

def cropland():
    area_value_df = load_area_value()
    return area_value_df[area_value_df['Item'] == 'Cropland'][['Item', 'Country', 'Year', 'Unit', 'Value']]

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
    return combined_national_data

def calculate_own_consumption(df):
    # Convert the '< 1 ha' and '1–2 ha' columns to numeric, forcing errors to NaN if necessary
    df['< 1 ha'] = pd.to_numeric(df['< 1 ha'], errors='coerce')
    df['1–2 ha'] = pd.to_numeric(df['1–2 ha'], errors='coerce')
    
    # Calculate own consumption with equation
    # GEP_subsistence_crops = (Agricultural Production per Area (USD_PPP/ha in give country and year at the national level) 
    # * (Cropland area national 1000 ha * % of ha for smallholderfarms <2ha from Lowder 2021)  
    # * (Value of crop used for own consumption, share of total value of crop production (%) for questionanires)* (A_reg)
    df['Own Consumption (%)'] = (
        (df['Value_x'] * (df['< 1 ha'] + df['1–2 ha']) * df['Agricultural Production per Area (USD_PPP/ha)'] * df['Value of crop used for own consumption, share of total value of crop production (%)'] / 100) 
        / df['Value_y'] 
        ) 

    return df

df = pd.merge(loadFAOData(), load_WB_class(), how="left", on=["Country", "Year"])
df = pd.merge(df, production_area_data(), on=['Country', 'Year'], how='left')
df = add_missing_national_data(df)

# Pivot the data so that each indicator becomes a column
df = df.pivot_table(index=['Country', 'Year','Agricultural Production per Area (USD_PPP/ha)'], columns='Indicator', values='Value', aggfunc='first').reset_index()

df = pd.merge(df, cropland(), on=['Country', 'Year'], how='left')
df = pd.merge(df, load_region_income(), on=['Country'], how='left')
df = pd.merge(df, load_region_lowder_data(), on='Region', how='left')
df = pd.merge(df, load_gross_prod(), on=['Country', 'Year'], how='left')

df = calculate_own_consumption(df)
# This look bad, but only at the end I realized that this column is not used
df = df.drop('Value of agricultural production sold at the market, share of total value of agricultural production (%)', axis=1)

df.to_csv('total_value_of_agriculture_2.csv', index=False)
print(f"The average percentage of own consumption is: {df['Own Consumption (%)'].mean():.2f}%")