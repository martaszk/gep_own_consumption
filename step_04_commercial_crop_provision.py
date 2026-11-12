"""Step 04: commercial crop provision GEP, by country, year and crop.

GEP_commercial = sum over crops of gross production value (USD) x CWON 2024 land rental rate.

The gross production value is FAOSTAT's reported value, or production (t) x producer price (USD/t) where FAOSTAT
reports production but no value. FAO production includes what households eat themselves, so this value is a
total; step 06 puts it beside the subsistence part.

``consts.METHOD`` selects the pricing chain.

METHOD = 'gep' combines CWON 2024 and global_invest (crop_provision, crop_benefits):

- Crops (``consts.CROP_LIST = 'faostat'``): every primary crop FAOSTAT values in its Value of Production data
  (item codes below the livestock block), minus the FAO group totals ("Cereals, primary", "Roots and Tubers,
  Total", ...) and processed products (cotton lint, cottonseed, palm oil, palm kernels, cassava leaves, kapok). The
  list is built from QV, not from production (QCL), because QCL also carries processed products that would count a
  crop a second time; it follows each new FAOSTAT release. ``CROP_LIST = 'cwon'`` uses CWON's 159 wealth crops
  (land_crop_list.csv) instead. The crops on one list but not the other are printed.
- Price per crop, country and year, in this order: the country's USD price; its SLC price converted to USD with the
  World Bank WDI PA.NUS.ATLS rate (as CWON); its price interpolated between its own neighbouring years (CWON); the
  FAO subregion, region and world price. ``consts.REGIONAL_PRICE`` sets how these three are taken:
  'weighted_median' weights each country's price by its production of the crop that year, so a large producer's
  own price counts more than a small neighbour's (large low-price producers are not valued at small high-price
  neighbours' prices, e.g. North Korean rice at Japanese and Korean prices, Cuban sugar cane at small-island
  prices); 'median' counts every country the same (global_invest). CWON's product substitutions are used where a
  crop has no price of its own (``consts.PRICE_SUBSTITUTES``).
- Price filters: a USD price that is a copy of the SLC price (currency not at par) is dropped. Then
  ``consts.OUTLIER_RULE``: 'world_median_ratio' (global_invest) drops prices above
  ``consts.MAX_RATIO_TO_WORLD_MEDIAN`` x the world median of the crop and year; 'cwon_iqr' replaces prices at or
  above the median + ``consts.CWON_IQR_MULTIPLIER`` x IQR by the median (CWON); 'none' keeps every price.
- ``consts.VALUE_BASIS``: 'reported_first' takes FAO's reported value (current USD) first; production x price only
  fills the crop-country-years FAO reports production for but no value (CWON's first choice). 'production_x_price'
  values every crop-country-year at production x price (global_invest's base-year basis, which puts crop provision
  and pollination on one gross basis); a pair FAO reports but that cannot be priced keeps an empty value.

METHOD = 'cwon' follows CWON 2024 (land.do in the World Bank reproducibility package FR_WLD_2024_195); the options
above are not used:

- crops: the 159 CWON wealth crops (land_crop_list.csv, required);
- production forward-filled over missing years from ``consts.CWON_FIRST_YEAR``;
- three price series per country, crop and year, each with CWON's substitutions, the target-year fill (a missing
  value in ``consts.CWON_TARGET_YEAR`` takes the year before), the outlier rule (at or above the median +
  ``consts.CWON_IQR_MULTIPLIER`` x IQR across countries, by crop and year -> median) and linear interpolation over
  interior gaps (a series with one observation is dropped): unit value = FAO gross production value (USD, or SLC
  converted) / production; producer price (USD, or SLC converted); export unit value = export value / export
  quantity (from the FAOSTAT trade file; without it this series is skipped);
- price order: unit value, producer price, regional unit value, regional producer price, world unit value, world
  producer price, export unit value, regional and world export unit value. Regional and world prices are
  production-weighted means over CWON's 14 ef_regions (from the rental-rate table);
- years ``consts.CWON_FIRST_YEAR`` to ``consts.CWON_TARGET_YEAR``.

Constant prices use the CPI deflator of ``utils.deflate``, not CWON's country GDP deflator; current-USD values are
not affected. With METHOD = 'cwon' the computed rent of the target year is printed beside the rent of CWON's
published crop wealth.

Both methods: China is FAO "China, mainland" (FAO's China aggregate is dropped). Belgium and Luxembourg are split
out of Belgium-Luxembourg before ``consts.BLX_SPLIT_YEAR`` by each crop's shares in that year (land-area shares
where a crop has none), as in CWON. The countries CWON leaves out are left out (``consts.CWON_DROPPED_COUNTRIES``).
Values start in ``consts.COMMERCIAL_FIRST_YEAR``. A country without a CWON rental rate gets no rent, as in CWON.
"""
import re

import numpy as np
import pandas as pd

import consts
from utils import attach_rental_rates, deflate, input_path, load_cpi, load_iso, load_rental_rates, read_fao_csv


def load_countries(iso_path, region_overrides):
    """Read the countries with their FAO subregion, region and name.

    The subregion is the UN intermediate region where there is one (e.g. Eastern Africa), else the UN sub-region.

    Args:
        iso_path: ISO table (``utils.load_iso``).
        region_overrides: Dict of ISO3 -> (subregion, region) for countries the ISO table gives no region.

    Returns:
        DataFrame with columns country-code (M49), alpha-3, name, subregion and region. Rows without an M49 code or
        a three-letter code are skipped with a warning.
    """
    iso = load_iso(iso_path).rename(columns={'m49': 'country-code'}).replace('', np.nan)
    bad = iso[iso['country-code'].isna() | (iso['alpha-3'].str.len() != 3)]
    if len(bad):
        print('WARNING: %d rows of %s could not be read and are skipped: %s'
              % (len(bad), iso_path, bad['name'].tolist()))
    iso = iso.drop(bad.index)
    iso['subregion'] = iso['intermediate-region'].fillna(iso['sub-region'])
    for code, (subregion, region) in region_overrides.items():
        iso.loc[iso['alpha-3'] == code, ['subregion', 'region']] = [subregion, region]
    return iso[['country-code', 'alpha-3', 'name', 'subregion', 'region']]


