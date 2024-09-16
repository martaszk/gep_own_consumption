

# Function: Estimating Own Consumption
def calculate_own_consumption(df, countries_to_exclude, observations_to_exclude):
    # Conditions for filtering
    indicator_2 = "Value of crop used for own consumption, share of total value of crop production (%)"  
    indicator_3 = "Average cultivated land area (ha),"
    indicator_4 = "Value of production per hectare/year, PPP (constant 2011 international USD)"

    # Exclude certain countries from analysis
    df_filtered = df[~df['Country'].isin(countries_to_exclude)]

    df_filtered = pd.merge(df_filtered, pd.DataFrame(observations_to_exclude), on=['Country', 'Year'], how='left', indicator=True)
    df_filtered = df_filtered[df_filtered['_merge'] == 'left_only'].drop(columns=['_merge'])

    # Create vectors for variables of interest
    df_ind2 = df_filtered[(df_filtered['Indicator'] == indicator_2) & (df_filtered['Disaggregation'] == 'National')]
    df_ind3 = df_filtered[(df_filtered['Indicator'] == indicator_3) & (df_filtered['Disaggregation'] == 'National')]
    df_ind4 = df_filtered[(df_filtered['Indicator'] == indicator_4) & (df_filtered['Disaggregation'] == 'National')]

    # Rename variables to be sensible
    df_ind2 = df_ind2.rename(columns={'Value': 'Own_Consumption_Percentage'})
    df_ind3 = df_ind3.rename(columns={'Value': 'Average_Cultivated_Land_Area'})
    df_ind4 = df_ind4.rename(columns={'Value': 'Production_Per_Hectare'})

    # Merge vectors back into a dataframe again.
    merged_df = pd.merge(df_ind2[['Country', 'Year', 'Own_Consumption_Percentage']],
        df_ind3[['Country', 'Year', 'Average_Cultivated_Land_Area']],
        on=['Country', 'Year'], how='inner')

    merged_df = pd.merge(merged_df,
        df_ind4[['Country', 'Year', 'Production_Per_Hectare']],
        on=['Country', 'Year'], how='inner')

    merged_df['Value_of_Own_Consumption'] = merged_df['Production_Per_Hectare'] * merged_df['Average_Cultivated_Land_Area'] * merged_df['Own_Consumption_Percentage']

    # Export cleaned dataframe for FAO own consumption data
    return merged_df

# Function: 
    # TODO: Alternative ways of estimating own consumption
    # This is because we do not trust the FAO values of own consumption.
    # "Step 3: own consumption - magnitude and change over time" in the manuscript.