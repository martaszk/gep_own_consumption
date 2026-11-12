"""Step 02: smallholder share a, the share of a country's crop production value that comes from small farms.

Small farms are farms below ``consts.SMALL_FARM_HA``. All sources are brought to the same quantity before they are
compared or combined:

- ``ricciardi_observed``: Ricciardi et al. (2018) production by farm-size class, valued with FAOSTAT producer
  prices (global median USD/t per crop over ``consts.PRICE_YEARS``): a = value on small farms / value on all
  farms. Used when at least ``consts.RICCIARDI_MIN_OBSERVED`` of the value is observed production, not filled by
  the authors with one yield for all farm sizes.
- ``ricciardi_area``: Ricciardi countries whose production was mostly filled with one yield: crop area by class,
  turned into a value share crop by crop with the yield ratio r, then weighted by crop value.
- ``rulis``: RuLIS land on small farms (step 01: households x mean cultivated area x lognormal share below the
  cut-off), divided by FAOSTAT cropland of the survey year: a_area = land_lt2 / cropland. If household land
  exceeds cropland, a_area is the share of household land on small farms (coverage capped at 1; flagged).
- ``lowder``: Lowder et al. (2021) country table: farm area of small farms x
  ``consts.SMALL_FARM_CROPLAND_FRACTION`` / FAOSTAT cropland of the census year. Lowder's own share is of all
  farmland, pasture included, which understates smallholders where large farms are mostly pasture; dividing by
  cropland avoids that.

Area shares (rulis, lowder, ricciardi_area) become value shares with the yield ratio r of small farms to larger
farms: a = a_area x r / (a_area x r + 1 - a_area). With ``consts.YIELD_RATIO = 'ricciardi'`` r is pooled from the
Ricciardi crops with observed production in both groups: the median across countries of each country's
value-weighted geometric mean, bounded by ``consts.YIELD_RATIO_BOUNDS``.

Each country takes the first source available in ``consts.A_TIER_ORDER``. RuLIS countries keep every survey's
value; step 03 uses them for a over time. Lowder countries whose census has no class below the cut-off
(Argentina, Australia, New Zealand, Zambia) get no share, but the area of their smallest class / cropland is kept
as a_upper_bound_pct, and step 05 caps their imputed share at it. Countries without any source are imputed in
step 05.
"""
import re

import numpy as np
import pandas as pd

import consts
from utils import (attach_iso3_by_name, codes_for_names, input_path, iso3_lookup, load_iso, load_wb_income,
                   read_fao_csv, read_semicolon_or_comma)


def area_to_value_share(area_share_pct, yield_ratio):
    """Convert the area share of small farms into their share of crop value.

    Args:
        area_share_pct: Share of crop area on small farms, in percent (scalar or array).
        yield_ratio: Yield of small farms relative to larger farms (1.0 = same yield).

    Returns:
        Share of crop value from small farms, in percent, same shape as ``area_share_pct``.
    """
    area_share = np.asarray(area_share_pct, dtype=float) / 100.0
    return 100.0 * area_share * yield_ratio / (area_share * yield_ratio + (1.0 - area_share))