def load_wdi_fx(path):
    """Read the World Bank WDI exchange rate PA.NUS.ATLS (LCU per US$).

    Args:
        path: The file as downloaded from data.worldbank.org (metadata lines before the header) or a DataBank
            export (year columns such as "2019 [YR2019]").

    Returns:
        DataFrame with columns alpha-3, Year and fx; only positive rates.
    """
    with open(path, encoding='utf-8-sig') as handle:
        lines = handle.read().splitlines()
    header = next(i for i, line in enumerate(lines) if 'Country Code' in line)
    separator = ';' if lines[header].count(';') > lines[header].count(',') else ','
    raw = pd.read_csv(path, skiprows=header, sep=separator, encoding='utf-8-sig', na_values=['..', ''])
    year_of = {c: int(re.match(r'\s*(\d{4})', str(c)).group(1)) for c in raw.columns if re.match(r'\s*\d{4}', str(c))}
    fx = raw[['Country Code'] + list(year_of)].melt(id_vars='Country Code', var_name='Year', value_name='fx')
    fx['Year'] = fx['Year'].map(year_of)
    fx['fx'] = pd.to_numeric(fx['fx'], errors='coerce')
    fx = fx[fx['fx'] > 0].rename(columns={'Country Code': 'alpha-3'})
    print('Exchange rates: World Bank WDI PA.NUS.ATLS from %s (%d countries, %d-%d).'
          % (path.name, fx['alpha-3'].nunique(), fx['Year'].min(), fx['Year'].max()))
    return fx[['alpha-3', 'Year', 'fx']]


def item_names(path):
    """Read the FAO item names of a FAOSTAT file.

    Args:
        path: FAOSTAT bulk file.

    Returns:
        Series of item names indexed by item code.
    """
    table = read_fao_csv(path, usecols=['Item Code', 'Item'])
    return table.drop_duplicates('Item Code').set_index('Item Code')['Item']


def item_label(code, names):
    """Return '<code> <name>' for printing a FAO item.

    Args:
        code: FAO item code.
        names: Item names from ``item_names``.

    Returns:
        Label text; '?' stands for an unknown name.
    """
    return '%d %s' % (code, names.get(code, '?'))


def load_cwon_crop_list(path):
    """Read CWON's wealth crops.

    Args:
        path: ``land_crop_list.csv`` from the CWON package.

    Returns:
        Set of FAO item codes with wealth_crop == 1.
    """
    crop_list = pd.read_csv(path, encoding='latin-1')
    return set(crop_list.loc[crop_list['wealth_crop'] == 1, 'fao_itemcode'].astype(int))


def crop_universe(value_of_production, names, crop_list, crop_list_path):
    """Choose the crops that are valued.

    'faostat': every primary crop FAOSTAT values in QV (item codes below the livestock block), minus group totals
    and processed products. 'cwon': CWON's wealth crops. When the CWON list is available, the crops on one list but
    not the other are printed.

    Args:
        value_of_production: Long QV table from ``load_faostat`` (item_code, element).
        names: Item names from ``item_names``.
        crop_list: 'faostat' or 'cwon'.
        crop_list_path: ``land_crop_list.csv``.

    Returns:
        Set of FAO item codes.

    Raises:
        FileNotFoundError: crop_list is 'cwon' and the CWON list is missing.
        ValueError: Unknown crop_list.
    """
    faostat_items = set(value_of_production.loc[value_of_production['element'] == consts.EL_VALUE_USD,
                                                 'item_code'].astype(int))
    faostat_items = ({item for item in faostat_items if item < consts.FIRST_LIVESTOCK_ITEM_CODE}
                     - consts.FAO_GROUP_TOTALS - consts.FAO_PROCESSED_ITEMS)
    cwon_items = load_cwon_crop_list(crop_list_path) if crop_list_path.exists() else None
    if crop_list == 'faostat':
        items = faostat_items
    elif crop_list == 'cwon':
        if cwon_items is None:
            raise FileNotFoundError("CROP_LIST = 'cwon' needs %s" % crop_list_path)
        items = cwon_items
    else:
        raise ValueError("CROP_LIST must be 'faostat' or 'cwon'")
    print('Crops valued: %d (CROP_LIST = %r).' % (len(items), crop_list))
    if cwon_items is not None:
        print('  On the FAOSTAT list only: %s'
              % ([item_label(code, names) for code in sorted(faostat_items - cwon_items)] or 'none'))
        print('  On the CWON list only:    %s'
              % ([item_label(code, names) for code in sorted(cwon_items - faostat_items)] or 'none'))
    return items


def load_faostat(path, elements, items, countries):
    """Read a FAOSTAT bulk table (wide layout) as long rows per country, item, element and year.

    Only countries are kept: the China aggregate, region aggregates and rows without an M49 code are dropped. M49
    codes of predecessor countries are mapped to their successors, then to ISO3.

    Args:
        path: FAOSTAT bulk file.
        elements: Element codes to keep.
        items: Item codes to keep, or None for all.
        countries: Country table from ``load_countries``.

    Returns:
        Tuple (long table with alpha-3, item_code, element, Year, value; the Belgium-Luxembourg rows with
        item_code, element, Year and value, for ``split_belgium_luxembourg``).
    """
    header = read_fao_csv(path, nrows=0).columns
    year_columns = [c for c in header if re.fullmatch(r'Y\d{4}', c)]
    keep = (['Area Code', 'Area Code (M49)', 'Item Code', 'Element Code']
            + (['Months Code'] if 'Months Code' in header else []) + year_columns)
    table = read_fao_csv(path, usecols=keep, low_memory=False)
    table = table[table['Element Code'].isin(elements)]
    if items is not None:
        table = table[table['Item Code'].isin(items)]
    if 'Months Code' in table.columns:
        table = table[table['Months Code'] == consts.ANNUAL_VALUE].drop(columns='Months Code')
    table = table[(table['Area Code'] != consts.FAO_CHINA_AGGREGATE)
                  & (table['Area Code'] < consts.FAO_FIRST_REGION_CODE)]
    long = table.melt(id_vars=['Area Code', 'Area Code (M49)', 'Item Code', 'Element Code'],
                      var_name='Year', value_name='value')
    long['Year'] = long['Year'].str[1:].astype(int)
    long['value'] = pd.to_numeric(long['value'], errors='coerce')
    long = long.dropna(subset=['value'])
    long['m49'] = pd.to_numeric(long['Area Code (M49)'].astype(str).str.replace("'", ''), errors='coerce')
    long = long.dropna(subset=['m49'])
    long['m49'] = long['m49'].astype(int).replace(consts.M49_SUCCESSORS)
    belgium_luxembourg = long[long['Area Code'] == consts.FAO_BELGIUM_LUXEMBOURG]
    codes = countries[['country-code', 'alpha-3']].astype({'country-code': int})
    long = long.merge(codes, left_on='m49', right_on='country-code')
    long = long.rename(columns={'Item Code': 'item_code', 'Element Code': 'element'})
    out = long.groupby(['alpha-3', 'item_code', 'element', 'Year'], as_index=False)['value'].sum()
    return out, belgium_luxembourg.rename(columns={'Item Code': 'item_code', 'Element Code': 'element'})


