# GEP crop provision: smallholder own consumption and commercial crop provision

This project computes the crop provision part of Gross Ecosystem Product (GEP) by country and year: the value of
crops that smallholder households grow and eat themselves (subsistence), and the value of all crop production
(commercial, which includes subsistence). Nature's contribution is the land rent share of the value of production,
taken from the CWON 2024 cropland rental rates.

The pipeline builds one panel for 2004–2021. The paper's trends use the whole panel; the GEP figure uses the base
year 2019. Every year follows the same rules, so the 2019 GEP figure is the 2019 point of the trend.

Change history: [changes.md](changes.md). Differences from the previous method:
[comparison_ver.old_new.md](comparison_ver.old_new.md).

## Contents

1. [Quick start](#1-quick-start)
2. [What is estimated](#2-what-is-estimated)
3. [Pipeline](#3-pipeline)
4. [Method by step](#4-method-by-step)
5. [Settings](#5-settings)
6. [Input files](#6-input-files)
7. [Outputs](#7-outputs)
8. [Results of the default run](#8-results-of-the-default-run)
9. [Using the panel for trends](#9-using-the-panel-for-trends)
10. [Known limitations](#10-known-limitations)
11. [Checks](#11-checks)
12. [Code layout](#12-code-layout)
13. [References](#13-references)

## 1. Quick start

Requirements: Python 3.12 and the packages in [requirements.txt](requirements.txt). The input CSV files are
stored in Git LFS, so after cloning run `git lfs pull` (git-lfs must be installed).

```
pip install -r requirements.txt
python run.py
```

`run.py` runs steps 01–07 in one pass, in under a minute, and writes everything to a new folder
`results/<YYYY-MM-DD_HH-MM>/`:

- `intermediates/`: tables passed between steps; each name starts with the number of the step that made it;
- `outputs/`: the results;
- `run_settings.yaml`: every value of `consts.py` used, the command line, the git commit, the package versions and
  the result of the checks.

Options:

| Command | Effect |
|---|---|
| `python run.py --no-intermediates` | do not write the intermediate tables (the steps still pass them on in memory) |
| `python run.py --until 5` | run steps 01–05 only |
| `python run.py --no-validate` | skip the checks of `validate.py` |
| `python run.py --set NAME=VALUE` | override any value of `consts.py` for this run; repeatable |
| `python run.py --set DICT.KEY=VALUE` | override one entry of a dict, e.g. `--set INPUTS.prices=Prices_2027.csv` |
| `python run.py --tag NAME` | append `_NAME` to the run folder name |

`VALUE` is read as a Python literal (`1.2`, `None`, `False`, `()`, `{'EGY': 2018}`); anything else is taken as text,
so `--set METHOD=cwon` works without quotes. Examples of sensitivity runs:

```
python run.py --tag cwon --set METHOD=cwon
python run.py --tag linear --set TIME_PATH=linear_fit --set MAX_SURVEY_AGE=10
python run.py --tag egypt --set "V_BREAK_FIX={'EGY': 2018}"
```

To see what changed between two runs, for example after a FAOSTAT update or a different setting:

```
python compare_runs.py results/2026-11-11_19-42 results/2026-11-12_09-10
```

It pairs the files of the two run folders and reports each as IDENTICAL, EQUAL (numbers within a relative tolerance
of 1e-9), DIFFERENT (with the columns, number of cells, largest difference and first rows) or MISSING, and lists the
settings that differ. Exit code 1 when anything differs.

Each run folder takes about 33 MB (30 MB is the table by crop); delete old ones by hand.

## 2. What is estimated

> **Own consumption (USD, country c, year t) = V(c,t) × a(c,t) × o(c,t)**

| Term | Meaning | Source |
|---|---|---|
| **V** | Crop production value, current USD | Set by `V_SOURCE`. By default (`'faostat_fill'`) FAOSTAT Value of Agricultural Production (QV), item "Crops", in current USD, and the gross value of step 04 where FAOSTAT has none. `'commercial'` uses the gross value of step 04 for every country. |
| **a** | Share of V that comes from farms under 2 ha (the smallholder share) | Ricciardi et al. 2018, RuLIS, Lowder et al. 2021, in that order of preference |
| **o** | Share of the crop production of farms under 2 ha that the household consumes itself | RuLIS (FAO Rural Livelihoods Information System) |

> **Subsistence GEP = own consumption × CWON 2024 cropland rental rate**
>
> **Commercial (total) GEP = Σ over crops of gross production value × CWON 2024 cropland rental rate**

Both parts use the same annual country rental rates and the same deflator. FAO production includes what households
eat themselves, so the commercial figure is the total of crop provision. The crop provision panel puts the total,
the subsistence part and total − subsistence side by side.

## 3. Pipeline

| Step | File | What it does | Reads from `input/` | Takes from earlier steps |
|---|---|---|---|---|
| 01 | `step_01_rulis_own_share.py` | RuLIS surveys; own-consumption share o per survey | RuLIS (2 files), ISO, World Bank groups | — |
| 02 | `step_02_smallholder_share.py` | smallholder share a per country, by source | Ricciardi, Lowder, Producer Prices, Land Use, ISO, World Bank groups | RuLIS surveys (01) |
| 03 | `step_03_yearly_share_paths.py` | yearly paths of o, and of a for RuLIS-based countries | — | o per survey (01), a (02) |
| 04 | `step_04_commercial_crop_provision.py` | commercial crop provision: gross value by crop, country and year × rental rate | Production, Prices, Value of Production, Trade, WDI exchange rates, CWON crop list and rental rates, ISO, CPI | — |
| 05 | `step_05_own_consumption.py` | all countries and years: V × a × o; base-year tables | Value of Production, ISO, World Bank groups, CPI | a (02, 03), o (03), crop table (04) |
| 06 | `step_06_gep_panel.py` | subsistence GEP and the crop provision panel | rental rates, CPI, ISO | own consumption (05), commercial by country (04) |
| 07 | `step_07_paper_outputs.py` | tables, figure and map for the paper | ee_r264 regions (map) | subsistence GEP (06) |

The steps pass their tables in memory; no step reads a result file. Step 04 does not depend on 01–03; it runs
before 05 because 05 may take crop value from its crop table.

## 4. Method by step

### Step 01: RuLIS surveys and the own-consumption share o

1. **Merge the two RuLIS files** survey by survey, group by group and variable by variable. The FAOSTAT bulk file
   wins where both have a value; FAO_data2 fills the cells the bulk file lacks (for example Albania 2005 has no
   national own-consumption value in the bulk file).
2. **Groups:** N national, R and U rural and urban, SF small-scale food producers, NSF the other farm households.
   RuLIS defines small-scale producers relative to each country: roughly the bottom 40% of farms by land, livestock
   and revenue (the SDG 2.3 definition). That is not the same as farms under 2 ha: the SF group farms on average from
   0.1 ha (Armenia) to 2.4 ha (Mali, Niger).
3. **Bring RuLIS to the 2 ha cut-off.** For each group g (SF, NSF), RuLIS gives the number of households, the mean
   cultivated area and its standard deviation. Assuming lognormal farm sizes within a group:
   - land_g = households_g × mean area_g
   - F_g = share of the group's land on farms under 2 ha (area-weighted lognormal distribution)
   - land under 2 ha = land_SF × F_SF + land_NSF × F_NSF (used by step 02)
   - **o for farms under 2 ha** = Σ_g land_g F_g o_g ÷ Σ_g land_g F_g

   The two groups are weighted by their land under 2 ha. Value per ha is taken as equal between them, because RuLIS
   value per ha has extreme outliers.
4. **Gaps in household counts.** Where only one group's household count is reported, the other is derived from the
   small-scale producers' share of agricultural households. Where that share is missing too, the country's median
   over its other surveys is used, else the median over all surveys (`ssfp_share_source`).
5. **One basis per country.** A survey that lacks something the under-2 ha share needs takes the national share ×
   the country's median ratio between the two (else the median ratio over all surveys); the small-scale share is the
   next fallback, then the mean of rural and urban. This keeps each country's series on one basis. The national share
   bridges best: its median ratio to the under-2 ha share is 1.008 over 66 surveys (small-scale: 0.896 over 67).
   `own_share_basis` records what each survey used.

The own-consumption share of farms under 2 ha is almost identical to the national share (median difference +0.1
points over 66 surveys). In the current run: 103 surveys in 42 countries, of which 98 surveys in 39 countries give an
own-consumption share.

### Step 02: smallholder share a

Every source is first converted to the same quantity: **the share of national crop value produced on farms under
2 ha.**

| Tier (`A_TIER_ORDER`) | How a is computed |
|---|---|
| `ricciardi_observed` | Ricciardi production by size class × FAOSTAT producer price (global median USD/t per crop, 2008–2016). a = value on farms under 2 ha ÷ value on all farms. Used where at least half the value is observed production, not filled in by the authors with one yield for all sizes. |
| `ricciardi_area` | Ricciardi countries where production was mostly filled in. Crop area by class becomes a value share crop by crop with the yield ratio r, then is weighted by crop value. |
| `rulis` | RuLIS land under 2 ha (step 01) ÷ FAOSTAT cropland in the survey year. If household land exceeds cropland, the share of household land under 2 ha is used instead (coverage capped at 1, flagged). |
| `lowder` | Lowder farm area under 2 ha × `SMALL_FARM_CROPLAND_FRACTION` ÷ FAOSTAT cropland in the census year (capped at 100%, flagged). Censuses whose smallest class starts at 2 ha or more (Argentina, Australia, New Zealand, Zambia) get no share; the area of their smallest class ÷ cropland is kept as an upper bound, and step 05 caps their imputed share at it. |

**Area shares to value shares** (rulis, lowder, ricciardi_area): a = a_area × r ÷ (a_area × r + 1 − a_area), where r
is the yield of farms under 2 ha relative to larger farms. With `YIELD_RATIO = 'ricciardi'`, r is pooled from the
Ricciardi crops whose production is observed in both groups: each country gets a value-weighted geometric mean, and r
is the median across countries. In the current run **r = 1.012** over 14 countries (from 0.03 in Cambodia and 0.38 in
Brazil to 2.66 in Nigeria and about 21 in Mali and Niger), so area shares are in effect used as value shares.

**Checks on Ricciardi before it is used:**

- Survey-based countries cover farm households only, like RuLIS. Their share is multiplied by the survey crop area ÷
  FAOSTAT crop area (capped at 1). Countries where that coverage cannot be computed (Mexico, Mongolia, Panama,
  Russia, South Africa, Timor-Leste) or is below `RICCIARDI_MIN_COVERAGE` (Mali) are left out.
- Where observed production implies a yield ratio outside `YIELD_RATIO_BOUNDS` (0.5–2), the observed value share is
  not used and the country falls to its area-based share: Niger (11.3), Mali (7.2), Nigeria (2.4), Uruguay (0.5) and
  Cambodia (0.3) in the current run.
- Countries with fewer than `RICCIARDI_MIN_CROPS` crops (Burkina Faso) or no size class below 2 ha are left out.

Each country takes the first available tier. For RuLIS, the survey nearest to the base year represents the country
in the tier table; step 03 uses every survey. `02_smallholder_share_candidates.csv` lists every source side by side.
In the current run a comes from 133 countries: Ricciardi observed 10, Ricciardi area 38, RuLIS 21, Lowder 64.

### Step 03: yearly paths

- **o, for every surveyed country:**
  - `TIME_PATH = 'interpolate'` (default): survey years keep their value; years between surveys are interpolated
    linearly; years before the first or after the last survey hold the nearest survey's value.
  - `TIME_PATH = 'linear_fit'`: a straight line through all of a country's surveys, held at its end values outside
    the survey years. This smooths noisy series such as Nigeria (76% in 2013, 22% in 2016, 30% in 2019).
- **a, for countries whose share comes from RuLIS** (`A_TIME_VARYING = True`): the same path through the survey
  values. Ricciardi and Lowder shares are single snapshots and stay constant.
- `MAX_SURVEY_AGE`: years further than this from any survey are left empty and get the regional median in step 05
  (`None` = always hold). Kenya's and Albania's only surveys are from 2005, so with `None` their share is held to
  2021.

### Step 04: commercial crop provision

Gross production value by crop, country and year × CWON 2024 rental rate, from `COMMERCIAL_FIRST_YEAR` (1995).

`METHOD = 'gep'` (default) combines CWON 2024 and global_invest:

- **Crops** (`CROP_LIST = 'faostat'`): every primary crop FAOSTAT values in its Value of Production data, minus the
  FAO group totals and processed products (cotton lint, cottonseed, palm oil, palm kernels, cassava leaves, kapok).
  The list is built from QV, not from production (QCL), because QCL also carries processed products that would count
  a crop twice. `CROP_LIST = 'cwon'` uses CWON's 159 wealth crops instead.
- **Price per crop, country and year**: the country's USD producer price; its SLC price converted with the World
  Bank WDI rate PA.NUS.ATLS (as CWON); its price interpolated between its own neighbouring years (CWON); the FAO
  subregion, region and world price. `REGIONAL_PRICE = 'weighted_median'` (default) weights each country's price by
  its production, so large low-price producers are not valued at small high-price neighbours' prices (North Korean
  rice at Japanese and Korean prices); `'median'` counts every country the same (global_invest). CWON's product
  substitutions are used where a crop has no price of its own.
- **Price filters**: a USD price that is a copy of the SLC price is dropped; then `OUTLIER_RULE`:
  `'world_median_ratio'` (default; global_invest) drops prices above 20 × the world median of the crop and year,
  `'cwon_iqr'` replaces prices at or above the median + 1.5 IQR by the median (CWON), `'none'` keeps all.
- **Gross value** (`VALUE_BASIS`): `'reported_first'` (default) takes FAO's reported value first and production ×
  price only where FAO reports production but no value; `'production_x_price'` values everything at production ×
  price (global_invest's base-year basis).

`METHOD = 'cwon'` follows CWON 2024 (land.do in the World Bank package FR_WLD_2024_195): the 159 wealth crops,
production forward-filled from 1970, three price series per country, crop and year (unit value, producer price,
export unit value) each with CWON's substitutions, target-year fill, outlier rule and interpolation, CWON's price
order with production-weighted regional and world averages over its 14 ef_regions, years 1970–2020. Constant prices
use the CPI deflator of this project, not CWON's GDP deflator; current-USD values are not affected.

Both methods: China is FAO "China, mainland"; Belgium and Luxembourg are split out of Belgium-Luxembourg before 2000
as in CWON; the seven territories CWON leaves out are left out; a country without a CWON rental rate gets no rent.

### Step 05: all countries, panel and base year

- **V** (`V_SOURCE`):
  - `'faostat'`: FAOSTAT "Crops" value only. Countries and years FAOSTAT does not value are left out.
  - `'faostat_fill'` (default): FAOSTAT where it reports, else the gross value of step 04. FAOSTAT publishes no
    current-USD crop value for, among others, Uganda after 1998, DR Congo, Haiti, Liberia, Somalia, South Sudan,
    North Korea, Papua New Guinea, Uzbekistan, Venezuela after 2014 and Zimbabwe in 2019–20.
  - `'commercial'`: the gross value of step 04 for every country, so subsistence and total crop provision rest on
    the same value.
  - Years after the last year of step 04 (2021 with `METHOD = 'cwon'`): FAOSTAT × the country's step 04 / FAOSTAT
    ratio of that last year where FAOSTAT reports, else the last value held.
  - `V_BREAK_FIX = {'EGY': 2018}`: from 2019, Egypt's V = V(2018) × production at 2018 prices ÷ production in 2018 at
    2018 prices, crop by crop. This keeps the change in quantity but not FAOSTAT's 2019 price jump (Egypt's QV
    doubles at flat production). Off by default; a sensitivity.
  - `crop_value_source` records which value each row uses.
- **a**: from step 02, with the RuLIS paths of step 03.
- **o**: from step 03. `OWN_SHARE_OVERRIDES` sets o for a country without a RuLIS survey from another source (China:
  47.3%, from the China Household Finance Survey; an upper bound).
- **Countries without a term** get the median of the donor countries in the same World Bank region (at least
  `MIN_COUNTRIES_FOR_REGIONAL_MEDIAN` = 5 donors), else the same UN region (continent), else the global median,
  constant over time. Donors for a are the countries with a source in step 02; donors for o are the surveyed
  countries' base-year values from step 03, held values included. An imputed a never exceeds a country's Lowder
  upper bound.
- **Scope**: the countries of the income groups in `EXCLUDE_INCOME_GROUPS` (default: high and upper-middle income)
  are left out of the panel after computation. They are listed in `own_consumption_excluded_2019.csv` and still
  serve as donors. The groups come from the World Bank historical classification (`OGHIST_2026_10_08.xlsx`), in the
  classification based on the GNI per capita of the base year: FY21, published in July 2020, for 2019.
  `INCOME_GROUP_YEAR` selects another year. One classification holds for every year of the panel: across the RuLIS
  surveys the own-consumption share is unrelated to income, so a country does not drop in and out of the panel when
  its class changes. Territories the classification does not cover get a group from `INCOME_GROUP_ADDITIONS`:
  Guadeloupe, French Guiana, Martinique and Réunion high income (French overseas departments), the Cook Islands high
  income and Niue upper middle income (OECD DAC list of ODA recipients). Venezuela, which the World Bank left
  unclassified for GNI years 2020–2024, gets upper middle income there; for 2019 the World Bank gives it the same
  group.
- **own_con2 = V × a/100 × o/100** in current USD, and `own_con2_2019` in 2019 USD.

### Step 06: subsistence GEP and the crop provision panel

- **Subsistence GEP** = own_con2 × CWON 2024 rental rate (annual, 1995–2020; later years hold the 2020 rate).
  Countries without a CWON rate get no GEP.
- **Panel** (`gep_crop_provision_panel.csv`): total (step 04), subsistence, total − subsistence and the subsistence
  share, in current and 2019 USD. With `METHOD = 'cwon'`, 2021 rows have subsistence but no total.

### Step 07: paper outputs

Table 1 (key statistics), table 2 (the 10 countries with the largest 2019 GEP), table 3 (every country's first and
last year and the change between them), the figure of global subsistence GEP per year and the map of 2019
subsistence GEP by country (both PNG), all from the subsistence GEP of the same run, in 2019 USD (`gep_value_2019`).
Countries and country-years are counted where they have a GEP value. The number of countries by years with a GEP
value (coverage statistics) is printed on the console only.

The map draws the regions of `ee_r264_correspondence.gpkg` in the Equal Earth projection, without Antarctica
(`MAP_EXCLUDED_REGIONS`). Each region takes the 2019 GEP of the country whose ISO3 code is the region's own code
(`ee_r264_label`), so every country with GEP is drawn once. Areas whose own code is not that of a country with GEP
stay gray, among them the disputed areas Z01–Z09 (Kashmir, Aksai Chin and others) and Western Sahara (ESH). The
countries with GEP fall into five quantile classes
(about 16 countries each); their bounds, in million 2019 USD, are the legend. The GeoPackage is read with `sqlite3`
and `shapely`; GDAL is not needed.

## 5. Settings

All settings, codes and paths are in [consts.py](consts.py), in three parts: run settings, fixed codes and tables,
paths. Every value there can be overridden for one run with `--set`; `run_settings.yaml` records what a run used.

| Setting | Default | Meaning |
|---|---|---|
| `BASE_YEAR` | 2019 | GEP base year; values are also restated in its prices |
| `DEFLATOR` | `'us_cpi'` | `'us_cpi'` or `'country_cpi'` |
| `DISCOUNT`, `HORIZON` | 0.04, 100 | CWON 2024 asset value of the rent (factor 24.505) |
| `OC_FIRST_YEAR`, `OC_LAST_YEAR` | 2004, 2021 | Own-consumption panel years |
| `SMALL_FARM_HA` | 2.0 | Farm-size cut-off |
| `OWN_SHARE_BASIS` | `'lt2ha'` | o for farms under 2 ha; `'small_scale'` or `'national'` for sensitivity runs |
| `A_TIER_ORDER` | Ricciardi observed, Ricciardi area, RuLIS, Lowder | Order of preference for a |
| `YIELD_RATIO` | `'ricciardi'` (pooled, 1.012) | Or a number, e.g. 1.2 |
| `YIELD_RATIO_BOUNDS` | (0.5, 2.0) | Plausible yield ratios |
| `SMALL_FARM_CROPLAND_FRACTION` | 1.0 | Share of Lowder farm area under 2 ha that is cropland |
| `RICCIARDI_MIN_CROPS`, `RICCIARDI_MIN_OBSERVED`, `RICCIARDI_MIN_COVERAGE` | 5, 0.5, 0.2 | When Ricciardi is used |
| `PRICE_YEARS` | (2008, 2016) | Producer prices valuing Ricciardi crops |
| `TIME_PATH` | `'interpolate'` | Or `'linear_fit'` |
| `A_TIME_VARYING` | True | RuLIS-based a follows the surveys over time |
| `MAX_SURVEY_AGE` | None | E.g. 10, to stop holding very old surveys |
| `MIN_COUNTRIES_FOR_REGIONAL_MEDIAN` | 5 | Fewer donors in the region: UN region; fewer there: global median |
| `EXCLUDE_INCOME_GROUPS` | High income, Upper middle income | Left out of the GEP panel; `()` keeps every country |
| `INCOME_GROUP_YEAR` | None (= `BASE_YEAR`) | Year of the GNI per capita behind the World Bank classification; 2019 gives FY21 |
| `INCOME_GROUP_ADDITIONS` | 7 territories (section 4, step 05) | Income groups where the World Bank classification has none |
| `OWN_SHARE_OVERRIDES` | China 47.3% | o from another source for countries without RuLIS |
| `V_SOURCE` | `'faostat_fill'` | `'faostat'`, `'faostat_fill'` or `'commercial'` |
| `V_BREAK_FIX` | `{}` | E.g. `{'EGY': 2018}` |
| `METHOD` | `'gep'` | `'gep'` or `'cwon'` |
| `COMMERCIAL_FIRST_YEAR` | 1995 | First year of commercial values (first CWON rental-rate year) |
| `OUTLIER_RULE` | `'world_median_ratio'` | `'world_median_ratio'`, `'cwon_iqr'` or `'none'` |
| `CROP_LIST` | `'faostat'` | `'faostat'` or `'cwon'` |
| `VALUE_BASIS` | `'reported_first'` | `'reported_first'` or `'production_x_price'` |
| `REGIONAL_PRICE` | `'weighted_median'` | `'weighted_median'` or `'median'` |
| `CWON_FIRST_YEAR`, `CWON_TARGET_YEAR` | 1970, 2020 | Years of `METHOD = 'cwon'` |

Part 2 of `consts.py` holds the FAOSTAT and RuLIS codes, country corrections, price substitutions, technical
thresholds and the thresholds of the checks; part 3 the file names of inputs, intermediates and outputs.

## 6. Input files

All files are in `input/`; the pipeline reads them and never changes them. Download dates are those of the files'
own metadata (date inside the archive or date first saved); please correct them where they are wrong.

| File | Content | Source | Version | Downloaded | Steps |
|---|---|---|---|---|---|
| `Production_Crops_Livestock_E_All_Data.csv` | FAOSTAT Crops and livestock products (QCL), wide layout | FAOSTAT, Bulk Downloads, "All Data" (https://www.fao.org/faostat/en/#data) | file of 2025-12-23 | 2026-11-09 | 04 |
| `Value_of_Production_E_All_Data.csv` | FAOSTAT Value of Agricultural Production (QV) | as above | file of 2026-05-07 | 2026-11-09 | 04, 05 |
| `Prices_E_All_Data.csv` | FAOSTAT Producer Prices (PP) | as above | file of 2026-10-09 | 2026-11-09 | 02, 04 |
| `Trade_CropsLivestock_E_All_Data.csv` | FAOSTAT Crops and livestock products, trade (TCL); 428 MB | as above | file of 2026-07-24 | 2026-11-09 | 04 (`METHOD = 'cwon'`; without it the export unit value is skipped) |
| `Inputs_LandUse_E_All_Data.csv` | FAOSTAT Land Use (RL): cropland | as above | file of 2026-10-01 | 2026-11-09 | 02 |
| `Rural_Livelihoods_Indicators_E_All_Data_Normalized.csv` | FAOSTAT Rural Livelihoods Indicators (RuLIS), normalized layout; renamed from `..._(Normalized).csv` | as above | file of 2026-07-23 | 2026-11-09 | 01 |
| `FAO_data2.csv` | RuLIS, an earlier extract (household-level indicators by group) | FAO RuLIS data portal | not recorded | 2024-09-16 (file date) | 01 |
| `API_PA.NUS.ATLS_DS2_en_csv_v2_3895.csv` | World Bank WDI PA.NUS.ATLS, DEC alternative conversion factor (LCU per US$) | https://data.worldbank.org/indicator/PA.NUS.ATLS, Download CSV | Last Updated 2026-10-08 | 2026-11-09 | 04 |
| `CPI_WB.csv` | World Bank WDI FP.CPI.TOTL.ZG, inflation, consumer prices (annual %), 2004–2023, ';' separated | World Bank DataBank export | not recorded | 2026-11-09 (file date) | 04, 05, 06 |
| `FarmSize_data_fullyProcessed.csv` | Ricciardi et al. 2018: crop area and production by farm-size class | Mendeley Data, doi:10.17632/tp63z6dz5g.1 | v1 | 2026-11-08 | 02 |
| `lowder_2021_country.xlsx` | Lowder et al. 2021, Web Appendix B, Table 3: farms and farm area by size class; renamed from `numer_area_country.xlsx` | World Development 142, 105455, supplementary material | 2021 | 2026-11-08 | 02 |
| `land_ef_regional_cropland_rental_rates_new.csv` | CWON 2024 cropland rental rates, country × year, 1995–2020, with ef_regions | World Bank reproducibility package FR_WLD_2024_195, `Input/Predefined` | 2024 | 2026-11-08 | 04, 06 |
| `land_crop_list.csv` | CWON 2024 crop list (wealth crops) | as above | 2024 | 2026-10-28 | 04 |
| `ISO-3-codes.csv` | ISO 3166 codes with UN regions, ';' separated | layout of `all.csv` of github.com/lukes/ISO-3166-Countries-with-Regional-Codes | not recorded | 2026-01-21 (file date) | 01, 02, 04, 05, 06 |
| `WBincomegroup.csv` | World Bank economies with region and income group, ';' separated | World Bank country and lending groups | classification of July 2024 (FY25): its income groups equal the FY25 column of `OGHIST_2026_10_08.xlsx` for every economy | 2024-09-16 (file date) | 01, 02, 05 |
| `OGHIST_2026_10_08.xlsx` | World Bank historical classification by income: the group (L, LM, UM, H) of each economy for fiscal years FY89–FY27, with the year of the GNI per capita each is based on | World Bank Country and Lending Groups, historical classification (https://datahelpdesk.worldbank.org/knowledgebase/articles/906519-world-bank-country-and-lending-groups) | FY89–FY27; workbook saved 2026-07-28 | 2026-10-08 (date in the file name) | 05 |
| `ee_r264_correspondence.gpkg` | ee_r264 countries and territories: outlines (multipolygons, EPSG:4326) with the codes of other classifications and Natural Earth attributes; 84 MB | GEP team | not recorded | 2026-11-11 | 07 (map) |

The `WBincomegroup.csv` Region column groups countries for imputing missing shares, and its names help match
countries; its Income group column is not used. The income groups that set the scope (`EXCLUDE_INCOME_GROUPS`) come
from `OGHIST_2026_10_08.xlsx`, for the base year. A local copy of the folder as of 2026-11-11,
including the zip archives the CSV files were extracted from, is in `input.zip` (not in git).

## 7. Outputs

`results/<run>/intermediates/` (written unless `--no-intermediates`):

| File | Content |
|---|---|
| `01_rulis_surveys.csv` | every RuLIS survey: shares by group, households, land, F_g, own-consumption share under 2 ha, basis |
| `01_own_share_observed.csv` | o per survey |
| `02_smallholder_share.csv` | a per country, with source tier, year and upper bound |
| `02_smallholder_share_candidates.csv` | all sources of a side by side, flags, coverage, implied yield ratio |
| `02_smallholder_share_rulis_surveys.csv` | a per RuLIS survey |
| `02_yield_ratio.csv`, `02_yield_ratio_by_country.csv` | pooled and country yield ratios |
| `03_own_share_panel.csv` | o by country and year, with source and nearest survey |
| `03_smallholder_share_panel.csv` | a by year for RuLIS-based countries |
| `04_cpi_index.csv` | CPI index per country (2019 = 100) |

`results/<run>/outputs/`:

| File | Step | Content |
|---|---|---|
| `agr_commercial_by_country_year_crop.csv` | 04 | gross value, price and source, rental rate and GEP by crop, country and year |
| `agr_commercial_CWON.csv` | 04 | commercial (total) crop provision by country and year, with crop wealth and 2019 USD |
| `agr_commercial_price_sources.csv` | 04 | share of each year's value by value and price source |
| `own_consumption_panel.csv` | 05 | **the own-consumption panel**: V and its source, a, o, their sources, own_con2 in current and 2019 USD, income group |
| `own_consumption_2019.csv` | 05 | base-year rows of the panel |
| `own_consumption_summary_2019.csv` | 05 | base-year total by region, by source of a and by source of o |
| `own_consumption_share_imputation.csv` | 05 | regional, UN-regional and global medians used for imputation |
| `own_consumption_excluded_2019.csv` | 05 | base-year rows of the countries left out by `EXCLUDE_INCOME_GROUPS` |
| `agr_subsistence_CWON.csv` | 06 | **subsistence GEP** by country and year: current USD (`gep_value`) and 2019 USD (`gep_value_2019`) |
| `gep_crop_provision_panel.csv` | 06 | total, subsistence, total − subsistence, subsistence share |
| `table_01_key_statistics.csv`, `table_02_top_10_countries_2019.csv`, `table_03_appendix_all_countries.csv` | 07 | paper tables |
| `figure_05_global_gep_annual_levels.png` | 07 | paper figure: global subsistence GEP per year |
| `figure_06_subsistence_gep_map_2019.png` | 07 | paper map: 2019 subsistence GEP by country, five quantile classes |

## 8. Results of the default run

Run of 2026-11-11 with the default settings (2019 values):

| Quantity | 2019 |
|---|---|
| Smallholder own consumption | 77.75 bn USD in 79 countries (9.7% of their crop value) |
| Subsistence GEP | 25.52 bn USD in 79 countries |
| Commercial (total) crop provision | gross value 3,023.45 bn USD; GEP 714.27 bn USD; 194 countries |
| Total − subsistence | 688.74 bn USD |

With `METHOD = 'cwon'`, the 2020 commercial rent is 659.99 bn USD against 687.21 bn implied by CWON 2024's published
crop wealth (16,840 bn / 24.505), −4.0%; the 2019 commercial GEP is 642.67 bn USD and the 2019 subsistence GEP
24.99 bn USD.

Sensitivity of the 2019 figures to the crop value V:

| V | Own consumption | Subsistence GEP | Countries |
|---|---|---|---|
| FAOSTAT only (`'faostat'`) | 69.72 bn | 23.08 bn | 57 |
| FAOSTAT, gaps from step 04 (`'faostat_fill'`, default) | 77.75 bn | 25.52 bn | 79 |
| Step 04 for every country (`'commercial'`) | 86.58 bn | 28.37 bn | 79 |
| Default, Egypt at 2018 prices (`V_BREAK_FIX`) | 74.84 bn | 24.12 bn | 79 |
| `'commercial'`, Egypt at 2018 prices | 83.67 bn | 26.97 bn | 79 |

Sensitivity to the year of the income classification: with the classification published in July 2019 (FY20, GNI
2018; `INCOME_GROUP_YEAR = 2018`) Indonesia, lower middle income in it, enters the panel and Algeria and Sri Lanka
leave: 85.97 bn USD of own consumption and 28.20 bn USD of subsistence GEP in 78 countries.

## 9. Using the panel for trends

- Use `own_con2_2019` and `gep_value_2019` (2019 USD), not the current-USD columns, so price inflation does not show
  up as a change in subsistence.
- With a mostly constant, most change over time comes from V and, in surveyed countries, from o. Say so in the paper.
- Separate countries with at least two surveys (`own_con_source` observed or interpolated) from imputed ones. Held
  and regional-median values are flat by construction, and that flatness is not evidence of stability.
- Watch for breaks in V that are FAOSTAT's, not real: Egypt 2019 (`V_BREAK_FIX`), and countries whose
  `crop_value_source` switches between FAOSTAT and step 04.

## 10. Known limitations

1. **Concentration.** India is 19% of the 2019 total. Its o is 9.7% from the 2012 survey, held to 2021 (2005:
   35.8%), and its a of 50% is a Ricciardi area share where census area is 2.1 × FAOSTAT cropland. Report India
   separately and check both terms.
2. **China** is an upper-middle income country and is left out by default. If it is included, o comes from the China
   Household Finance Survey (47.3%, an upper bound) and a from Lowder's 1997 census; China would then be about
   420 bn USD of own consumption and dominate the total.
3. **Old sources.** Lowder census years run from 1987 to 2017. With `MAX_SURVEY_AGE = None`, RuLIS shares are held
   up to 16 years (Albania, Kenya).
4. **Survey breaks.** o changes by more than 20 points between consecutive surveys in Nigeria (−54), Mali (+40),
   Burkina Faso (+39), Côte d'Ivoire (−28), India (−26), Niger (+26) and Malawi (+20). These look like changes in
   survey design. Run `TIME_PATH = 'linear_fit'` as a sensitivity.
5. **North Africa.** The Middle East & North Africa region has one surveyed country (Iraq), so Algeria, Djibouti,
   Egypt, Morocco and Tunisia take the Africa median (47.9%), which comes from Sub-Saharan surveys.
6. **Smallholder sources disagree** by more than 25 points for Ethiopia (Ricciardi area 81% from a 2001 census;
   RuLIS 40%; Lowder 54%), Cambodia, Niger, Nigeria, Peru and Uganda. The pooled r takes its median over countries
   including those outside `YIELD_RATIO_BOUNDS` (Mali, Niger, Cambodia), and Albania and Ghana have yield ratios of
   exactly 1.000, a sign of constant-yield production passing as observed.
7. **RuLIS land** is rounded to 0.1 ha, and the lognormal assumption fails in some surveys (Niger, Nepal). RuLIS
   household land can exceed FAOSTAT cropland (it may count land cropped twice a year); such surveys are capped and
   flagged.
8. **Two value bases.** With `'faostat'` or `'faostat_fill'`, subsistence uses FAOSTAT's reported value and the total
   uses step 04's prices. They agree for the median country but differ by more than 30% in 2019 for the Central
   African Republic, Guinea, Laos, Sudan, Viet Nam and Yemen. `V_SOURCE = 'commercial'` puts both on one basis.
9. **CPI.** `CPI_WB.csv` covers 2004–2023, so the 2019-USD columns of step 04 are empty for 1995–2003. A missing
   inflation rate inside that period counts as 0%; with `DEFLATOR = 'country_cpi'` a country with gaps gets a wrong
   deflator without a warning. The default US CPI has no gaps.
10. **Income groups.** The scope rests on one World Bank classification, the one based on the base year's GNI per
    capita (FY21 for 2019), applied to every year. The year matters: Indonesia is upper middle income in FY21 but
    lower middle income in FY20 and FY22–FY23; with FY20 its 3.0 bn USD of subsistence GEP enters the panel and
    Algeria and Sri Lanka leave (28.20 instead of 25.52 bn USD in 2019, section 8). Six territories missing from the
    classification get a group from `INCOME_GROUP_ADDITIONS`; none of them has subsistence GEP.
11. **CWON method.** With `METHOD = 'cwon'` the values end in 2020, and CWON's outlier rule (median + 1.5 IQR across
    countries) cuts the unit values of high-price countries hard; this matters little for subsistence countries but
    does for the total.

## 11. Checks

`run.py` runs the checks of [validate.py](validate.py) after the last step. Hard checks must hold (the formula, the
survey paths, rental rates, totals that add up); a failure makes `run.py` end with exit code 1. Flags point at
results worth a look (held surveys, survey jumps, breaks in values, regional prices, gaps between FAOSTAT and
step 04 values). The default run has 0 hard failures and 13 flags.

## 12. Code layout

| File | Content |
|---|---|
| `run.py` | the only entry point |
| `consts.py` | settings, codes, thresholds and paths; no functions |
| `utils.py` | helpers used by more than one step; no constants |
| `step_NN_*.py` | the steps; each has a `run()` that takes the tables of earlier steps and returns its own |
| `validate.py` | checks of the results |
| `compare_runs.py` | comparison of two run folders |

Conventions: every function and module has a docstring (Google style); the steps read `consts.NAME` when they run,
so `--set` reaches every value; method options are passed to functions as arguments; numbers in the code are unit
conversions only (100 for percent, 1000 for thousand USD, 1e9 for billions); messages use `print`.

## 13. References

- Lowder, S. K., Sánchez, M. V. & Bertini, R. (2021). Which farms feed the world and has farmland become more
  concentrated? *World Development* 142, 105455. Web Appendix B, Table 3.
- Ricciardi, V., Ramankutty, N., Mehrabi, Z., Jarvis, L. & Chookolingo, B. (2018). How much of the world's food do
  smallholders produce? *Global Food Security* 17, 64–72. Data: Mendeley Data, doi:10.17632/tp63z6dz5g.1.
- FAO. Rural Livelihoods Information System (RuLIS), FAOSTAT Rural Livelihoods Indicators.
- FAO. FAOSTAT: Value of Agricultural Production (QV), Producer Prices (PP), Production (QCL), Trade (TCL), Land Use
  (RL).
- World Bank (2024). The Changing Wealth of Nations 2024 (CWON), reproducibility package FR_WLD_2024_195.
- World Bank. World Development Indicators: PA.NUS.ATLS, FP.CPI.TOTL.ZG.
- Šavrič, B., Patterson, T. & Jenny, B. (2019). The Equal Earth map projection. *International Journal of
  Geographical Information Science* 33(3), 454–465.