def load_cropland(path, iso):
    """Read FAOSTAT cropland per country and year from the Land Use bulk file.

    Args:
        path: FAOSTAT Land Use bulk file (wide layout: one column per year, Y1961, Y1962, ...).
        iso: ISO table from ``utils.load_iso`` (columns m49, alpha-3).

    Returns:
        DataFrame with columns alpha-3, Year and cropland_ha.

    Raises:
        ValueError: The file has no cropland area rows, or an area unit other than ha or 1000 ha.
    """
    print('  Cropland from %s' % path.name)
    table = read_semicolon_or_comma(path, low_memory=False)
    year_columns = [c for c in table.columns if re.fullmatch(r'Y\d{4}', str(c))]
    keep = [c for c in table.columns if c in ('Area Code', 'Area Code (M49)', 'Area', 'Item', 'Element', 'Unit')]
    table = table.melt(id_vars=keep, value_vars=year_columns, var_name='Year', value_name='Value')
    table['Year'] = table['Year'].str[1:]
    code = pd.to_numeric(table['Area Code'], errors='coerce')
    table = table[(code < consts.FAO_FIRST_REGION_CODE) & (code != consts.FAO_CHINA_AGGREGATE)]
    table['Value'] = pd.to_numeric(table['Value'], errors='coerce')
    table['Year'] = pd.to_numeric(table['Year'], errors='coerce')
    table = table.dropna(subset=['Value', 'Year'])
    table['Year'] = table['Year'].astype(int)
    m49 = pd.to_numeric(table['Area Code (M49)'].astype(str).str.replace("'", ''), errors='coerce')
    table['alpha-3'] = m49.replace(consts.M49_SUCCESSORS).map(dict(zip(iso['m49'], iso['alpha-3'])))
    table = table.dropna(subset=['alpha-3'])
    area = table[(table['Element'].astype(str).str.strip() == 'Area') & (table['Item'] == 'Cropland')].copy()
    if area.empty:
        raise ValueError('%s has no Element "Area" rows for item "Cropland".' % path)
    unit = area['Unit'].astype(str).str.strip().str.lower()
    factor = np.where(unit.isin(['1000 ha', 'thousand ha', '1000ha']), 1000.0,
                      np.where(unit.isin(['ha', 'hectares']), 1.0, np.nan))
    if np.isnan(factor).any():
        raise ValueError('Unexpected FAOSTAT area units: %s' % sorted(unit[np.isnan(factor)].unique()))
    area['cropland_ha'] = area['Value'] * factor
    return area.groupby(['alpha-3', 'Year'], as_index=False)['cropland_ha'].first()


def cropland_near(cropland, code, year):
    """Return a country's cropland in the year closest to a given year (ties: the earlier year).

    Args:
        cropland: Cropland table from ``load_cropland``.
        code: ISO3 code.
        year: Year wanted (may be NaN).

    Returns:
        Tuple (cropland_ha, year used); (NaN, NaN) if the country has no cropland or the year is missing.
    """
    country = cropland[cropland['alpha-3'] == code]
    if country.empty or not np.isfinite(year):
        return np.nan, np.nan
    nearest = (country['Year'] - year).abs().sort_values(kind='stable').index[0]
    return country.at[nearest, 'cropland_ha'], country.at[nearest, 'Year']


def read_prices(path, years):
    """Return the global median producer price per FAOSTAT item.

    Args:
        path: FAOSTAT Producer Prices bulk file (wide layout).
        years: (first, last) year of the prices used.

    Returns:
        Series of USD/tonne indexed by FAOSTAT item code.

    Raises:
        ValueError: The file has no annual producer prices in USD/tonne.
    """
    header = read_fao_csv(path, nrows=0).columns
    year_columns = [c for c in header if re.fullmatch(r'Y\d{4}', c) and years[0] <= int(c[1:]) <= years[1]]
    use = (['Area Code', 'Item Code', 'Element Code'] + (['Months Code'] if 'Months Code' in header else [])
           + year_columns)
    prices = read_fao_csv(path, usecols=use, low_memory=False)
    prices = prices[(prices['Element Code'] == consts.EL_PRICE_USD)
                    & (prices['Area Code'] < consts.FAO_FIRST_REGION_CODE)]
    if 'Months Code' in prices:
        prices = prices[prices['Months Code'] == consts.ANNUAL_VALUE]
    if prices.empty:
        raise ValueError('%s has no producer prices in USD/tonne (element %d).' % (path, consts.EL_PRICE_USD))
    long = prices.melt(id_vars=['Item Code'], value_vars=year_columns, value_name='price')
    long['price'] = pd.to_numeric(long['price'], errors='coerce')
    return long[long['price'] > 0].groupby('Item Code')['price'].median()