def split_belgium_luxembourg(production, belgium_luxembourg, split_year, land_area_km2):
    """Split Belgium-Luxembourg production before the split year into Belgium and Luxembourg.

    Each crop is split by the two countries' production shares in the split year; a crop without production then
    is split by land area. Country-years that already have production keep it.

    Args:
        production: Long production table from ``load_faostat``.
        belgium_luxembourg: Belgium-Luxembourg rows from ``load_faostat``.
        split_year: First year with separate data.
        land_area_km2: Dict BEL / LUX -> land area.

    Returns:
        ``production`` with the split rows added.
    """
    joint = belgium_luxembourg[belgium_luxembourg['Year'] < split_year][['item_code', 'Year', 'value']]
    if joint.empty:
        return production
    first_year = production[production['alpha-3'].isin(list(land_area_km2)) & (production['Year'] == split_year)]
    shares = first_year.pivot_table(index='item_code', columns='alpha-3', values='value', aggfunc='sum')
    shares = shares.reindex(columns=list(land_area_km2)).fillna(0)
    total = shares.sum(axis=1)
    total_area = sum(land_area_km2.values())
    parts = []
    for code, area in land_area_km2.items():
        area_share = area / total_area
        share = (shares[code] / total).where(total > 0, area_share)
        part = joint.assign(**{'alpha-3': code, 'element': consts.EL_PRODUCTION})
        part['value'] = part['value'] * part['item_code'].map(share).fillna(area_share)
        parts.append(part)
    split = pd.concat(parts)
    have = production.set_index(['alpha-3', 'item_code', 'Year']).index
    split = split[~split.set_index(['alpha-3', 'item_code', 'Year']).index.isin(have)]
    return pd.concat([production, split], ignore_index=True)


def stata_pctile(values, percentile):
    """Return a percentile computed as Stata's ``_pctile`` does (CWON's outlier rule).

    Args:
        values: Values (array-like; NaN ignored).
        percentile: Percentile, 0-100.

    Returns:
        The percentile, or NaN for no values.
    """
    values = np.asarray(values, dtype=float)
    values = np.sort(values[~np.isnan(values)])
    count = len(values)
    if count == 0:
        return np.nan
    position = count * percentile / 100.0
    index = int(np.floor(position))
    if position > index:
        return values[min(index, count - 1)]
    return values[0] if index == 0 else (values[index - 1] + values[min(index, count - 1)]) / 2.0


def iqr_outliers(table, column, multiplier):
    """Replace values at or above the median + multiplier x interquartile range of their crop and year by the median.

    Percentiles follow Stata (``stata_pctile``), as in CWON's land.do.

    Args:
        table: DataFrame with item_code, Year and ``column``.
        column: Value column.
        multiplier: IQR multiplier (``consts.CWON_IQR_MULTIPLIER``).

    Returns:
        Tuple (copy of ``table`` with the outliers replaced, boolean Series marking them).
    """
    groups = table.groupby(['item_code', 'Year'])[column]
    median = groups.transform(stata_pctile, 50)
    lower = groups.transform(stata_pctile, 25)
    upper = groups.transform(stata_pctile, 75)
    outliers = table[column].notna() & median.notna() & (table[column] >= median + multiplier * (upper - lower))
    table = table.copy()
    table.loc[outliers, column] = median[outliers]
    return table, outliers


def remove_outliers(prices, rule, max_ratio, iqr_multiplier):
    """Apply the outlier rule to country prices.

    Args:
        prices: DataFrame with item_code, Year and price.
        rule: 'world_median_ratio' (drop prices above ``max_ratio`` x the world median of the crop and year),
            'cwon_iqr' (``iqr_outliers``) or 'none'.
        max_ratio: Ratio to the world median for 'world_median_ratio'.
        iqr_multiplier: IQR multiplier for 'cwon_iqr'.

    Returns:
        Tuple (prices after the rule, number of prices dropped or replaced, description for printing).

    Raises:
        ValueError: Unknown rule.
    """
    if rule == 'world_median_ratio':
        world_median = prices.groupby(['item_code', 'Year'])['price'].transform('median')
        outliers = prices['price'] > max_ratio * world_median
        return prices[~outliers], int(outliers.sum()), 'dropped as > %g x world median' % max_ratio
    if rule == 'cwon_iqr':
        prices, outliers = iqr_outliers(prices, 'price', iqr_multiplier)
        return prices, int(outliers.sum()), 'replaced by the median (CWON median + %g IQR)' % iqr_multiplier
    if rule == 'none':
        return prices, 0, 'filtered'
    raise ValueError("OUTLIER_RULE must be 'world_median_ratio', 'cwon_iqr' or 'none'")


