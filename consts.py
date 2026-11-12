"""Settings, fixed codes and file paths of the crop provision GEP pipeline.

Three parts, in this order:

1. Run settings: method options and years. These are the values to change for a sensitivity run.
2. Fixed codes and tables: FAOSTAT and RuLIS codes, country corrections, layouts of the result tables.
3. Paths: input files, intermediate files and output files.

Every name in this file can be overridden for one run with ``python run.py --set NAME=VALUE``. The code reads
the values when a step runs, and no value in this file is computed from another one, so an override never
leaves a dependent value behind.
"""
from pathlib import Path

# =====================================================================================================================
# 1. Run settings
# =====================================================================================================================

# ---- General -----------------------------------------------------------------------------------------------------
BASE_YEAR = 2019                    # GEP base year; values are also restated in prices of this year
DEFLATOR = 'us_cpi'                 # 'us_cpi' (US CPI for every country) or 'country_cpi' (each country's CPI)
DISCOUNT = 0.04                     # CWON 2024 discount rate: asset value = rent x (1 - (1 + r)^-T) / r
HORIZON = 100                       # CWON 2024 asset horizon T (years)

# ---- Smallholder own consumption (steps 01-05) -------------------------------------------------------------------
OC_FIRST_YEAR = 2004                # first year of the own-consumption panel
OC_LAST_YEAR = 2021                 # last year of the own-consumption panel
SMALL_FARM_HA = 2.0                 # farm-size cut-off (ha), as in Lowder et al. and Ricciardi et al.

# Own-consumption share o used for each RuLIS survey:
#   'lt2ha'       share of farms < SMALL_FARM_HA (RuLIS groups weighted by their land below the cut-off)
#   'small_scale' RuLIS small-scale food producers (bottom 40% definition, SDG 2.3)
#   'national'    RuLIS national figure
# A survey that lacks the chosen basis takes another RuLIS share scaled to it (flagged in own_share_basis).
OWN_SHARE_BASIS = 'lt2ha'

# Sources of the smallholder share a, in the order they are tried (the first available wins)
A_TIER_ORDER = ('ricciardi_observed', 'ricciardi_area', 'rulis', 'lowder')
RICCIARDI_MIN_CROPS = 5             # a Ricciardi country with fewer crops is not used
RICCIARDI_MIN_OBSERVED = 0.5        # share of production value that must be observed (not filled with one yield
                                    # for all farm sizes) for the tier 'ricciardi_observed'
RICCIARDI_MIN_COVERAGE = 0.2        # survey-based Ricciardi countries cover farm households only: their share is
                                    # scaled by survey crop area / FAOSTAT crop area (capped at 1); below this
                                    # coverage, or if it cannot be computed, the country is not used
SMALL_FARM_CROPLAND_FRACTION = 1.0  # share of Lowder's farm area below the cut-off that is cropland
YIELD_RATIO = 'ricciardi'           # yield of small farms relative to larger farms, used to turn area shares into
                                    # value shares: 'ricciardi' (pooled from Ricciardi observed data) or a number
                                    # (1.0 = same yield)
YIELD_RATIO_BOUNDS = (0.5, 2.0)     # plausible range of the yield ratio
PRICE_YEARS = (2008, 2016)          # producer prices used to value Ricciardi crops (global median per crop)

# Yearly path of the survey shares between and beyond surveys (step 03):
#   'interpolate'  linear between surveys, nearest survey held before the first and after the last
#   'linear_fit'   straight line fitted through all surveys of a country (smooths noisy series), held at its
#                  value of the first / last survey year outside the survey years
TIME_PATH = 'interpolate'
A_TIME_VARYING = True               # a from RuLIS follows the same yearly path as o
MAX_SURVEY_AGE = None               # years; a year further than this from every survey gets the regional median
                                    # instead of a held share (None = always hold)
MIN_COUNTRIES_FOR_REGIONAL_MEDIAN = 5   # imputation: region, else UN region (continent), else global median

# World Bank income groups left out of the GEP panel. One classification for every year: the World Bank historical
# classification (OGHIST) based on the GNI per capita of INCOME_GROUP_YEAR. () keeps all countries. Excluded
# countries are still computed, written to the table of excluded countries, and still serve as donors for regional
# medians.
EXCLUDE_INCOME_GROUPS = ('High income', 'Upper middle income')
INCOME_GROUP_YEAR = None            # year of the GNI per capita the classification is based on (OGHIST row "Data for
                                    # calendar year"); None = BASE_YEAR. 2019 gives FY21, published July 2020.