def read_ricciardi(path, lookup, cut):
    """Read the Ricciardi et al. (2018) farm-size data.

    Args:
        path: ``FarmSize_data_fullyProcessed.csv``.
        lookup: Normalised country name -> ISO3, from ``utils.iso3_lookup``.
        cut: Farm-size cut-off (ha).

    Returns:
        One row per country, crop and farm-size class with alpha-3, area (harvested, else planted, else crop,
        else cultivated area; Area_fix is not used because it holds the FAOSTAT national total where the class
        area is missing), P (production, 0 if missing), observed (production not filled with one yield) and small
        (the class lies below the cut-off). Countries whose name has no ISO3 code are dropped.
    """
    columns = ['Crop', 'Item_Code', 'NAME_0', 'fs_class_min', 'fs_class_max', 'year', 'cen_sur', 'Area_FAO',
               'Harvested_area', 'Planted_area', 'Crop_area', 'Cultivated_area', 'Production', 'Production_fix',
               'Production_fix_dummy']
    ricciardi = pd.read_csv(path, usecols=columns, low_memory=False).rename(columns={'NAME_0': 'Country'})
    ricciardi['alpha-3'] = codes_for_names(ricciardi['Country'], lookup)
    missing = sorted(ricciardi.loc[ricciardi['alpha-3'].isna(), 'Country'].unique())
    if missing:
        print('  Ricciardi: names without ISO3 (dropped): %s' % missing)
    ricciardi = ricciardi.dropna(subset=['alpha-3'])
    ricciardi['area'] = (ricciardi['Harvested_area'].combine_first(ricciardi['Planted_area'])
                         .combine_first(ricciardi['Crop_area']).combine_first(ricciardi['Cultivated_area']))
    ricciardi['P'] = ricciardi['Production_fix'].fillna(0.0)
    ricciardi['observed'] = (ricciardi['Production_fix_dummy'] == 0) & ricciardi['Production'].notna()
    ricciardi['small'] = ricciardi['fs_class_max'].notna() & (ricciardi['fs_class_max'] <= cut)
    return ricciardi


def value_ricciardi(ricciardi, prices):
    """Value the Ricciardi production with the global median producer price of each crop.

    Args:
        ricciardi: Table from ``read_ricciardi``.
        prices: Prices from ``read_prices``.

    Returns:
        Copy of the rows of crops with a price, with the columns price (USD/t) and V (USD).
    """
    ricciardi = ricciardi.copy()
    ricciardi['price'] = ricciardi['Item_Code'].map(prices)
    no_price = ricciardi.loc[ricciardi['price'].isna() & (ricciardi['P'] > 0), 'Crop'].unique()
    print('02: Ricciardi: %d countries, %d crops; %d crops without a producer price (left out): %s'
          % (ricciardi['alpha-3'].nunique(), ricciardi['Crop'].nunique(), len(no_price), sorted(no_price)[:15]))
    ricciardi = ricciardi[ricciardi['price'].notna()].copy()
    ricciardi['V'] = ricciardi['P'] * ricciardi['price']
    return ricciardi


def crop_group_totals(rows):
    """Sum the value and area of one country and crop over its farm-size classes.

    Args:
        rows: Rows of one country and crop from ``value_ricciardi``.

    Returns:
        Series: V, V_small, V_obs (value, of small farms, observed), A, A_small (class areas), A_fao (FAOSTAT
        area), and Vo_small, Vo_large, Ao_small, Ao_large (observed value and area of small and larger farms).
    """
    return pd.Series({
        'V': rows['V'].sum(), 'V_small': rows.loc[rows['small'], 'V'].sum(),
        'V_obs': rows.loc[rows['observed'], 'V'].sum(),
        'A': rows['area'].sum(min_count=1), 'A_small': rows.loc[rows['small'], 'area'].sum(min_count=1),
        'A_fao': rows['Area_FAO'].iloc[0],
        'Vo_small': rows.loc[rows['observed'] & rows['small'], 'V'].sum(),
        'Vo_large': rows.loc[rows['observed'] & ~rows['small'], 'V'].sum(),
        'Ao_small': rows.loc[rows['observed'] & rows['small'], 'area'].sum(min_count=1),
        'Ao_large': rows.loc[rows['observed'] & ~rows['small'], 'area'].sum(min_count=1)})


def ricciardi_crop_totals(ricciardi):
    """Return the totals of ``crop_group_totals`` for every country and crop.

    Args:
        ricciardi: Valued Ricciardi rows from ``value_ricciardi``.

    Returns:
        DataFrame with alpha-3, Crop and the columns of ``crop_group_totals``.
    """
    columns = ['V', 'small', 'observed', 'area', 'Area_FAO']
    return ricciardi.groupby(['alpha-3', 'Crop'])[columns].apply(crop_group_totals).reset_index()


def country_yield_ratio(rows):
    """Return a country's yield ratio: the value-weighted geometric mean of its crops' ratios.

    Args:
        rows: Crops of one country with columns r (yield ratio) and V (value).

    Returns:
        Series with yield_ratio and n_crops_ratio.
    """
    return pd.Series({'yield_ratio': float(np.exp(np.average(np.log(rows['r']), weights=rows['V']))),
                      'n_crops_ratio': len(rows)})