def country_prices(producer_prices, fx, outlier_rule, max_ratio, iqr_multiplier, copy_fx_tolerance, copy_rtol):
    """Return one USD/t price per country, crop and year from the country's own producer prices.

    The USD price is used, else the SLC price converted with the WDI rate. A USD price equal to the SLC price
    where the currency is not at par is a copy and is dropped. Then the outlier rule is applied.

    Args:
        producer_prices: Long producer price table from ``load_faostat`` (USD and SLC elements).
        fx: Exchange rates from ``load_wdi_fx``.
        outlier_rule: ``consts.OUTLIER_RULE``.
        max_ratio: ``consts.MAX_RATIO_TO_WORLD_MEDIAN``.
        iqr_multiplier: ``consts.CWON_IQR_MULTIPLIER``.
        copy_fx_tolerance: A USD price equal to the SLC price is a copy unless |fx - 1| is at most this.
        copy_rtol: Relative difference below which the USD and SLC prices count as equal.

    Returns:
        DataFrame with alpha-3, item_code, Year, price and price_source ('country USD', 'country SLC converted').
    """
    prices = producer_prices.pivot_table(index=['alpha-3', 'item_code', 'Year'], columns='element', values='value',
                                         aggfunc='first').reset_index()
    prices = prices.rename(columns={consts.EL_PRICE_USD: 'usd', consts.EL_PRICE_SLC: 'slc'})
    for column in ['usd', 'slc']:
        if column not in prices.columns:
            prices[column] = np.nan
        prices.loc[prices[column] <= 0, column] = np.nan
    prices = prices.merge(fx, on=['alpha-3', 'Year'], how='left')
    copies = (prices['usd'].notna() & np.isclose(prices['usd'], prices['slc'], rtol=copy_rtol)
              & ((prices['fx'] - 1).abs() > copy_fx_tolerance))
    prices.loc[copies, 'usd'] = np.nan
    prices['price'] = prices['usd']
    prices['price_source'] = np.where(prices['usd'].notna(), 'country USD', None)
    convert = prices['price'].isna() & prices['slc'].notna() & (prices['fx'] > 0)
    prices.loc[convert, 'price'] = prices.loc[convert, 'slc'] / prices.loc[convert, 'fx']
    prices.loc[convert, 'price_source'] = 'country SLC converted'
    prices = prices.dropna(subset=['price'])
    count = len(prices)
    prices, n_outliers, note = remove_outliers(prices, outlier_rule, max_ratio, iqr_multiplier)
    print('Producer prices: %d country-crop-years; %d USD copies of SLC removed; %d %s.'
          % (count, int(copies.sum()), n_outliers, note))
    return prices[['alpha-3', 'item_code', 'Year', 'price', 'price_source']]


def substitute_prices(observed, substitutes):
    """Add CWON's product substitutions where a crop has no country price of its own.

    Args:
        observed: Country prices from ``country_prices``.
        substitutes: Dict of crop -> crops whose mean price it takes (``consts.PRICE_SUBSTITUTES``).

    Returns:
        ``observed`` with the substituted prices added (price_source 'country substitute crop').
    """
    have = set(zip(observed['alpha-3'], observed['item_code'], observed['Year']))
    parts = []
    for target, sources in substitutes.items():
        substitute = (observed[observed['item_code'].isin(sources)].groupby(['alpha-3', 'Year'], as_index=False)
                      ['price'].mean())
        substitute['item_code'] = target
        substitute = substitute[[key not in have for key in
                                 zip(substitute['alpha-3'], substitute['item_code'], substitute['Year'])]]
        substitute['price_source'] = 'country substitute crop'
        parts.append(substitute)
    return pd.concat([observed] + parts, ignore_index=True)


def interpolate_prices(observed):
    """Interpolate a country's price of a crop between its own neighbouring years (CWON).

    Args:
        observed: Country prices (alpha-3, item_code, Year, price, price_source).

    Returns:
        ``observed`` with the interpolated years added (price_source 'country interpolated').
    """
    parts = []
    for (code, item), series in observed.groupby(['alpha-3', 'item_code'], sort=False):
        if len(series) < 2:
            continue
        series = series.set_index('Year').sort_index()
        full = series.reindex(range(series.index.min(), series.index.max() + 1))
        gap = full['price'].isna()
        if gap.any():
            filled = full['price'].interpolate(method='index', limit_area='inside')
            parts.append(pd.DataFrame({'alpha-3': code, 'item_code': item, 'Year': full.index[gap],
                                       'price': filled[gap].to_numpy(), 'price_source': 'country interpolated'}))
    added = pd.concat(parts, ignore_index=True) if parts else observed.iloc[0:0]
    print('Producer prices: %d country-crop-years added by interpolation.' % len(added))
    return pd.concat([observed, added], ignore_index=True)


def grouped_weighted_median(table, by, value, weight):
    """Return the weighted median of each group: the smallest value at which the cumulative weight reaches half.

    Args:
        table: DataFrame.
        by: Group columns.
        value: Value column.
        weight: Weight column; rows without a positive weight are left out.

    Returns:
        DataFrame with the group columns and ``value``.
    """
    rows = table.dropna(subset=[value, weight])
    rows = rows[rows[weight] > 0].sort_values(by + [value])
    cumulative = rows.groupby(by)[weight].cumsum()
    half = rows.groupby(by)[weight].transform('sum') / 2.0
    return rows[cumulative >= half].groupby(by, as_index=False).first()[by + [value]]


def commercial_values(production, prices, observed, countries, reported, regional_price, value_basis):
    """Compute the gross value per country, crop and year (METHOD = 'gep').

    Crop-country-years without a price of their own take the subregion, region or world price of the countries'
    own prices (``observed``).

    Args:
        production: Long production table (element, value in tonnes).
        prices: Country prices with substitutions and interpolation.
        observed: Country prices from ``country_prices`` (donors of the regional prices).
        countries: Country table from ``load_countries``.
        reported: FAO reported gross production value (element EL_VALUE_USD, thousand USD).
        regional_price: 'weighted_median' or 'median'.
        value_basis: 'reported_first' or 'production_x_price'.

    Returns:
        DataFrame with alpha-3, item_code, Year, production_t, price, price_source, gross_value_usd, value_source
        and gross_value_fao_reported_usd.

    Raises:
        ValueError: Unknown regional_price or value_basis, or duplicate rows.
    """
    keys = consts.CROP_YEAR_KEYS
    values = production[production['element'] == consts.EL_PRODUCTION][keys + ['value']].rename(
        columns={'value': 'production_t'})
    values = values[values['production_t'] > 0]
    values = values.merge(prices, on=keys, how='left')
    values = values.merge(countries[['alpha-3', 'subregion', 'region']], on='alpha-3', how='left')
    donors = observed.merge(countries[['alpha-3', 'subregion', 'region']], on='alpha-3', how='left')
    donors = donors.merge(values[keys + ['production_t']], on=keys, how='left')
    for level, by in [('subregion', ['subregion']), ('region', ['region']), ('world', [])]:
        if regional_price == 'median':
            level_price = donors.groupby(by + ['item_code', 'Year'], as_index=False)['price'].median()
        elif regional_price == 'weighted_median':
            level_price = grouped_weighted_median(donors, by + ['item_code', 'Year'], 'price', 'production_t')
        else:
            raise ValueError("REGIONAL_PRICE must be 'median' or 'weighted_median'")
        level_price = level_price.rename(columns={'price': 'price_' + level})
        values = values.merge(level_price, on=by + ['item_code', 'Year'], how='left')
        take = values['price'].isna() & values['price_' + level].notna()
        values.loc[take, 'price'] = values.loc[take, 'price_' + level]
        values.loc[take, 'price_source'] = level + ' median'
    values['gross_value_usd'] = values['production_t'] * values['price']
    values['value_source'] = np.where(values['price'].notna(), 'production x price', 'no price')

    reported = reported[reported['element'] == consts.EL_VALUE_USD][keys + ['value']].rename(
        columns={'value': 'reported'})
    reported['reported'] = reported['reported'] * 1000.0
    values = values.merge(reported, on=keys, how='outer')
    if value_basis == 'reported_first':
        take = values['reported'].notna()
        values.loc[take, 'gross_value_usd'] = values.loc[take, 'reported']
        values.loc[take, 'value_source'] = 'FAO reported'
        values.loc[take, ['price', 'price_source']] = [np.nan, None]
    elif value_basis == 'production_x_price':
        take = values['reported'].notna() & values['gross_value_usd'].isna()
        values.loc[take, 'value_source'] = 'FAO reported, not priced (missing)'
    else:
        raise ValueError("VALUE_BASIS must be 'reported_first' or 'production_x_price'")
    values['gross_value_fao_reported_usd'] = values['reported']
    values = values.drop(columns='reported')
    if values.duplicated(keys).any():
        raise ValueError('Duplicate country-crop-year rows in the commercial values.')
    return values[keys + ['production_t', 'price', 'price_source', 'gross_value_usd', 'value_source',
                          'gross_value_fao_reported_usd']]


