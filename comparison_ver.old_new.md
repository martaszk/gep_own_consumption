# Comparison with the previous method

How the current method of [README.md](README.md) differs from the previous version of the own-consumption
(subsistence) estimate, and why. The code history is in [changes.md](changes.md).

## Formula

- **Previous:** own consumption = cropland × Lowder smallholder share of the World Bank region × FAO value of
  production per hectare in international dollars (PPP), converted to USD × RuLIS national own-consumption share.
  Missing country-years were interpolated and extrapolated with a regression on covariates (built in
  `02-construct-data-covariates.py`), and the result was upscaled to the number of farms with Lowder's hectares of
  smallholder cropland, which were constant over time.
- **Current:** own consumption = V × a × o: crop production value in current USD × the country's share of that value
  from farms under 2 ha × the own-consumption share of farms under 2 ha. Countries without a term take a regional
  median.

## What changed and why

| Previous method | Current method | Reason |
|---|---|---|
| Lowder share by World Bank **region** (e.g. Latin America & Caribbean 0.9% for every country in the region) | **Country-level** share from Ricciardi, RuLIS or Lowder | The regional figure is dominated by large countries and was very wrong for others: Guatemala, Nicaragua and Peru came out at 0.1–0.7% of crop value. |
| Lowder share of **all farmland** (pasture included) | Share of **cropland** (Lowder hectares under 2 ha ÷ FAOSTAT cropland) | Including pasture understates smallholders where large farms are mostly grazing land: Lowder farmland share vs Ricciardi crop-area share is 0.3% vs 34% for Peru and 4.9% vs 47% for Nigeria. |
| Cropland × FAO value per ha in Int. $ (PPP), then converted to USD | Crop value in current USD (FAOSTAT, with the commercial step's gross value where FAOSTAT has none, or the commercial gross value for every country) | Same unit and source as the commercial part, so "total − subsistence" subtracts like from like. No PPP conversion is needed. |
| RuLIS **national** own-consumption share applied to land under 2 ha | Own-consumption share **of farms under 2 ha**, built from the RuLIS small-scale and other farm-household groups | Both terms refer to the same farms. |
| Covariate regression to interpolate and extrapolate | Yearly paths between surveys (step 03) and regional medians for countries without data (step 05) | The terms of the formula are shares, which are filled between and beyond surveys and taken from similar countries, instead of predicting own consumption itself. |
| Low and lower-middle income countries only, class re-read every year (with an interpolation run for countries moving in and out of income brackets) | Every country with crop value is computed; the GEP panel leaves out the groups in `EXCLUDE_INCOME_GROUPS`, using one World Bank classification for every year: the one based on the base year's GNI per capita (FY21 for 2019) | A country never drops in and out of the panel when its class changes from year to year. Excluded countries still serve as donors for regional medians. Across 85 RuLIS surveys, the own-consumption share is unrelated to income (correlation −0.06). |
| RuLIS from FAO_data2 only | FAOSTAT RuLIS bulk file first, FAO_data2 for gaps | More surveys: 103 (in 42 countries) vs 76. |
| FAOSTAT QV only | `V_SOURCE = 'faostat_fill'`: the commercial gross value where FAOSTAT has no value | FAOSTAT publishes no current-USD crop value for Uganda after 1998, DR Congo, Haiti, Liberia, Somalia, South Sudan, North Korea, Papua New Guinea, Uzbekistan, Venezuela after 2014 and Zimbabwe in 2019–20. With FAOSTAT only, these countries dropped out of subsistence, Uganda included, which has five RuLIS surveys. |
| CWON 2024 decade rental rates (`CWON2024_crop_coef.csv`) | CWON 2024 annual rental rates by country and year (1995–2020; later years hold 2020) | The annual table is CWON's own input; subsistence and commercial use the same rates. |
| Values deflated with each country's own CPI | US CPI for every country by default (`DEFLATOR = 'us_cpi'`); `'country_cpi'` as an option | Values are in current USD, so the US CPI restates them in 2019 USD without mixing in local inflation. |

Data no longer read: the regional Lowder file `lowder_2021.csv`, `WBHIST.csv`, and `FAO_area_value.csv` (an extract
of FAOSTAT Land Use, replaced by the FAOSTAT bulk file).

## Effect on the numbers

The previous method's results are not reproduced by this code. For the current method, the 2019 figures and their
sensitivity to the choice of V are in section 8 of [README.md](README.md). With FAOSTAT values only
(`V_SOURCE = 'faostat'`, the setting before the gap filling), 2019 subsistence GEP is 23.08 bn USD in 57 countries;
with the default gap filling it is 25.52 bn USD in 79 countries.