def pooled_yield_ratio(crops, setting, bounds, min_crops, cut):
    """Determine the yield ratio of small farms to larger farms used for area-based shares.

    The ratio of a crop is (observed value per ha of small farms) / (observed value per ha of larger farms). A
    country's ratio is the value-weighted geometric mean over its crops; countries with fewer than ``min_crops``
    crops are not used. The pooled ratio is the median over countries, bounded by ``bounds``.

    Args:
        crops: Crop totals from ``ricciardi_crop_totals``.
        setting: ``consts.YIELD_RATIO``: 'ricciardi' for the pooled ratio, or a number.
        bounds: (lowest, highest) plausible ratio.
        min_crops: Fewest crops with a ratio for a country to count.
        cut: Farm-size cut-off (ha), for the printed message.

    Returns:
        Tuple (ratio used, table of country ratios with alpha-3, yield_ratio, n_crops_ratio). Without any
        country ratio the pooled ratio is 1.0 (same yield).
    """
    usable = (crops[['Vo_small', 'Vo_large', 'Ao_small', 'Ao_large']] > 0).all(axis=1)
    crops = crops.assign(r=np.where(usable, (crops['Vo_small'] / crops['Ao_small'])
                                    / (crops['Vo_large'] / crops['Ao_large']), np.nan))
    by_country = crops.dropna(subset=['r']).groupby('alpha-3')[['r', 'V']].apply(country_yield_ratio).reset_index()
    by_country = by_country[by_country['n_crops_ratio'] >= min_crops]
    if setting == 'ricciardi':
        ratio = float(np.clip(by_country['yield_ratio'].median(), *bounds)) if len(by_country) else 1.0
        print('    yield ratio farms < %g ha / larger farms, by country: %s'
              % (cut, dict(zip(by_country['alpha-3'], by_country['yield_ratio'].round(2)))))
    else:
        ratio = float(setting)
    print('    yield ratio used for area-based shares: r = %.3f (%s)' % (ratio, setting))
    return ratio, by_country


def coverage_of_country(rows):
    """Return the survey crop area of a country as a share of its FAOSTAT crop area.

    Args:
        rows: Crops of one country with columns A and A_fao.

    Returns:
        Coverage (float).
    """
    return rows['A'].sum() / rows['A_fao'].sum()


def country_value_shares(rows):
    """Return a country's small-farm value share, observed value fraction and area-based value share.

    Args:
        rows: Crops of one country with columns V, V_small, V_obs and a_val_k.

    Returns:
        Series with ric_value_share_pct, ric_observed_value_frac and ric_area_based_share_pct (value-weighted mean
        of the crops' area-based value shares); NaN where the country has no value.
    """
    total = rows['V'].sum()
    with_share = rows['a_val_k'].notna()
    return pd.Series({
        'ric_value_share_pct': 100 * rows['V_small'].sum() / total if total > 0 else np.nan,
        'ric_observed_value_frac': rows['V_obs'].sum() / total if total > 0 else np.nan,
        'ric_area_based_share_pct': (np.average(rows.loc[with_share, 'a_val_k'], weights=rows.loc[with_share, 'V'])
                                     if (with_share & (rows['V'] > 0)).any() else np.nan)})