def cwon_master(master, using, keys):
    """Combine two tables as Stata's ``merge 1:1 ... nogen`` with the master winning on matched keys.

    Args:
        master: Rows that win.
        using: Rows added where the master has no row with the same keys.
        keys: Key columns.

    Returns:
        ``master`` followed by the rows of ``using`` that the master lacks.
    """
    marked = using.merge(master[keys].drop_duplicates().assign(_m=1), on=keys, how='left')
    return pd.concat([master, marked[marked['_m'].isna()].drop(columns='_m')], ignore_index=True)


def cwon_fill_target(table, column, keys, target_year):
    """Fill a missing value of the target year with the year before (land.do).

    Args:
        table: DataFrame with Year, ``column`` and ``keys``.
        column: Value column.
        keys: Columns that identify a series, without Year.
        target_year: ``consts.CWON_TARGET_YEAR``.

    Returns:
        ``table`` with the target-year rows of series that miss it replaced by the year-before value.
    """
    have = table.dropna(subset=[column])
    present = have[have['Year'] == target_year][keys].drop_duplicates().assign(_t=1)
    previous = have[have['Year'] == target_year - 1].merge(present, on=keys, how='left')
    previous = previous[previous['_t'].isna()].drop(columns='_t').assign(Year=target_year)
    rest = table[~((table['Year'] == target_year) & table[column].isna())]
    return pd.concat([rest, previous], ignore_index=True)


def cwon_substitute(table, column, substitutes, extra=()):
    """Apply CWON's product substitutions; the substitute wins over the crop's own value (land.do).

    A crop with several source crops takes their mean; a crop with one source takes its rows. A value of 0 counts
    as missing.

    Args:
        table: DataFrame with alpha-3, Year, item_code, ``column`` and the ``extra`` key columns.
        column: Value column.
        substitutes: Dict of crop -> source crops (``consts.PRICE_SUBSTITUTES``), applied in this order.
        extra: Further key columns, e.g. ['element'].

    Returns:
        ``table`` with the substitutes.
    """
    keys = ['alpha-3', 'Year'] + list(extra)
    for target, sources in substitutes.items():
        if len(sources) > 1:
            substitute = table[table['item_code'].isin(sources)].groupby(keys, as_index=False)[column].mean()
        else:
            substitute = table[table['item_code'] == sources[0]].copy()
        substitute['item_code'] = target
        substitute.loc[substitute[column] == 0, column] = np.nan
        table = cwon_master(substitute, table, keys + ['item_code'])
    return table


def cwon_interpolate(table, column, years):
    """Interpolate a price series over interior gaps (land.do tsfill + ipolate).

    Series with one observation are dropped; a value of 0 counts as missing.

    Args:
        table: DataFrame with alpha-3, item_code, Year and ``column``.
        column: Value column.
        years: (first, last) year.

    Returns:
        DataFrame with alpha-3, item_code, Year and ``column``; years with a value only.
    """
    first, last = years
    table = table[(table['Year'] >= first) & (table['Year'] <= last)].dropna(subset=[column])
    wide = table.pivot_table(index=['alpha-3', 'item_code'], columns='Year', values=column, aggfunc='first')
    wide = wide[wide.notna().sum(axis=1) >= 2]
    wide = wide.reindex(columns=range(first, last + 1)).interpolate(axis=1, limit_area='inside')
    out = wide.stack().rename(column).reset_index()
    out.loc[out[column] == 0, column] = np.nan
    return out.dropna(subset=[column])


def cwon_production(production, first_year):
    """Forward-fill production over missing years from the first year (land.do carryforward).

    Args:
        production: Long production table.
        first_year: ``consts.CWON_FIRST_YEAR``.

    Returns:
        DataFrame with alpha-3, item_code, Year and production_t, up to the last production year.
    """
    rows = production[(production['element'] == consts.EL_PRODUCTION) & (production['Year'] >= first_year)]
    last = int(rows['Year'].max())
    wide = rows.pivot_table(index=['alpha-3', 'item_code'], columns='Year', values='value', aggfunc='first')
    wide = wide.reindex(columns=range(first_year, last + 1)).ffill(axis=1)
    return wide.stack().rename('production_t').reset_index()


def cwon_producer_prices(producer_prices, fx, cwon_countries, years, substitutes, iqr_multiplier):
    """Build CWON's producer price series: USD (else SLC converted), substituted, cleaned, interpolated.

    Args:
        producer_prices: Long producer price table (USD and SLC elements).
        fx: Exchange rates from ``load_wdi_fx``.
        cwon_countries: Countries with a CWON region.
        years: (first, target) year.
        substitutes: ``consts.PRICE_SUBSTITUTES``.
        iqr_multiplier: ``consts.CWON_IQR_MULTIPLIER``.

    Returns:
        DataFrame with alpha-3, item_code, Year and pp (USD/t).
    """
    keys = consts.CROP_YEAR_KEYS
    prices = producer_prices[producer_prices['element'].isin([consts.EL_PRICE_USD, consts.EL_PRICE_SLC])
                             & (producer_prices['Year'] >= years[0])].rename(columns={'value': 'pp'})
    prices = cwon_fill_target(prices, 'pp', ['alpha-3', 'item_code', 'element'], years[1])
    prices = cwon_substitute(prices, 'pp', substitutes, extra=['element'])
    usd = prices[prices['element'] == consts.EL_PRICE_USD][keys + ['pp']]
    slc = prices[prices['element'] == consts.EL_PRICE_SLC].merge(fx, on=['alpha-3', 'Year'], how='inner')
    slc = slc.assign(pp=slc['pp'] / slc['fx'])[keys + ['pp']]
    prices = cwon_master(usd, slc, keys)
    prices = prices[prices['alpha-3'].isin(cwon_countries)]
    return cwon_interpolate(iqr_outliers(prices, 'pp', iqr_multiplier)[0], 'pp', years)


