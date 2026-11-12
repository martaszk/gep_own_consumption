# Changes

Newest first. Differences of the method from its previous version are described in
[comparison_ver.old_new.md](comparison_ver.old_new.md).

## 2026-11-11: map of the subsistence GEP in step 07; step 08 and its ee_r264 export removed

Step 07 draws a new output, `figure_06_subsistence_gep_map_2019.png`: the 2019 subsistence GEP by country on the
regions of `input/ee_r264_correspondence.gpkg`, in five quantile classes, Equal Earth projection, without
Antarctica. A region takes the value of the country whose ISO3 code is its own code (`ee_r264_label`), so each of the
79 countries with GEP is drawn once. The GeoPackage is back in `input/` (from Git LFS) and is read with `sqlite3`
and `shapely`, so GDAL is still not needed; `shapely` is added to `requirements.txt`.

Step 08 is removed together with its output `gep_agr_crop_subsistence_ee_r264.csv` and its input
`ee_r264_correspondence.csv`. That export joined the regions on `adm0_a3`: it repeated India's value in six rows,
Pakistan's and Morocco's in two, left out Palestine and South Sudan (whose `adm0_a3` codes are ISR and SDS), and its
column summed to about twice the subsistence GEP. All other result files are identical to those of the run before
the change (`compare_runs.py`: 24 identical; missing only the removed export and the new map).

## 2026-11-11: ee_r264 correspondence as CSV; GDAL no longer needed