def ricciardi_shares(ricciardi, crops, yield_ratio, cut, bounds, min_coverage, min_crops, min_observed):
    """Compute the two Ricciardi shares of each country and flag the countries that cannot be used.

    Census countries are national. Survey countries cover farm households only, so their shares are scaled by
    coverage (survey crop area / FAOSTAT crop area, capped at 1); they are not used if coverage is unknown or below
    ``min_coverage``. Observed production implies a yield ratio; where it is outside ``bounds`` (self-reported
    production on very small plots, or class areas that do not match production), the observed value share is
    not used and the country falls back to its area-based share.

    Args:
        ricciardi: Valued Ricciardi rows from ``value_ricciardi``.
        crops: Crop totals from ``ricciardi_crop_totals``.
        yield_ratio: Yield ratio from ``pooled_yield_ratio``.
        cut: Farm-size cut-off (ha).
        bounds: (lowest, highest) plausible yield ratio.
        min_coverage: Lowest coverage of a survey country.
        min_crops: Fewest crops of a usable country.
        min_observed: Lowest observed share of production value for ``ricciardi_observed``.

    Returns:
        One row per country with ric_* details, ricciardi_observed and ricciardi_area (% or NaN) and ric_flag
        (reason a country is not used).
    """
    crops = crops.copy()
    crops['a_area_k'] = np.where(crops['A'] > 0, 100 * crops['A_small'] / crops['A'], np.nan)
    crops['a_val_k'] = area_to_value_share(crops['a_area_k'], yield_ratio)

    shares = ricciardi.groupby('alpha-3').agg(ric_year=('year', 'first'), ric_n_crops=('Crop', 'nunique'),
                                              Country=('Country', 'first'), ric_census_or_survey=('cen_sur', 'first'),
                                              ric_small_rows=('small', 'sum')).reset_index()
    coverage = (crops[(crops['A'] > 0) & (crops['A_fao'] > 0)].groupby('alpha-3')[['A', 'A_fao']]
                .apply(coverage_of_country).rename('ric_area_coverage').reset_index())
    shares = shares.merge(coverage, on='alpha-3', how='left')
    totals = crops.groupby('alpha-3')[['V', 'V_small', 'V_obs', 'a_val_k']].apply(country_value_shares).reset_index()
    shares = shares.merge(totals, on='alpha-3', how='left')

    value_share = shares['ric_value_share_pct'] / 100
    area_share = area_to_value_share(shares['ric_area_based_share_pct'], 1.0 / yield_ratio) / 100
    shares['ric_implied_yield_ratio'] = (value_share / (1 - value_share)) / (area_share / (1 - area_share))
    implausible = (~shares['ric_implied_yield_ratio'].between(*bounds)
                   & shares['ric_implied_yield_ratio'].notna())

    survey = shares['ric_census_or_survey'] == 'sur'
    scale = np.where(survey, shares['ric_area_coverage'].clip(upper=1.0), 1.0)
    for column in ['ric_value_share_pct', 'ric_area_based_share_pct']:
        shares[column] = shares[column] * scale
    shares['ric_flag'] = None
    shares.loc[shares['ric_small_rows'] == 0, 'ric_flag'] = 'no farm-size class below %g ha' % cut
    shares.loc[survey & shares['ric_area_coverage'].isna(), 'ric_flag'] = 'survey, coverage unknown'
    shares.loc[survey & (shares['ric_area_coverage'] < min_coverage), 'ric_flag'] = \
        'survey, coverage < %g' % min_coverage
    shares.loc[shares['ric_n_crops'] < min_crops, 'ric_flag'] = 'fewer than %d crops' % min_crops
    enough = shares['ric_flag'].isna()
    shares['ricciardi_observed'] = np.where(enough & (shares['ric_observed_value_frac'] >= min_observed)
                                            & ~implausible, shares['ric_value_share_pct'], np.nan)
    if implausible.any():
        print('    Ricciardi observed production not used (implied yield ratio outside %s): %s'
              % (bounds, dict(zip(shares.loc[implausible, 'alpha-3'],
                                  shares.loc[implausible, 'ric_implied_yield_ratio'].round(1)))))
    shares['ricciardi_area'] = np.where(enough, shares['ric_area_based_share_pct'], np.nan)
    print('    Ricciardi usable: %d countries with observed production, %d area-based; left out: %s'
          % (shares['ricciardi_observed'].notna().sum(), shares['ricciardi_area'].notna().sum(),
             dict(zip(shares.loc[~enough, 'alpha-3'], shares.loc[~enough, 'ric_flag']))))
    return shares