def cwon_unit_values(value_of_production, production, fx, items, cwon_countries, years, substitutes, iqr_multiplier):
    """Build CWON's unit value series: gross production value / production, substituted, cleaned, interpolated.

    Args:
        value_of_production: Long QV table (USD and SLC elements, thousand currency units).
        production: Production from ``cwon_production``.
        fx: Exchange rates from ``load_wdi_fx``.
        items: Crops valued.
        cwon_countries: Countries with a CWON region.
        years: (first, target) year.
        substitutes: ``consts.PRICE_SUBSTITUTES``.
        iqr_multiplier: ``consts.CWON_IQR_MULTIPLIER``.

    Returns:
        DataFrame with alpha-3, item_code, Year and uv (USD/t).
    """
    keys = consts.CROP_YEAR_KEYS
    gross = value_of_production[value_of_production['element'].isin([consts.EL_VALUE_USD, consts.EL_VALUE_SLC])
                                & value_of_production['item_code'].isin(items)
                                & (value_of_production['Year'] >= years[0])].rename(columns={'value': 'gv'})
    gross = cwon_fill_target(gross, 'gv', ['alpha-3', 'item_code', 'element'], years[1])
    usd = gross[gross['element'] == consts.EL_VALUE_USD]
    usd = usd.assign(gv=usd['gv'] * 1000.0)[keys + ['gv']]
    slc = gross[gross['element'] == consts.EL_VALUE_SLC].merge(fx, on=['alpha-3', 'Year'], how='inner')
    slc = slc.assign(gv=slc['gv'] * 1000.0 / slc['fx'])[keys + ['gv']]
    gross = cwon_master(usd, slc, keys)
    unit = production[keys + ['production_t']].merge(gross, on=keys, how='outer')
    unit['uv'] = unit['gv'] / unit['production_t'].replace(0, np.nan)
    unit = cwon_fill_target(unit, 'uv', ['alpha-3', 'item_code'], years[1])
    unit = cwon_substitute(unit[keys + ['uv']], 'uv', substitutes)
    unit = unit[unit['alpha-3'].isin(cwon_countries)]
    return cwon_interpolate(iqr_outliers(unit, 'uv', iqr_multiplier)[0], 'uv', years)


def cwon_export_unit_values(trade_path, countries, items, cwon_countries, years, substitutes, iqr_multiplier):
    """Build CWON's export unit value series: export value / export quantity, substituted, cleaned, interpolated.

    Args:
        trade_path: FAOSTAT trade bulk file; without it the series is empty.
        countries: Country table from ``load_countries``.
        items: Crops valued.
        cwon_countries: Countries with a CWON region.
        years: (first, target) year.
        substitutes: ``consts.PRICE_SUBSTITUTES``.
        iqr_multiplier: ``consts.CWON_IQR_MULTIPLIER``.

    Returns:
        DataFrame with alpha-3, item_code, Year and euv (USD/t).
    """
    if not trade_path.exists():
        print('WARNING: %s not found; the CWON export unit value step is skipped.' % trade_path)
        return pd.DataFrame({'alpha-3': pd.Series(dtype=object), 'item_code': pd.Series(dtype='int64'),
                             'Year': pd.Series(dtype='int64'), 'euv': pd.Series(dtype=float)})
    keys = consts.CROP_YEAR_KEYS
    trade, _ = load_faostat(trade_path, [consts.EL_EXPORT_QTY, consts.EL_EXPORT_VALUE],
                            set(items) | set(consts.CWON_TRADE_ITEM_MAP), countries)
    trade = trade[trade['Year'] >= years[0]].pivot_table(index=keys, columns='element', values='value',
                                                         aggfunc='first').reset_index()
    for element in (consts.EL_EXPORT_QTY, consts.EL_EXPORT_VALUE):
        if element not in trade.columns:
            trade[element] = np.nan
    trade['euv'] = trade[consts.EL_EXPORT_VALUE] * 1000.0 / trade[consts.EL_EXPORT_QTY].replace(0, np.nan)
    trade = cwon_fill_target(trade[keys + ['euv']], 'euv', ['alpha-3', 'item_code'], years[1])
    trade['item_code'] = trade['item_code'].replace(consts.CWON_TRADE_ITEM_MAP)
    trade = trade.groupby(keys, as_index=False)['euv'].mean()
    trade.loc[trade['euv'] == 0, 'euv'] = np.nan
    trade = cwon_substitute(trade[trade['item_code'].isin(items)], 'euv', substitutes)
    trade = trade[trade['alpha-3'].isin(cwon_countries)]
    return cwon_interpolate(iqr_outliers(trade, 'euv', iqr_multiplier)[0], 'euv', years)


def cwon_wmean(table, by, column):
    """Return the production-weighted mean of a price by group (land.do regional and world averages).

    Args:
        table: DataFrame with the group columns, ``column`` and production_t.
        by: Group columns.
        column: Price column.

    Returns:
        DataFrame with the group columns and ``column``.
    """
    rows = table.dropna(subset=[column])
    rows = rows.assign(_w=rows[column] * rows['production_t'])
    sums = rows.groupby(by)[['_w', 'production_t']].sum()
    return (sums['_w'] / sums['production_t'].replace(0, np.nan)).rename(column).reset_index()


