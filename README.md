# GEP: own consumption

# Steps: 
1. Take FAO own consumption and create a clean panel of country-year own consumption. 
2. Create a dataset of covariates that we can use for interpolation and extrapolation. 
3. Within the FAO data, several countries have missing years. Additionally, FAO is missing several important countries with food insecurity. We can use the dataset of covariates to regress own consumption values on these covariates (including year) to interpolate the missing years and extrapolate to new countries. This expands the sample. 
4. Using the clean, updated values for own consumption, we can convert this into a GEP measure and upscale it for the number of farmers in each country to be the aggregate GEP for each country-year. This creates a panel of GEP values. 
5. With the panel data on GEP, we can assess descriptives about subsistence agriculture GEP globally.

# File Edits: 
02 - Ryan Starts to build covariate data
03 - Marta clean up. Marta add Interpolation run for countries (4) moving in and out of income brackets. 
   - Ryan review 
04 - Ryan complete's extrapolation. Marta review
05 - Marta adds CWON (nature's contribution) corrections (Done).  Also Marta adds CWON to the commerical agriculture github repo.
   - Marta brings in discounting for CPI correction. (DONE)
06 - Ryan starts summary stats. Marta helps as she wants. 

# Comments from Marta:
We change the columns heads to small letters at the end, as the whole has been written with capital letters