# Income groups of countries and territories the World Bank classification of INCOME_GROUP_YEAR does not give; used
# only where it has none:
#   GLP, GUF, MTQ, REU  French overseas departments (Guadeloupe, French Guiana, Martinique, Reunion), part of France;
#                       not in the World Bank classification
#   COK                 Cook Islands, not in the World Bank classification; left the OECD DAC list of ODA recipients
#                       in 2020 as a high-income country
#   NIU                 Niue, not in the World Bank classification; upper middle income on the OECD DAC list of ODA
#                       recipients
#   VEN                 Venezuela, unclassified for GNI years 2020-2024 (FY22-FY26); the World Bank gives upper middle
#                       income for 2019 (FY21) and lower middle income for 2025 (FY27)
INCOME_GROUP_ADDITIONS = {'GLP': 'High income', 'GUF': 'High income', 'MTQ': 'High income', 'REU': 'High income',
                          'COK': 'High income', 'NIU': 'Upper middle income', 'VEN': 'Upper middle income'}

# Own-consumption share o (%) for a country without a RuLIS survey, from another source. Used for every year
# instead of the regional median (flagged in own_con_source).
OWN_SHARE_OVERRIDES = {
    # China: China Household Finance Survey 2015-2019 (24,678 rural household observations): mean share of crop
    # output value sold = 52.7% (Land 2024, 13(12), 2058, Table 1). Not sold = 47.3%: an upper bound for own
    # consumption (it also includes seed, feed, storage and gifts; household mean, not value-weighted).
    'CHN': (47.3, 'CHFS 2015-2019: 100 - 52.7% of crop output value sold (upper bound)'),
}

# Crop production value V (step 05):
#   'faostat'       FAOSTAT QV "Crops" (current USD) only. Countries and years FAOSTAT does not value (Uganda after
#                   1998, DR Congo, Haiti, Zimbabwe 2019-20, ...) are left out.
#   'faostat_fill'  FAOSTAT where it reports; elsewhere the gross value of step 04 (commercial crop provision).
#   'commercial'    the gross value of step 04 for every country, so subsistence and commercial crop provision
#                   rest on the same value.
# Years after the last year of step 04: FAOSTAT x the country's step 04 / FAOSTAT ratio of that last year where
# FAOSTAT reports, otherwise the last-year value of step 04 held (flagged).
V_SOURCE = 'commercial'

# Breaks in the value series (country -> last year before the break). From the year after it,
# V(t) = V(year) x production(t) at year prices / production(year) at year prices, crop by crop from the crop table
# of step 04: the series keeps the quantity change but not the price jump.
# Egypt: FAOSTAT QV doubles from 2018 to 2019 at flat production (every major crop x2-3.8).
V_BREAK_FIX = {}                    # sensitivity: {'EGY': 2018}

# ---- Commercial crop provision (step 04) -------------------------------------------------------------------------
METHOD = 'cwon'                     # 'gep' (the options below) or 'cwon' (CWON 2024 exactly; the options below
                                    # are then not used)
COMMERCIAL_FIRST_YEAR = 1995        # first year of the CWON rental rates (and of CWON's balance sheet)
OUTLIER_RULE = 'world_median_ratio'    # 'world_median_ratio' (drop prices above MAX_RATIO_TO_WORLD_MEDIAN x the
                                    # world median; global_invest, crop_benefits), 'cwon_iqr' (CWON: prices at or
                                    # above the median + CWON_IQR_MULTIPLIER x IQR -> median) or 'none'
CROP_LIST = 'faostat'               # 'faostat' (FAOSTAT QV primary crops minus group totals and processed
                                    # products) or 'cwon' (CWON's 159 wealth crops, land_crop_list.csv)
VALUE_BASIS = 'reported_first'      # 'reported_first' (FAO reported value, production x price for the gaps) or
                                    # 'production_x_price' (every crop-country-year at production x price)