def cwon_values(production, producer_prices, value_of_production, countries, items, fx, rental_rates_path,
                trade_path, years, substitutes, iqr_multiplier):
    """Compute the gross value per country, crop and year as production x the first price in CWON's order.

    Args:
        production: Long production table.
        producer_prices: Long producer price table.
        value_of_production: Long QV table.
        countries: Country table from ``load_countries``.
        items: Crops valued.
        fx: Exchange rates from ``load_wdi_fx``.
        rental_rates_path: CWON rental-rate table (source of the ef_regions).
        trade_path: FAOSTAT trade bulk file.
        years: (first, target) year.
        substitutes: ``consts.PRICE_SUBSTITUTES``.
        iqr_multiplier: ``consts.CWON_IQR_MULTIPLIER``.

    Returns:
        DataFrame with the columns of ``commercial_values``.
    """
    keys = consts.CROP_YEAR_KEYS
    rates = pd.read_csv(rental_rates_path, encoding='latin-1')
    regions = rates[['wb_code', 'ef_region']].rename(columns={'wb_code': 'alpha-3'}).dropna()
    cwon_countries = set(regions['alpha-3'])
    production = cwon_production(production, years[0])
    price_series = [cwon_producer_prices(producer_prices, fx, cwon_countries, years, substitutes, iqr_multiplier),
                    cwon_unit_values(value_of_production, production, fx, items, cwon_countries, years, substitutes,
                                     iqr_multiplier),
                    cwon_export_unit_values(trade_path, countries, items, cwon_countries, years, substitutes,
                                            iqr_multiplier)]
    base = production[production['production_t'].notna() & (production['production_t'] != 0)
                      & production['item_code'].isin(items)].merge(regions, on='alpha-3')
    for series in price_series:
        base = base.merge(series, on=keys, how='left')
    for column in ['uv', 'pp', 'euv']:
        base = base.merge(cwon_wmean(base, ['ef_region', 'item_code', 'Year'], column)
                          .rename(columns={column: 'reg_' + column}), on=['ef_region', 'item_code', 'Year'], how='left')
        base = base.merge(cwon_wmean(base, ['item_code', 'Year'], column)
                          .rename(columns={column: 'wld_' + column}), on=['item_code', 'Year'], how='left')
    base = base[(base['Year'] >= years[0]) & (base['Year'] <= years[1])].copy()
    base['price'] = np.nan
    base['price_source'] = pd.Series(None, index=base.index, dtype=object)
    for column, label in consts.CWON_ORDER:
        take = base['price'].isna() & base[column].notna()
        base.loc[take, 'price'], base.loc[take, 'price_source'] = base.loc[take, column], label
    base.loc[base['price'] == 0, ['price', 'price_source']] = [np.nan, None]
    base['gross_value_usd'] = base['production_t'] * base['price']
    base['value_source'] = np.where(base['price_source'] == 'FAO unit value', 'CWON unit value',
                                    np.where(base['price'].notna(), 'CWON filled', 'no price'))
    reported = value_of_production[value_of_production['element'] == consts.EL_VALUE_USD][keys + ['value']].rename(
        columns={'value': 'gross_value_fao_reported_usd'})
    reported['gross_value_fao_reported_usd'] *= 1000.0
    base = base.merge(reported, on=keys, how='left')
    print('CWON method: %d crop-country-years, %d without any price.' % (len(base), int(base['price'].isna().sum())))
    return base[keys + ['production_t', 'price', 'price_source', 'gross_value_usd', 'value_source',
                        'gross_value_fao_reported_usd']]


def country_year_totals(by_crop, cpi, countries, discount, horizon, deflator, base_year):
    """Sum the crops of each country and year.

    Args:
        by_crop: Crop table with gross_value_usd, gep_value, rental_rate, rental_rate_source and price_source.
        cpi: CPI index from ``utils.load_cpi``.
        countries: Country table from ``load_countries``.
        discount: Discount rate of the asset value (``consts.DISCOUNT``).
        horizon: Horizon of the asset value in years (``consts.HORIZON``).
        deflator: ``consts.DEFLATOR``.
        base_year: ``consts.BASE_YEAR``.

    Returns:
        One row per country and year with gross_value_usd, gep_value, rental_rate, rental_rate_source, n_crops,
        gross_value_regional_price_usd (valued at regional or world prices), crop_wealth_usd (asset value of the
        rent), the deflator columns of ``utils.deflate`` and Country.
    """
    valued = by_crop[by_crop['gep_value'].notna()]
    totals = (valued.groupby(['alpha-3', 'Year'])
              .agg(gross_value_usd=('gross_value_usd', 'sum'),
                   gep_value=('gep_value', 'sum'),
                   rental_rate=('rental_rate', 'first'),
                   rental_rate_source=('rental_rate_source', 'first'),
                   n_crops=('item_code', 'nunique'))
              .reset_index())
    regional = valued[valued['price_source'].isin(consts.REGIONAL_PRICE_SOURCES)]
    totals = totals.merge(regional.groupby(['alpha-3', 'Year'])['gross_value_usd'].sum()
                          .rename('gross_value_regional_price_usd'), on=['alpha-3', 'Year'], how='left')
    totals['gross_value_regional_price_usd'] = totals['gross_value_regional_price_usd'].fillna(0)
    totals['crop_wealth_usd'] = totals['gep_value'] * (1 - (1 + discount) ** -horizon) / discount
    totals = deflate(totals, ['gep_value'], cpi, deflator, base_year)
    return totals.merge(countries[['alpha-3', 'name']].rename(columns={'name': 'Country'}), on='alpha-3', how='left')


def price_source_shares(by_crop):
    """Return each year's gross value by value source and price source.

    Args:
        by_crop: Crop table with Year, value_source, price_source and gross_value_usd.

    Returns:
        DataFrame with Year, value_source, price_source, n_crop_country, gross_value_usd and share_of_year.
    """
    sources = (by_crop.groupby(['Year', 'value_source', 'price_source'], dropna=False)['gross_value_usd']
               .agg(['count', 'sum']).reset_index()
               .rename(columns={'count': 'n_crop_country', 'sum': 'gross_value_usd'}))
    sources['share_of_year'] = sources['gross_value_usd'] / sources.groupby('Year')['gross_value_usd'].transform('sum')
    return sources