Step 08 read `input/ee_r264_correspondence.gpkg` (84 MB) with geopandas, using only its attribute table. The
GeoPackage needed GDAL, and in a terminal with a conda environment active, conda's `GDAL_DRIVER_PATH` made the GDAL
of pyogrio try to load conda's plugins built for another GDAL version (`ERROR 1: Can't load requested DLL:
...\gdalplugins\gdal_HDF5.dll`). The attribute table (264 rows, 38 columns) is now `input/ee_r264_correspondence.csv`
(96 KB), read with pandas; the GeoPackage was removed from `input/`. geopandas and pyogrio are no longer required.
The CSV reads back identical to the attribute table of the GeoPackage, and every result file is identical to that
of a run with the GeoPackage.

## 2026-11-11: income groups of the base year (values change)

The scope (`EXCLUDE_INCOME_GROUPS`) used the income groups of `WBincomegroup.csv`, the World Bank classification of
July 2024 (FY25, based on the GNI per capita of 2023), whatever the base year. The groups now come from the World
Bank historical classification `input/OGHIST_2026_10_08.xlsx`, in the classification based on the GNI per capita of
the base year: FY21 (published July 2020) for 2019. `INCOME_GROUP_YEAR` (default None, the base year) selects another
year. `WBincomegroup.csv` is still read for the World Bank regions and the country names; its income groups are no
longer used. They equal the FY25 column of OGHIST for every economy, which confirms the date of the file.

Effect on the default run, 2019 unless stated:

| Country | Group, FY25 → FY21 | Panel | Own consumption | Subsistence GEP | GEP 2004–2021, 2019 USD |
|---|---|---|---|---|---|
| Algeria | upper → lower middle | enters | 231.1 mn USD | 111.4 mn USD | 1,623.5 mn USD |
| Ukraine | upper → lower middle | enters | 111.4 mn USD | 8.9 mn USD | 208.7 mn USD |
| El Salvador | upper → lower middle | enters | 95.3 mn USD | 21.4 mn USD | 412.0 mn USD |
| Moldova | upper → lower middle | enters | 5.0 mn USD | 0.4 mn USD | 10.2 mn USD |
| Mongolia | upper → lower middle | enters | 2.4 mn USD | 0.6 mn USD | 19.5 mn USD |
| Lebanon | lower → upper middle | leaves | 245.7 mn USD | 56.5 mn USD | 700.0 mn USD |
| Jordan | lower → upper middle | leaves | 54.8 mn USD | 12.6 mn USD | 190.2 mn USD |
| Samoa | lower → upper middle | leaves | 6.1 mn USD | 2.0 mn USD | 61.6 mn USD |

2019: own consumption 77.61 → 77.75 bn USD (77 → 79 countries; 10.3% → 9.7% of their crop value); subsistence GEP
25.45 → 25.52 bn USD; total − subsistence 688.81 → 688.74 bn USD. The panel has 1414 country-years instead of 1378,
and the average annual GEP in table 1 is 28.35 instead of 28.27 bn 2019 USD. Seven other countries in the results
change group without changing scope: Bulgaria, Guyana and Russia from high to upper middle income, Mauritius from
upper middle to high income, Guinea, Haiti and Tajikistan from lower middle to low income. Venezuela is upper middle
income in FY21, so its entry in `INCOME_GROUP_ADDITIONS` is used only for GNI years 2020–2024. Without the rows of
the eight countries and the column `income_group`, every result file is identical to that of the previous run.

## 2026-11-11: paper tables and figure in 2019 USD, countries counted with a GEP value (values change)

The paper tables and the figure (step 07) were labelled "2019 USD" but summed `gep_value`, which is in current USD, so
the series, the average annual GEP and the percent changes included inflation. They now use `gep_value_2019`. Table
1 counts countries and observations only where there is a GEP value; before, countries without a CWON rental rate
(no GEP) were counted too. Coverage statistics follow the same definition.

Effect on the default run: the average annual global GEP in table 1 is 28.27 instead of 25.26 bn 2019 USD; the
first and last values and the percent changes of table 3 and the figure are in 2019 USD; the 2019 values (table 1,
table 2) are unchanged. The number of countries stays 77, because every country in the panel has a rental rate
since the previous change (before it, 84 countries were counted and 78 had a GEP value).

## 2026-11-11: Taiwan's UN region in the own-consumption imputation (values change)

The ISO table gives Taiwan no region. `REGION_OVERRIDES` (Eastern Asia, Asia) was used by the commercial step only;
the imputation of step 05 now uses it too. Taiwan is a high-income country, so it is not in the panel and is no
donor; the change touches one row of `own_consumption_excluded_2019.csv`: its own-consumption share is the median of
Asia (30.3%, 11 countries) instead of the global median (41.5%), and its 2019 own consumption 352.4 instead of
482.7 mn USD. Every other result file is unchanged.

## 2026-11-11: income groups for seven territories (values change)

`WBincomegroup.csv` gives Venezuela no income group and does not list Guadeloupe, French Guiana, Martinique,
Réunion, the Cook Islands and Niue, so `EXCLUDE_INCOME_GROUPS` never left them out. `INCOME_GROUP_ADDITIONS` in
`consts.py` now gives them a group (the basis of each is noted there); it is used only where the World Bank file has
none. With the default scope all seven leave the panel:

| Country | Rows in the panel | Own consumption 2019 | Subsistence GEP 2019 | Subsistence GEP 2004–2021 |
|---|---|---|---|---|
| Venezuela | 18 | 22.9 mn USD | 5.1 mn USD | 263.2 mn USD |
| Cook Islands, Niue | 18 each | 0.3 and 0.6 mn USD | none (no CWON rental rate) | none |
| Guadeloupe, French Guiana, Martinique, Réunion | 3 each (2004–2006) | — | none (no CWON rental rate) | none |

2019: own consumption 77.64 → 77.61 bn USD (80 → 77 countries); subsistence GEP 25.46 → 25.45 bn USD (78 → 77
countries). The panel has 77 countries instead of 84 and 1378 country-years instead of 1444; the paper tables follow.
A country without a group now has an empty `income_group` cell instead of the text "nan".

## 2026-11-11: restructured code, same results

The code was reorganised without changing the method or the values of the results. The work was checked stage by
stage against the results of the old code for four settings scenarios (default; `METHOD='cwon'`; two combinations
covering the other options), with `compare_runs.py`.

### Running

- One entry point: `python run.py` runs all steps in one pass, in file order. Before, the scripts had to run in the
  order 01, 02, 03, 06, 04, 05, 06, because 04 read an output of 06 and 06 read an output of 05.
- The steps pass their tables in memory; no step reads a result file.
- Every run writes to its own folder `results/<YYYY-MM-DD_HH-MM>/` with `intermediates/`, `outputs/` and
  `run_settings.yaml` (all settings, overrides, git commit, package versions, result of the checks).
- `--set NAME=VALUE` overrides any value of `consts.py` for one run; `--until`, `--no-intermediates`, `--no-validate`
  and `--tag` are the other options.
- `compare_runs.py` compares the files of two run folders.

### Files

| Before | After |
|---|---|
| `01-construct-data-own-consume.py` | `step_01_rulis_own_share.py` |
| `02-construct-smallholder-share.py` | `step_02_smallholder_share.py` |
| `03-interplote-missing-data.py` | `step_03_yearly_share_paths.py` |
| `06-crop-provision-commercial (5).py` | `step_04_commercial_crop_provision.py` (without the panel) |
| `04-extrapolate-data.py` | `step_05_own_consumption.py` |
| `05-create-gep-panel.py` | `step_06_gep_panel.py` (with the crop provision panel) |
| `07-analyze-summary-stats.py`, `08-generate-paper-outputs.py` | `step_07_paper_outputs.py` |
| `09-export-gep-ee-r250.py` | `step_08_ee_r264_export.py`, reading `input/ee_r264_correspondence.gpkg` |
| `gep_settings.py`, `own_consumption_settings.py`, settings at the top and middle of the commercial script | `consts.py` (settings, codes, paths), `utils.py` (shared helpers), helpers of one step moved into it |
| `validate_crop_panel.py`, `validate_subsistence.py` | `validate.py`, run by `run.py` |
| `README (1).md`, `own_consumption_method (1).md` | `README.md`, `changes.md`, `comparison_ver.old_new.md` |
| — | `run.py`, `compare_runs.py`, `requirements.txt`, `.gitignore`, `.gitattributes` |

Removed, because they could not run (missing inputs) or were one-off edits: `create_gep_map_png.py`,
`create_gep_png_map.py`, `create_gep_map_simple.py`, `generate_map_and_appendix.py`,
`generate_appendix_markdown.py`, `update_map_section.py`. They remain in the first commit of the repository.

`input/` keeps only the files the code reads. The extracted subfolders and the two zip archives were removed; a copy
of the whole folder as of 2026-11-11 is the local `input.zip`. Input CSV files and the gpkg are stored in Git LFS.

### Result files

| Before | After (`results/<run>/...`) |
|---|---|
| `intermediates/rulis-surveys.csv` | `intermediates/01_rulis_surveys.csv` |
| `intermediates/data-own-consumption-shares-observed.csv` | `intermediates/01_own_share_observed.csv` |
| `intermediates/smallholder-share.csv` | `intermediates/02_smallholder_share.csv` |
| `intermediates/smallholder-share-candidates.csv` | `intermediates/02_smallholder_share_candidates.csv` |
| `intermediates/smallholder-share-rulis-surveys.csv` | `intermediates/02_smallholder_share_rulis_surveys.csv` |
| `intermediates/smallholder-yield-ratio.csv` | `intermediates/02_yield_ratio.csv` |
| `intermediates/smallholder-yield-ratio-by-country.csv` | `intermediates/02_yield_ratio_by_country.csv` |
| `intermediates/data-own-consumption-shares.csv` | `intermediates/03_own_share_panel.csv` |
| `intermediates/smallholder-share-panel.csv` | `intermediates/03_smallholder_share_panel.csv` |
| `intermediates/CPI_WorldBank.csv` | `intermediates/04_cpi_index.csv` |
| `output/agr_commercial_by_country_year_crop.csv`, `output/agr_commercial_CWON.csv`, `output/agr_commercial_price_sources.csv` | same names in `outputs/` |
| `intermediates/data-own-consumption-extrapolation.csv` | `outputs/own_consumption_panel.csv` |
| `results/own-consumption-2019.csv` | `outputs/own_consumption_2019.csv` |
| `results/own-consumption-summary-2019.csv` | `outputs/own_consumption_summary_2019.csv` |
| `results/own-consumption-share-imputation.csv` | `outputs/own_consumption_share_imputation.csv` |
| `results/own-consumption-excluded-2019.csv` | `outputs/own_consumption_excluded_2019.csv` |
| `output/agr_subsitence_CWON.csv` and `output/agr_subsistence_adjusted_2020.csv` | one file `outputs/agr_subsistence_CWON.csv` |
| `output/gep-crop-provision-panel.csv` | `outputs/gep_crop_provision_panel.csv` |
| `output/table_0*.csv`, `coverage_statistics.txt`, `figure_05_global_gep_annual_levels.png/.pdf` | same names in `outputs/` |
| `output/global_gep_annual_levels.png/.pdf` | removed (the same figure as `figure_05`) |
| `output/REPRODUCIBLE_OUTPUTS_SUMMARY.txt` | removed (repeated table 1, held outdated instructions) |
| `output/gep-agr-crop-subsistence.csv` (09, could not run) | `outputs/gep_agr_crop_subsistence_ee_r264.csv` |

Changes inside the result files (no value changed):

- `crop_value_source` labels no longer carry the old script number: "06 gross value (FAOSTAT missing)" became
  "commercial gross value (FAOSTAT missing)"; likewise "06 gross value", "06 gross value of 2023 held" and
  "FAOSTAT x 06/FAOSTAT ratio of 2023".
- Empty columns of the previous method removed: `wb_income`, `own_con_int`, `ppp_factor`, `ppp_factor_source`
  (own-consumption tables), `rental_rate_decadal`, `gep_value_decadal` (subsistence).
- `agr_subsistence_CWON.csv` holds what the two subsistence files held: `gep_value` in current USD and `CPI`,
  `CPI_2019`, `gep_value_2019`.
- The own-consumption tables always have the column `income_group`, and `own_consumption_excluded_2019.csv` is
  always written (empty when no income group is excluded).
- The first column of `own_consumption_summary_2019.csv` is called `group` instead of `index`.
- The PDF figure carries no creation date, so two runs give identical files.
- Numbers differ by at most 1.2e-13 (relative) from the old results, because tables no longer pass through CSV files
  between steps (writing and reading a CSV changed the last digits).
- The setting value `OUTLIER_RULE = 'william'` is now called `'world_median_ratio'`; the rule is the same.
- The paper tables and figure are made in the same run as the data. The files in the old `output/` folder were
  older than the data they described (they matched a run with `V_SOURCE = 'faostat'`: 23.01 bn USD of subsistence
  GEP in 2019).

### Checks

`validate.py` holds the checks of both validators. Checks that failed under settings other than the default, although
the results were right, were corrected: a missing `income_group` column when no income group is excluded; the global
median of o taken from each country's last survey instead of its base-year value; `own_con2 > 0` where a = 0 (USA,
whose Ricciardi data have no production below 2 ha); years missing in a country series with `V_SOURCE = 'faostat'`
(now a flag); the deflator checks with `DEFLATOR = 'country_cpi'`; years beyond `MAX_SURVEY_AGE`, which are imputed
by design. The thresholds and years are taken from `consts.py`.

## Before 2026-11-11

### Script numbering

1. First numbering (old README): `00-gep-county-csv.py` (ee_r250 export), `01-construct-data-own-consume.py`,
   `02-construct-data-covariates.py`, `03-interplote-missing-data.py`, `04-extrapolate-data.py`,
   `05-create-gep-panel.py`, `06-crop-provision-commercial.py`, `07-analyze-summary-stats.py` (was 06),
   `08-generate-paper-outputs.py` (was 07).
2. `02-construct-data-covariates.py` was replaced by `02-construct-smallholder-share.py`.
3. A renumbered variant (`gep_own_consumption_renumbered.zip`) had 04 = commercial, 05 = extrapolate, 06 = GEP panel.
4. The scripts on disk before the refactor kept 04 = extrapolate, 05 = GEP panel, 06 = commercial (with the panel),
   09 = ee_r250 export.

### File edits (from the old README)

- 02: Ryan starts to build covariate data.
- 03: Marta clean up. Marta adds the interpolation run for countries (4) moving in and out of income brackets. Ryan
  review.
- 04: Ryan completes the extrapolation. Marta review.
- 05: Marta adds the CWON (nature's contribution) corrections (done). Marta also adds CWON to the commercial
  agriculture GitHub repository. Marta brings in discounting for the CPI correction (done).
- 06: Ryan starts the summary statistics. Marta helps as she wants.

### Comments from Marta (from the old README)

- We change the column heads to small letters at the end, as the whole has been written with capital letters.