REGIONAL_PRICE = 'weighted_median'  # 'weighted_median' (weighted by each country's production) or 'median'
USD_COPY_FX_TOLERANCE = 0.10        # a USD price equal to the SLC price is a copy unless |fx - 1| <= this
USD_COPY_RTOL = 1e-9                # relative difference below which a USD price counts as equal to the SLC price
MAX_RATIO_TO_WORLD_MEDIAN = 20.0    # OUTLIER_RULE 'world_median_ratio': prices above this x the world median of
                                    # the crop and year are dropped
CWON_IQR_MULTIPLIER = 1.5           # CWON outlier rule: value >= median + this x interquartile range -> median

# METHOD = 'cwon' (CWON 2024, land.do in the World Bank reproducibility package FR_WLD_2024_195)
CWON_FIRST_YEAR = 1970              # first price and production year (BASE_YEAR in Wealth_master_updater.do)
CWON_TARGET_YEAR = 2020             # last year (TARGET_YEAR in Wealth_master_updater.do)
CWON_PUBLISHED_2020_WEALTH_BN = 16840   # CWON 2024 published 2020 crop wealth, bn USD
CWON_ANNUITY_FACTOR = 24.505        # CWON 2024 wealth / rent: (1 - 1.04^-100) / 0.04

# =====================================================================================================================
# 2. Fixed codes and tables
# =====================================================================================================================

# ---- FAOSTAT element, item and area codes (stable across releases, unlike names and units) ------------------------
EL_PRODUCTION = 5510                # Production (tonnes)
EL_PRICE_USD = 5532                 # Producer Price (USD/tonne)
EL_PRICE_SLC = 5531                 # Producer Price (SLC/tonne)
EL_VALUE_USD = 57                   # Gross Production Value (current thousand US$)
EL_VALUE_SLC = 56                   # Gross Production Value (current thousand SLC)
EL_EXPORT_QTY = 5910                # Export Quantity (tonnes)
EL_EXPORT_VALUE = 5922              # Export Value (thousand US$)
ANNUAL_VALUE = 7021                 # Months Code of the annual producer price
FAO_CHINA_AGGREGATE = 351           # FAO "China" = mainland + Taiwan + Hong Kong + Macao (dropped)
FAO_BELGIUM_LUXEMBOURG = 15         # FAO area code of Belgium-Luxembourg (before 2000)
FAO_FIRST_REGION_CODE = 5000        # FAO area codes from here on are region aggregates
FAO_FIRST_AGGREGATE_ITEM_CODE = 1700    # FAO item codes from here on are group totals and aggregates
FIRST_LIVESTOCK_ITEM_CODE = 866     # FAO primary crops have item codes below the livestock block
FAO_QV_CROPS_ITEM_CODE = 2041       # FAOSTAT QV "Crops" (total of all crops)
# FAO item group totals and aggregates; excluded so no crop is counted twice
FAO_GROUP_TOTALS = {1717, 1720, 1723, 1726, 1729, 1730, 1732, 1735, 1738, 1739, 1753, 1765, 1770,
                    1780, 1804, 1814, 1816, 1817, 1841, 2041, 2044, 2051, 2054, 2057}
# Processed or by-products with crop-range codes (the items CWON marks wealth_crop == 0); their primary crop is
# already valued (cotton lint and cottonseed <- seed cotton; palm oil and kernels <- oil palm fruit; cassava leaves
# <- cassava; kapok fibre and seed <- kapok fruit)
FAO_PROCESSED_ITEMS = {256, 257, 311, 329, 378, 767, 778, 839}
# M49 codes that FAOSTAT files use for a country whose successor is in the ISO table
M49_SUCCESSORS = {159: 156,         # China, mainland in releases that code it 159
                  891: 688,         # Serbia and Montenegro -> Serbia
                  200: 203,         # Czechoslovakia -> Czechia
                  230: 231,         # Ethiopia PDR -> Ethiopia
                  736: 729}         # Sudan (former) -> Sudan

# ---- Commercial crop provision (step 04) -------------------------------------------------------------------------
CROP_YEAR_KEYS = ['alpha-3', 'item_code', 'Year']       # one row per country, crop and year
REGION_OVERRIDES = {'TWN': ('Eastern Asia', 'Asia')}     # (subregion, UN region) where the ISO table has none
                                                        # (Taiwan); used by step 04 and the imputation of step 05