def print_summary(by_crop, by_country, base_year):
    """Print the base-year totals, the value by source and the largest values from production x price.

    Args:
        by_crop: Crop table.
        by_country: Country-year table from ``country_year_totals``.
        base_year: ``consts.BASE_YEAR``.
    """
    reported_sources = ['FAO reported', 'CWON unit value']
    filled_sources = ['production x price', 'CWON filled']
    base = by_country[by_country['Year'] == base_year]
    settings = ("METHOD = 'cwon'" if consts.METHOD == 'cwon' else
                'VALUE_BASIS = %r, REGIONAL_PRICE = %r' % (consts.VALUE_BASIS, consts.REGIONAL_PRICE))
    print('Commercial crop provision %d (%s): gross value %.2f bn USD, GEP (rent) %.2f bn USD, %d countries.'
          % (base_year, settings, base['gross_value_usd'].sum() / 1e9, base['gep_value'].sum() / 1e9, len(base)))
    crops = by_crop[by_crop['gep_value'].notna() & (by_crop['Year'] == base_year)]
    reported = crops['value_source'].isin(reported_sources)
    filled = crops['value_source'].isin(filled_sources)
    print('  %d gross value: FAO reported value / unit value %.2f bn, filled from prices %.2f bn (of which '
          'regional or world prices %.2f bn).'
          % (base_year, crops.loc[reported, 'gross_value_usd'].sum() / 1e9,
             crops.loc[filled, 'gross_value_usd'].sum() / 1e9,
             crops.loc[crops['price_source'].isin(consts.REGIONAL_PRICE_SOURCES), 'gross_value_usd'].sum() / 1e9))
    if consts.METHOD == 'cwon':
        target = by_country[by_country['Year'] == consts.CWON_TARGET_YEAR]
        print('  %d GEP (rent) %.2f bn USD; CWON 2024 published: %.2f bn USD (%s bn wealth / %s).'
              % (consts.CWON_TARGET_YEAR, target['gep_value'].sum() / 1e9,
                 consts.CWON_PUBLISHED_2020_WEALTH_BN / consts.CWON_ANNUITY_FACTOR,
                 '{:,}'.format(consts.CWON_PUBLISHED_2020_WEALTH_BN), consts.CWON_ANNUITY_FACTOR))
        print('  %d gross value by CWON price source (bn USD):\n%s'
              % (base_year, (crops.groupby('price_source')['gross_value_usd'].sum() / 1e9).round(2)
                 .sort_values(ascending=False).to_string()))
    largest = crops[filled].nlargest(consts.N_LARGEST_PRINTED, 'gross_value_usd')
    print('  Largest %d values from production x price (check these first):\n%s'
          % (base_year, largest[['alpha-3', 'crop', 'production_t', 'price', 'price_source', 'gross_value_usd']]
             .to_string(index=False)))


def run():
    """Compute commercial crop provision by crop, by country and year, and the value by price source.

    Returns:
        Dict with ``cpi_index`` (CPI per country and year, base year = 100), ``commercial_by_crop`` (one row per
        country, crop and year with price, price source, gross value, rental rate and GEP),
        ``commercial_by_country`` (one row per country and year) and ``commercial_price_sources``.

    Raises:
        ValueError: Unknown ``consts.METHOD``.
    """
    if consts.METHOD not in ('gep', 'cwon'):
        raise ValueError("METHOD must be 'gep' or 'cwon'")
    rental_rates = load_rental_rates(input_path('rental_rates'))
    cpi = load_cpi(input_path('cpi'), consts.BASE_YEAR)
    countries = load_countries(input_path('iso'), consts.REGION_OVERRIDES)
    names = item_names(input_path('production_value')).combine_first(item_names(input_path('production')))
    crop_list = consts.CROP_LIST
    if consts.METHOD == 'cwon':
        print("METHOD = 'cwon': CWON 2024 exactly; CROP_LIST, VALUE_BASIS, REGIONAL_PRICE and OUTLIER_RULE "
              "are not used.")
        crop_list = 'cwon'
    value_of_production, _ = load_faostat(input_path('production_value'), [consts.EL_VALUE_USD, consts.EL_VALUE_SLC],
                                          None, countries)
    items = crop_universe(value_of_production, names, crop_list, input_path('crop_list'))
    production, belgium_luxembourg = load_faostat(input_path('production'), [consts.EL_PRODUCTION], items, countries)
    production = split_belgium_luxembourg(production, belgium_luxembourg, consts.BLX_SPLIT_YEAR,
                                          consts.BLX_LAND_AREA_KM2)
    producer_prices, _ = load_faostat(input_path('prices'), [consts.EL_PRICE_USD, consts.EL_PRICE_SLC], items,
                                      countries)
    fx = load_wdi_fx(input_path('wdi_fx'))

    if consts.METHOD == 'cwon':
        by_crop = cwon_values(production, producer_prices, value_of_production, countries, items, fx,
                              input_path('rental_rates'), input_path('trade'),
                              (consts.CWON_FIRST_YEAR, consts.CWON_TARGET_YEAR), consts.PRICE_SUBSTITUTES,
                              consts.CWON_IQR_MULTIPLIER)
    else:
        reported = value_of_production[value_of_production['item_code'].isin(items)
                                       & (value_of_production['element'] == consts.EL_VALUE_USD)]
        observed = country_prices(producer_prices, fx, consts.OUTLIER_RULE, consts.MAX_RATIO_TO_WORLD_MEDIAN,
                                  consts.CWON_IQR_MULTIPLIER, consts.USD_COPY_FX_TOLERANCE, consts.USD_COPY_RTOL)
        prices = interpolate_prices(substitute_prices(observed, consts.PRICE_SUBSTITUTES))
        by_crop = commercial_values(production, prices, observed, countries, reported, consts.REGIONAL_PRICE,
                                    consts.VALUE_BASIS)
    by_crop = by_crop[(by_crop['Year'] >= consts.COMMERCIAL_FIRST_YEAR)
                      & ~by_crop['alpha-3'].isin(consts.CWON_DROPPED_COUNTRIES)]
    by_crop = attach_rental_rates(by_crop, rental_rates)
    by_crop['gep_value'] = by_crop['gross_value_usd'] * by_crop['rental_rate']
    by_crop['crop'] = by_crop['item_code'].map(names)
    no_rate = by_crop[by_crop['rental_rate'].isna() & by_crop['gross_value_usd'].notna()]
    print('No CWON rental rate (no rent, as in CWON): %s.' % sorted(no_rate['alpha-3'].unique()))

    by_country = country_year_totals(by_crop, cpi, countries, consts.DISCOUNT, consts.HORIZON, consts.DEFLATOR,
                                     consts.BASE_YEAR)
    print_summary(by_crop, by_country, consts.BASE_YEAR)
    return {'cpi_index': cpi,
            'commercial_by_crop': by_crop,
            'commercial_by_country': by_country,
            'commercial_price_sources': price_source_shares(by_crop)}