def rulis_shares(rulis_surveys, cropland, yield_ratio, base_year):
    """Compute the RuLIS smallholder share of every survey and pick one survey per country.

    Args:
        rulis_surveys: Survey table of step 01 (alpha-3, Country, Year, household_land_ha, land_lt2_ha,
            lt2_share_of_household_land_pct).
        cropland: Cropland table from ``load_cropland``.
        yield_ratio: Yield ratio from ``pooled_yield_ratio``.
        base_year: The survey closest to this year represents the country.

    Returns:
        Tuple (every survey with a_pct and its terms, one row per country with rulis_year, household_coverage,
        rulis_area_share_pct, rulis and rulis_flag).
    """
    surveys = rulis_surveys.dropna(subset=['land_lt2_ha']).copy()
    nearest = [cropland_near(cropland, code, year) for code, year in zip(surveys['alpha-3'], surveys['Year'])]
    surveys['cropland_ha'] = [value for value, _ in nearest]
    surveys['household_coverage'] = surveys['household_land_ha'] / surveys['cropland_ha']
    surveys['coverage_used'] = surveys['household_coverage'].clip(upper=1.0)
    surveys['rulis_area_share_pct'] = surveys['lt2_share_of_household_land_pct'] * surveys['coverage_used']
    surveys['rulis_flag'] = np.where(surveys['household_coverage'] > 1.0,
                                     'household land exceeds cropland (coverage capped at 1)', None)
    surveys['rulis'] = area_to_value_share(surveys['rulis_area_share_pct'], yield_ratio)
    surveys = surveys.dropna(subset=['rulis'])
    every_survey = surveys[['alpha-3', 'Country', 'Year', 'household_land_ha', 'land_lt2_ha', 'cropland_ha',
                            'household_coverage', 'lt2_share_of_household_land_pct', 'rulis_area_share_pct',
                            'rulis', 'rulis_flag']].rename(columns={'rulis': 'a_pct'})
    surveys['dist'] = (surveys['Year'] - base_year).abs()
    per_country = surveys.sort_values(['alpha-3', 'dist', 'Year']).drop_duplicates('alpha-3')
    per_country = per_country[['alpha-3', 'Year', 'household_coverage', 'rulis_area_share_pct', 'rulis',
                               'rulis_flag']].rename(columns={'Year': 'rulis_year'})
    print('    RuLIS: %d surveys in %d countries; household land / cropland: median %.2f, %d surveys capped at 1'
          % (len(surveys), surveys['alpha-3'].nunique(), surveys['household_coverage'].median(),
             surveys['rulis_flag'].notna().sum()))
    return every_survey, per_country


def first_reported(row):
    """Return the first reported value of a row, or NaN if none is reported.

    Args:
        row: Series of class areas.

    Returns:
        First non-missing value, or NaN.
    """
    return row.dropna().iloc[0] if row.notna().any() else np.nan


def read_lowder_country(path, lookup):
    """Read Lowder et al. (2021) Web Appendix B, Table 3: farms and farm area by size class, one census per country.

    For censuses whose smallest class starts at 2 ha or more, the area of that smallest reported class is kept as
    an upper bound of the area below 2 ha.

    Args:
        path: ``lowder_2021_country.xlsx``.
        lookup: Normalised country name -> ISO3, from ``utils.iso3_lookup``.

    Returns:
        One row per country with alpha-3, Country, lowder_farm_area_ha, lowder_farm_area_lt2_ha,
        lowder_smallest_class_area_ha, lowder_farms, lowder_farms_lt2 and lowder_census_year.
    """
    raw = pd.read_excel(path, header=None)
    header = raw.index[raw.iloc[:, 0].astype(str).str.strip() == 'Country'][0]
    labels = raw.iloc[header + 1].astype(str).str.replace('–', '-').str.replace(' ', '')
    below_1 = labels[labels == '<1ha'].index[0]
    from_1_to_2 = labels[labels == '1-2ha'].index[0]
    table = raw.iloc[header + 2:].copy()
    table['Country'] = table.iloc[:, 0].ffill().astype(str).str.replace('*', '', regex=False).str.strip()
    table['census'] = table.iloc[:, 1].ffill().astype(str)
    table['FA'] = table.iloc[:, 2].astype(str).str.strip()
    table = table[table['FA'].isin(['F', 'A'])]
    for column in [3, below_1, from_1_to_2]:
        table[column] = pd.to_numeric(table[column], errors='coerce')
    table['lt2'] = table[[below_1, from_1_to_2]].sum(axis=1, min_count=1)        # NaN if neither class reported
    classes = [c for c in range(below_1, raw.shape[1]) if str(raw.iat[header + 1, c]).strip() not in ('nan', '')]
    for column in classes:
        table[column] = pd.to_numeric(table[column], errors='coerce')
    first = table[classes].apply(first_reported, axis=1)
    table['first_class'] = np.where(table['lt2'].isna(), first, np.nan)
    area = table[table['FA'] == 'A'][['Country', 'census', 3, 'lt2', 'first_class']].rename(
        columns={3: 'lowder_farm_area_ha', 'lt2': 'lowder_farm_area_lt2_ha',
                 'first_class': 'lowder_smallest_class_area_ha'})
    farms = table[table['FA'] == 'F'][['Country', 3, 'lt2']].rename(
        columns={3: 'lowder_farms', 'lt2': 'lowder_farms_lt2'})
    lowder = area.merge(farms, on='Country', how='left')
    lowder['lowder_census_year'] = pd.to_numeric(lowder['census'].str.extract(r'(\d{4})')[0], errors='coerce')
    lowder = attach_iso3_by_name(lowder, 'Country', lookup, 'Lowder Table 3')
    return lowder.drop(columns=['census']).drop_duplicates('alpha-3')