BLX_SPLIT_YEAR = 2000               # before this year FAOSTAT reports Belgium-Luxembourg; split by this year's shares
BLX_LAND_AREA_KM2 = {'BEL': 30280, 'LUX': 2590}         # land areas, the split of crops without shares (land.do)
# Crops without prices of their own take a related crop's price (CWON land.do): sugar crops nes <- mean of sugar
# cane and beet; jojoba, tallowtree <- oilseeds nes; coir, hemp tow <- fibre crops nes
PRICE_SUBSTITUTES = {161: [156, 157], 277: [339], 305: [339], 813: [821], 777: [821]}
CWON_DROPPED_COUNTRIES = {'ASM', 'GUM', 'CYM', 'BMU', 'GRL', 'LIE', 'VIR'}   # land.do drops these
CWON_TRADE_ITEM_MAP = {1946: 27, 1980: 782}     # land.do recodes these trade items
# CWON price order: column of the price table and the price_source label it gets
CWON_ORDER = [('uv', 'FAO unit value'), ('pp', 'FAO producer price'),
              ('reg_uv', 'unit value, regional avg'), ('reg_pp', 'producer price, regional avg'),
              ('wld_uv', 'unit value, world avg'), ('wld_pp', 'producer price, world avg'),
              ('euv', 'export unit value'), ('reg_euv', 'export UV, regional avg'),
              ('wld_euv', 'export UV, world avg')]
# price_source labels of prices taken from other countries (regional or world prices), by method
REGIONAL_PRICE_SOURCES = ('subregion median', 'region median', 'world median',
                          'unit value, regional avg', 'producer price, regional avg', 'unit value, world avg',
                          'producer price, world avg', 'export UV, regional avg', 'export UV, world avg')
N_LARGEST_PRINTED = 10              # largest values from production x price printed for checking

# ---- Country names ----------------------------------------------------------------------------------------------
# Names that neither the ISO table nor the World Bank table resolves (normalised form -> ISO3)
ISO3_ALIASES = {
    'democratic republic of the congo': 'COD', 'congo dem rep': 'COD', 'congo rep': 'COG',
    'united republic of tanzania': 'TZA', 'tanzania': 'TZA', 'republic of moldova': 'MDA',
    'egypt arab rep': 'EGY', 'gambia the': 'GMB', 'yemen rep': 'YEM', 'kyrgyz republic': 'KGZ',
    'lao pdr': 'LAO', 'micronesia fed sts': 'FSM', 'korea dem people s rep': 'PRK',
    'democratic people s republic of korea': 'PRK', 'republic of korea': 'KOR', 'korea rep': 'KOR',
    'iran islamic rep': 'IRN', 'venezuela rb': 'VEN', 'cote d ivoire': 'CIV', 'turkiye': 'TUR',
    'turkey': 'TUR', 'slovak republic': 'SVK', 'st lucia': 'LCA', 'st vincent and the grenadines': 'VCT',
    'st kitts and nevis': 'KNA', 'sao tome and principe': 'STP', 'swaziland': 'SWZ', 'eswatini': 'SWZ',
    'west bank and gaza': 'PSE', 'palestine': 'PSE', 'kosovo': 'XKX', 'vietnam': 'VNM',
    'viet nam': 'VNM', 'bolivia': 'BOL', 'china mainland': 'CHN', 'bahamas the': 'BHS',
    'cape verde': 'CPV', 'cabo verde': 'CPV', 'russian federation': 'RUS', 'czech republic': 'CZE',
    'macedonia fyr': 'MKD', 'north macedonia': 'MKD', 'hong kong sar china': 'HKG',
    'macao sar china': 'MAC', 'netherlands kingdom of the': 'NLD', 'timor leste': 'TLS',
    'netherlands': 'NLD', 'united kingdom': 'GBR', 'united kingdom of great britain and northern ireland': 'GBR',
    'french guyana': 'GUF', 'french guiana': 'GUF', 'united states virgin islands': 'VIR',
    'bolivia plurinational state of': 'BOL', 'guinea bissau': 'GNB', 'iran islamic republic of': 'IRN',
    'venezuela bolivarian republic of': 'VEN', 'lao people s democratic republic': 'LAO',
    'micronesia federated states of': 'FSM',
}

