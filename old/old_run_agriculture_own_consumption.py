# Dependencies
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import functions_own_consumption as oc

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


# TODO: Using the results, fill in the missing values for 
    # missing own consumption for country/year = point estimate (0.0193) * FAO value for a country/year
    # Two countries with missing FAO commerical data: Uganda and Gutemala

# CHECK: Using formula to predict for own consumption values we have. What is the difference (e.g., what is the error)


# CHECK: What is the value per hectacre in each country? Do we have outliers?

# TODO: Upscale by the number of farms (or number of people) in each country...
    # Maybe static over time, but changing over time.

# TODO: Export CSV with own consumption dataset

# TODO: 