def lowder_shares(lowder, cropland, yield_ratio, cropland_fraction):
    """Compute the Lowder smallholder share of each country from farm area below 2 ha and FAOSTAT cropland.

    Args:
        lowder: Table from ``read_lowder_country``.
        cropland: Cropland table from ``load_cropland``.
        yield_ratio: Yield ratio from ``pooled_yield_ratio``.
        cropland_fraction: Share of the farm area below 2 ha that is cropland.

    Returns:
        Copy of ``lowder`` with cropland_census_ha, lowder_farmland_share_pct, lowder_area_share_pct (capped at
        100), lowder_flag, lowder (value share, %) and a_upper_bound_pct.
    """
    lowder = lowder.copy()
    nearest = [cropland_near(cropland, code, year)
               for code, year in zip(lowder['alpha-3'], lowder['lowder_census_year'])]
    lowder['cropland_census_ha'] = [value for value, _ in nearest]
    lowder['lowder_farmland_share_pct'] = 100 * lowder['lowder_farm_area_lt2_ha'] / lowder['lowder_farm_area_ha']
    lowder['lowder_area_share_pct'] = (100 * lowder['lowder_farm_area_lt2_ha'] * cropland_fraction
                                       / lowder['cropland_census_ha'])
    lowder['lowder_flag'] = np.where(lowder['lowder_area_share_pct'] > 100,
                                     'farm area < 2 ha exceeds cropland (capped)', None)
    lowder['lowder_area_share_pct'] = lowder['lowder_area_share_pct'].clip(upper=100)
    lowder['lowder'] = area_to_value_share(lowder['lowder_area_share_pct'], yield_ratio)
    lowder['a_upper_bound_pct'] = area_to_value_share(
        (100 * lowder['lowder_smallest_class_area_ha'] / lowder['cropland_census_ha']).clip(upper=100), yield_ratio)
    print('    Lowder: %d countries with farm area < 2 ha and cropland (%d capped at 100%%)'
          % (lowder['lowder'].notna().sum(), lowder['lowder_flag'].notna().sum()))
    return lowder


def choose_by_tier(ricciardi, rulis, lowder, tier_order):
    """Put the sources side by side and give each country the first available source.

    Args:
        ricciardi: Country table from ``ricciardi_shares``.
        rulis: One row per country from ``rulis_shares``.
        lowder: Table from ``lowder_shares``.
        tier_order: Source names in the order they are tried (``consts.A_TIER_ORDER``).

    Returns:
        One row per country with every source and a_pct (%, 0-100), a_source, a_year and a_upper_bound_pct;
        lowder_name holds Lowder's country name.
    """
    year_column = {'ricciardi_observed': 'ric_year', 'ricciardi_area': 'ric_year', 'rulis': 'rulis_year',
                   'lowder': 'lowder_census_year'}
    candidates = (ricciardi[['alpha-3', 'Country', 'ric_year', 'ric_census_or_survey', 'ric_n_crops',
                             'ric_area_coverage', 'ric_observed_value_frac', 'ric_implied_yield_ratio',
                             'ric_value_share_pct', 'ricciardi_observed', 'ricciardi_area', 'ric_flag']]
                  .merge(rulis, on='alpha-3', how='outer')
                  .merge(lowder[['alpha-3', 'Country', 'lowder_census_year', 'lowder_farmland_share_pct',
                                 'lowder_area_share_pct', 'lowder', 'lowder_flag', 'a_upper_bound_pct']]
                         .rename(columns={'Country': 'lowder_name'}), on='alpha-3', how='outer'))
    candidates['Country'] = candidates['Country'].fillna(candidates['lowder_name'])
    candidates['a_pct'] = np.nan
    candidates['a_source'] = None
    candidates['a_year'] = np.nan
    for tier in tier_order:
        take = candidates['a_pct'].isna() & candidates[tier].notna()
        candidates.loc[take, 'a_pct'] = candidates.loc[take, tier]
        candidates.loc[take, 'a_source'] = tier
        candidates.loc[take, 'a_year'] = candidates.loc[take, year_column[tier]]
    candidates['a_pct'] = candidates['a_pct'].clip(0, 100)
    return candidates