# ---- World Bank income classification (step 05) ---------------------------------------------------------------
WB_INCOME_SHEET = 'Country Analytical History'     # OGHIST sheet with the group of each economy by fiscal year
WB_INCOME_CODES = {'L': 'Low income', 'LM': 'Lower middle income', 'UM': 'Upper middle income',
                   'H': 'High income'}             # OGHIST codes -> group names ('..' or empty: not classified)

# ---- RuLIS (step 01) --------------------------------------------------------------------------------------------
# FAOSTAT RuLIS indicator codes used (Rural Livelihoods Indicators, normalized bulk file)
RULIS_CODES = {
    24254: 'own',          # Value of crop used for own consumption, share of total value of crop production (%)
    24294: 'cultivated',   # Average cultivated land area (ha)
    24235: 'hh',           # Total number of households in the country (by group)
    24234: 'ssfp_share',   # Small-scale food producers, share of total agricultural households (%)
}
RULIS_GROUPS = {'N': 'N', 'R': 'R', 'U': 'U', 'SF': 'SF', 'NSF': 'NSF'}
RULIS_OLD_GROUPS = {'National': 'N', 'Rural': 'R', 'Urban': 'U', 'Small holder farms': 'SF',
                    'Non-small holder farms': 'NSF'}
# Small-scale producers' share of agricultural households (fraction) within which the households of one farm
# group can be derived from the other, and the share can weight the groups
SMALL_SCALE_SHARE_LIMITS = (0.001, 0.999)

# ---- Smallholder share (step 02) --------------------------------------------------------------------------------
MIN_CROPS_FOR_YIELD_RATIO = 3       # fewest Ricciardi crops with a yield ratio for a country's ratio to count
MIN_COUNTRIES_FOR_COMPARISON = 3    # fewest countries with two sources for the printed comparison of the sources

# ---- Paper tables, figure and map (step 07) ---------------------------------------------------------------------
TOP_COUNTRIES = 10                  # countries in the table of the largest base-year GEP
FIGURE_DPI = 300                    # resolution of the PNG figures
MAP_EXCLUDED_REGIONS = ('ATA',)     # ee_r264 regions left off the map (Antarctica)

# ---- Checks (validate.py) ---------------------------------------------------------------------------------------
CHECK_RTOL = 1e-9                   # relative tolerance of the checks that recompute a value exactly
CHECK_RTOL_ROUNDED = 1e-6           # relative tolerance where values were summed in a different order
CHECK_RTOL_WEALTH = 1e-3            # relative tolerance of crop wealth = rent x CWON_ANNUITY_FACTOR
CHECK_INTERPOLATION_TOLERANCE = 1e-6    # largest difference (points) of an interpolated share from the straight line
CHECK_MAX_OWN_SHARE_OF_VALUE = 0.5  # flag own consumption above this share of the crop production value
CHECK_MAX_SURVEY_JUMP = 20          # flag own shares that change more than this (points) between two surveys
CHECK_MAX_YEARS_HELD = 10           # flag shares held more than this many years from a survey
CHECK_MAX_SOURCE_SPREAD = 25        # flag countries whose smallholder-share sources differ by more (points)
CHECK_MAX_AREA_COVERAGE = 1.2       # flag ricciardi_area where census area exceeds this x FAO cropland
CHECK_OLD_SOURCE_YEAR = 2000        # flag smallholder shares from a source older than this year
CHECK_MAX_CWON_DEVIATION_PCT = 5    # flag a commercial target-year rent this far (%) from CWON's published one
CHECK_MAX_YEAR_CHANGE = 0.5         # flag gross values that change more than this (share) from one year to the next
CHECK_LARGE_COUNTRY_USD = 1e9       # ... in countries with a gross value above this
CHECK_MAX_REGIONAL_SHARE = 0.25     # flag countries with more than this share of gross value from regional prices
CHECK_MAX_UNIT_VALUE_GAP = 0.05     # flag unit-value crops this far (share) from the FAO reported value
CHECK_MAX_VALUE_RATIO_GAP = 0.3     # flag own-consumption crop value this far (share) from the commercial value
CHECK_ROWS_SHOWN = 15               # rows printed per flag

