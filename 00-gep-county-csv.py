import pandas as pd
import numpy as np
import geopandas as gpd

# Load gep data
df = pd.read_csv('./output/agr_subsistence_adjusted_2020.csv', delimiter=',', encoding='utf-8')

# Only keep 2019 values 
df = df[df['Year'] == 2019]

# Correctiong for ee_r250 country mapping
file_path = "../data/ee_r250_correspondence.gpkg"
gdf = gpd.read_file(file_path)
# Merge on country code from df_gep and adm0_a3 from geopackage
df_merged = pd.merge(gdf, df,  how='left', left_on='adm0_a3', right_on='alpha-3')
# Keep a subset of variables 
df_merged = df_merged[['ee_r264_id', 'iso3_r250_id', 'iso3_r250_label', 'ee_r264_description', 'gep_value_2019']]

# Save a csv file of country, year petrolium values
df_gep = df_merged.sort_values(by = ['ee_r264_id'], ascending = [True])
df_gep.to_csv("./output/gep-agr-crop-subsistence.csv", index=False)