def print_summary(candidates, shares, tier_order, cut):
    """Print the sources used and how the sources compare where several are available.

    Args:
        candidates: Table from ``choose_by_tier``.
        shares: One row per country with a share or an upper bound.
        tier_order: Source names in the order they are tried.
        cut: Farm-size cut-off (ha).
    """
    bound_only = shares['a_pct'].isna()
    print('    upper bounds only (census without a class below %g ha): %s'
          % (cut, dict(zip(shares.loc[bound_only, 'alpha-3'], shares.loc[bound_only, 'a_upper_bound_pct'].round(1)))))
    print('02: smallholder share for %d countries; by source: %s'
          % (shares['a_pct'].notna().sum(),
             shares['a_source'].value_counts().reindex(list(tier_order)).fillna(0).astype(int).to_dict()))
    for first, second in [('ricciardi_observed', 'rulis'), ('ricciardi_observed', 'lowder'), ('rulis', 'lowder'),
                          ('ricciardi_area', 'lowder')]:
        both = candidates.dropna(subset=[first, second])
        if len(both) >= consts.MIN_COUNTRIES_FOR_COMPARISON:
            print('    %s vs %s: %d countries, correlation %.2f, median difference %+.1f points'
                  % (first, second, len(both), np.corrcoef(both[first], both[second])[0, 1],
                     (both[first] - both[second]).median()))


def run(rulis_surveys):
    """Compute the smallholder share a of every country with a source.

    Args:
        rulis_surveys: Survey table of step 01.

    Returns:
        Dict with ``smallholder_share`` (one row per country: a_pct, a_source, a_year, a_upper_bound_pct),
        ``smallholder_share_candidates`` (every source side by side), ``smallholder_share_rulis_surveys`` (a per
        RuLIS survey), ``yield_ratio`` (the ratio used) and ``yield_ratio_by_country``.
    """
    iso = load_iso(input_path('iso'))
    lookup = iso3_lookup(iso, load_wb_income(input_path('wb_income')), consts.ISO3_ALIASES)
    cropland = load_cropland(input_path('land_use'), iso)

    ricciardi = read_ricciardi(input_path('ricciardi'), lookup, consts.SMALL_FARM_HA)
    ricciardi = value_ricciardi(ricciardi, read_prices(input_path('prices'), consts.PRICE_YEARS))
    crops = ricciardi_crop_totals(ricciardi)
    yield_ratio, ratio_by_country = pooled_yield_ratio(crops, consts.YIELD_RATIO, consts.YIELD_RATIO_BOUNDS,
                                                       consts.MIN_CROPS_FOR_YIELD_RATIO, consts.SMALL_FARM_HA)
    ricciardi_by_country = ricciardi_shares(ricciardi, crops, yield_ratio, consts.SMALL_FARM_HA,
                                            consts.YIELD_RATIO_BOUNDS, consts.RICCIARDI_MIN_COVERAGE,
                                            consts.RICCIARDI_MIN_CROPS, consts.RICCIARDI_MIN_OBSERVED)
    rulis_every_survey, rulis_by_country = rulis_shares(rulis_surveys, cropland, yield_ratio, consts.BASE_YEAR)
    lowder = lowder_shares(read_lowder_country(input_path('lowder_country'), lookup), cropland, yield_ratio,
                           consts.SMALL_FARM_CROPLAND_FRACTION)

    candidates = choose_by_tier(ricciardi_by_country, rulis_by_country, lowder, consts.A_TIER_ORDER)
    shares = candidates[candidates['a_pct'].notna() | candidates['a_upper_bound_pct'].notna()][
        ['alpha-3', 'Country', 'a_pct', 'a_source', 'a_year', 'a_upper_bound_pct']]
    print_summary(candidates, shares, consts.A_TIER_ORDER, consts.SMALL_FARM_HA)
    ratio_table = pd.DataFrame([{'pooled_yield_ratio': yield_ratio, 'setting': consts.YIELD_RATIO,
                                 'n_countries': len(ratio_by_country)}])
    return {'smallholder_share': shares,
            'smallholder_share_candidates': candidates.drop(columns=['lowder_name']),
            'smallholder_share_rulis_surveys': rulis_every_survey,
            'yield_ratio': ratio_table,
            'yield_ratio_by_country': ratio_by_country}