# ---- Comparison of two runs (compare_runs.py) ---------------------------------------------------------------------
COMPARE_RTOL = 1e-9                 # relative tolerance for numbers in CSV files
COMPARE_ROWS_SHOWN = 5              # rows listed per differing column
COMPARE_KEY_COLUMNS = 3             # non-float columns used to name a row
COMPARE_TEXT_SHOWN = 120            # characters shown of a differing text line
COMPARE_TEXT_SUFFIXES = ('.txt', '.md', '.tex', '.yaml', '.json')   # compared line by line

# =====================================================================================================================
# 3. Paths
# =====================================================================================================================

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / 'input'
RESULTS_DIR = ROOT / 'results'                  # one folder per run: <RESULTS_DIR>/<date>/intermediates, /outputs
RUN_FOLDER_FORMAT = '%Y-%m-%d_%H-%M'            # name of the run folder, e.g. 2026-11-11_16-05
RUN_FOLDER_FORMAT_SECONDS = '%Y-%m-%d_%H-%M-%S' # used when a folder of the same minute exists
RUN_SETTINGS_FILE = 'run_settings.yaml'         # settings and versions of a run, in its folder

# Input files, by key: file names in INPUT_DIR
INPUTS = {
    'iso': 'ISO-3-codes.csv',
    'wb_income': 'WBincomegroup.csv',
    'wb_income_history': 'OGHIST_2026_10_08.xlsx',
    'cpi': 'CPI_WB.csv',
    'rental_rates': 'land_ef_regional_cropland_rental_rates_new.csv',
    'rulis_faostat': 'Rural_Livelihoods_Indicators_E_All_Data_Normalized.csv',
    'rulis_old': 'FAO_data2.csv',
    'ricciardi': 'FarmSize_data_fullyProcessed.csv',
    'lowder_country': 'lowder_2021_country.xlsx',
    'land_use': 'Inputs_LandUse_E_All_Data.csv',
    'production': 'Production_Crops_Livestock_E_All_Data.csv',
    'prices': 'Prices_E_All_Data.csv',
    'production_value': 'Value_of_Production_E_All_Data.csv',
    'trade': 'Trade_CropsLivestock_E_All_Data.csv',
    'wdi_fx': 'API_PA.NUS.ATLS_DS2_en_csv_v2_3895.csv',
    'crop_list': 'land_crop_list.csv',
    'ee_r264': 'ee_r264_correspondence.gpkg',
}

# Intermediate files, by key: file names in <run folder>/intermediates; the number is the step that writes them
INTERMEDIATES = {
    'rulis_surveys': '01_rulis_surveys.csv',
    'own_share_observed': '01_own_share_observed.csv',
    'smallholder_share': '02_smallholder_share.csv',
    'smallholder_share_candidates': '02_smallholder_share_candidates.csv',
    'smallholder_share_rulis_surveys': '02_smallholder_share_rulis_surveys.csv',
    'yield_ratio': '02_yield_ratio.csv',
    'yield_ratio_by_country': '02_yield_ratio_by_country.csv',
    'own_share_panel': '03_own_share_panel.csv',
    'smallholder_share_panel': '03_smallholder_share_panel.csv',
    'cpi_index': '04_cpi_index.csv',
}

# Output files, by key: file names in <run folder>/outputs ({base_year} is filled in with BASE_YEAR; a figure is
# written as .png)
OUTPUTS = {
    'commercial_by_crop': 'agr_commercial_by_country_year_crop.csv',
    'commercial_by_country': 'agr_commercial_CWON.csv',
    'commercial_price_sources': 'agr_commercial_price_sources.csv',
    'own_consumption_panel': 'own_consumption_panel.csv',
    'own_consumption_base_year': 'own_consumption_{base_year}.csv',
    'own_consumption_summary': 'own_consumption_summary_{base_year}.csv',
    'own_consumption_share_imputation': 'own_consumption_share_imputation.csv',
    'own_consumption_excluded': 'own_consumption_excluded_{base_year}.csv',
    'subsistence': 'agr_subsistence_CWON.csv',
    'crop_provision_panel': 'gep_crop_provision_panel.csv',
    'table_key_statistics': 'table_01_key_statistics.csv',
    'table_top_countries': 'table_02_top_10_countries_{base_year}.csv',
    'table_appendix': 'table_03_appendix_all_countries.csv',
    'figure_global_gep': 'figure_05_global_gep_annual_levels',
    'figure_gep_map': 'figure_06_subsistence_gep_map_{base_year}',
}
