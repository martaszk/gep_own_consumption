"""Step 05: smallholder own consumption for every country and year with crop production value.

Years ``consts.OC_FIRST_YEAR`` to ``consts.OC_LAST_YEAR``, current USD, and the tables of the GEP base year::

    own_con2 (USD) = V x a / 100 x o / 100

- V: crop production value, current USD, by ``consts.V_SOURCE``: 'faostat' is FAOSTAT Value of Agricultural
  Production, "Crops"; 'faostat_fill' the same, with the gross value of step 04 where FAOSTAT has none;
  'commercial' the gross value of step 04 for every country. ``consts.V_BREAK_FIX`` holds a country's prices at
  the year before a break in the value series. crop_value_source records which was used.
- a: smallholder share (% of crop value from small farms) from step 02, and for RuLIS countries the yearly path
  from step 03.
- o: own-consumption share of small farms (%) from step 03, or ``consts.OWN_SHARE_OVERRIDES``.

Countries without a or o take the median of the donor countries in the same World Bank region if there are at
least ``consts.MIN_COUNTRIES_FOR_REGIONAL_MEDIAN`` donors, else in the same UN region (continent), else the global
median; the value is constant over time and flagged in the *_source columns. Donors of a are the countries with a
source in step 02; donors of o are the surveyed countries' base-year values from step 03. An imputed a never
exceeds the Lowder upper bound of a country whose census has no class below 2 ha.

Countries of the income groups in ``consts.EXCLUDE_INCOME_GROUPS`` are left out of the panel; they are listed in
their own table and still serve as donors. The groups are the World Bank classification based on the GNI per capita
of ``consts.INCOME_GROUP_YEAR`` (None: the base year), one classification for every year of the panel.
"""
import re

import numpy as np
import pandas as pd

import consts
from utils import deflate, input_path, load_cpi, load_iso, load_wb_income, read_fao_csv


def read_crop_value_usd(path, iso):
    """Read FAOSTAT Value of Agricultural Production, item "Crops", in current USD per country and year.

    Args:
        path: FAOSTAT Value of Production bulk file (wide layout).
        iso: ISO table from ``utils.load_iso`` (columns m49, alpha-3).

    Returns:
        DataFrame with alpha-3, Year and crop_value_usd (positive values only).

    Raises:
        ValueError: The file has no "Crops" rows.
    """
    header = read_fao_csv(path, nrows=0).columns
    year_columns = [c for c in header if re.fullmatch(r'Y\d{4}', c)]
    table = read_fao_csv(path, low_memory=False,
                         usecols=['Area Code', 'Area Code (M49)', 'Item Code', 'Item', 'Element Code'] + year_columns)
    table = table[(table['Element Code'] == consts.EL_VALUE_USD) & (table['Area Code'] < consts.FAO_FIRST_REGION_CODE)
                  & (table['Area Code'] != consts.FAO_CHINA_AGGREGATE)]
    crops = table[table['Item Code'] == consts.FAO_QV_CROPS_ITEM_CODE]
    if crops.empty:
        aggregates = table.loc[table['Item Code'] > consts.FAO_FIRST_AGGREGATE_ITEM_CODE,
                               ['Item Code', 'Item']].drop_duplicates().values.tolist()
        raise ValueError('No "Crops" rows (item %d) in %s. Aggregate items in the file: %s'
                         % (consts.FAO_QV_CROPS_ITEM_CODE, path, aggregates))
    crops = crops.copy()
    crops['m49'] = pd.to_numeric(crops['Area Code (M49)'].astype(str).str.replace("'", ''), errors='coerce')
    crops['alpha-3'] = crops['m49'].replace(consts.M49_SUCCESSORS).map(dict(zip(iso['m49'], iso['alpha-3'])))
    long = crops.dropna(subset=['alpha-3']).melt(id_vars=['alpha-3'], value_vars=year_columns,
                                                 var_name='Year', value_name='crop_value_usd')
    long['Year'] = long['Year'].str[1:].astype(int)
    long['crop_value_usd'] = pd.to_numeric(long['crop_value_usd'], errors='coerce') * 1000.0
    long = long[long['crop_value_usd'] > 0]
    return long.groupby(['alpha-3', 'Year'], as_index=False)['crop_value_usd'].sum()


def crop_value_panel(fao_values, source, break_fix, crops, base_year):
    """Build the crop production value V per country and year.

    Args:
        fao_values: FAOSTAT values from ``read_crop_value_usd``.
        source: 'faostat', 'faostat_fill' or 'commercial' (``consts.V_SOURCE``).
        break_fix: Dict of country -> last year before a break in its value series (``consts.V_BREAK_FIX``).
        crops: Crop table of step 04 (alpha-3, item_code, Year, production_t, gross_value_usd), production > 0.
        base_year: GEP base year, for the printed effect of a break fix.

    Returns:
        DataFrame with alpha-3, Year, crop_value_usd and crop_value_source; positive values only.

    Raises:
        ValueError: Unknown source.
    """
    if source not in ('faostat', 'faostat_fill', 'commercial'):
        raise ValueError("V_SOURCE must be 'faostat', 'faostat_fill' or 'commercial'")
    fao = fao_values[['alpha-3', 'Year', 'crop_value_usd']].rename(columns={'crop_value_usd': 'v_fao'})
    if source == 'faostat' and not break_fix:
        return fao.rename(columns={'v_fao': 'crop_value_usd'}).assign(crop_value_source='FAOSTAT QV Crops')
    commercial = (crops.groupby(['alpha-3', 'Year'])['gross_value_usd'].sum(min_count=1)
                  .rename('v_commercial').reset_index().dropna(subset=['v_commercial']))
    commercial = commercial[commercial['v_commercial'] > 0]
    last_year = int(commercial['Year'].max())
    values = fao.merge(commercial, on=['alpha-3', 'Year'], how='outer')
    if source == 'faostat':
        values['crop_value_usd'], values['crop_value_source'] = values['v_fao'], 'FAOSTAT QV Crops'
    elif source == 'faostat_fill':
        values['crop_value_usd'] = values['v_fao'].fillna(values['v_commercial'])
        values['crop_value_source'] = np.where(values['v_fao'].notna(), 'FAOSTAT QV Crops',
                                               np.where(values['v_commercial'].notna(),
                                                        'commercial gross value (FAOSTAT missing)', None))
    else:
        values['crop_value_usd'] = values['v_commercial']
        values['crop_value_source'] = np.where(values['v_commercial'].notna(), 'commercial gross value', None)
    if source != 'faostat':
        values = extend_after_last_year(values, fao, last_year)
    for code, break_year in break_fix.items():
        values = apply_break_fix(values, crops, code, break_year, base_year)
    values = values[values['crop_value_usd'] > 0]
    return values[['alpha-3', 'Year', 'crop_value_usd', 'crop_value_source']]


def extend_after_last_year(values, fao, last_year):
    """Fill the years after the last year of step 04 for the sources that use its gross value.

    Where FAOSTAT reports, V = FAOSTAT x the country's commercial / FAOSTAT ratio of the last year; otherwise the
    last-year commercial value is held. Countries without any row after the last year get the held value for every
    later FAOSTAT year.

    Args:
        values: Table with alpha-3, Year, v_fao, v_commercial, crop_value_usd and crop_value_source.
        fao: FAOSTAT values (alpha-3, Year, v_fao).
        last_year: Last year with a commercial value.

    Returns:
        Copy of ``values`` with the later years filled.
    """
    values = values.copy()
    reference = values[values['Year'] == last_year].set_index('alpha-3')
    ratio = (reference['v_commercial'] / reference['v_fao']).replace([np.inf, -np.inf], np.nan)
    late = (values['Year'] > last_year) & values['crop_value_usd'].isna()
    scaled = values.loc[late, 'v_fao'] * values.loc[late, 'alpha-3'].map(ratio)
    held = values.loc[late, 'alpha-3'].map(reference['v_commercial'])
    values.loc[late, 'crop_value_usd'] = scaled.fillna(held)
    values.loc[late, 'crop_value_source'] = np.where(
        scaled.notna(), 'FAOSTAT x commercial/FAOSTAT ratio of %d' % last_year,
        np.where(held.notna(), 'commercial gross value of %d held' % last_year, None))
    have = set(zip(values['alpha-3'], values['Year']))
    later_years = sorted(year for year in fao['Year'].unique() if year > last_year)
    added = [{'alpha-3': code, 'Year': year, 'crop_value_usd': value,
              'crop_value_source': 'commercial gross value of %d held' % last_year}
             for code, value in reference['v_commercial'].dropna().items() for year in later_years
             if (code, year) not in have]
    if added:
        values = pd.concat([values, pd.DataFrame(added)], ignore_index=True)
    return values


def apply_break_fix(values, crops, code, break_year, base_year):
    """Value a country's crops at constant prices of the year before a break in its value series.

    From the year after the break, V(t) = V(break year) x production(t) at break-year prices / production(break
    year) at break-year prices, crop by crop: the series keeps the quantity change but not the price jump. Years
    without production hold the last production year.

    Args:
        values: Crop value table (alpha-3, Year, crop_value_usd, crop_value_source).
        crops: Crop table of step 04 (alpha-3, item_code, Year, production_t, gross_value_usd).
        code: ISO3 code of the country.
        break_year: Last year before the break.
        base_year: GEP base year, for the printed effect.

    Returns:
        Copy of ``values`` with the country's later years replaced; unchanged (with a warning) if the country has
        no value or production in the break year.
    """
    values = values.copy()
    country = crops[crops['alpha-3'] == code]
    break_rows = country[country['Year'] == break_year]
    prices = break_rows.assign(p=break_rows['gross_value_usd'] / break_rows['production_t'])
    prices = prices.dropna(subset=['p']).set_index('item_code')['p']
    priced = country[country['item_code'].isin(prices.index)]
    quantity = priced.assign(q=priced['production_t'] * priced['item_code'].map(prices)).groupby('Year')['q'].sum()
    rows = values['alpha-3'] == code
    break_value = values.loc[rows & (values['Year'] == break_year), 'crop_value_usd']
    if break_value.empty or break_value.isna().all() or break_year not in quantity.index:
        print('WARNING: V_BREAK_FIX %s: no value or production in %d; not applied.' % (code, break_year))
        return values
    after = rows & (values['Year'] > break_year)
    later = quantity.index > break_year
    quantity_after = values.loc[after, 'Year'].map(quantity).fillna(
        quantity[later].iloc[-1] if later.any() else quantity[break_year])
    before = values.loc[after & (values['Year'] == base_year), 'crop_value_usd'].sum()
    values.loc[after, 'crop_value_usd'] = float(break_value.iloc[0]) * quantity_after / quantity[break_year]
    values.loc[after, 'crop_value_source'] = (values.loc[after, 'crop_value_source'].astype(str)
                                              + '; break fix: %d prices' % break_year)
    now = values.loc[after & (values['Year'] == base_year), 'crop_value_usd'].sum()
    print('  V_BREAK_FIX %s: from %d at %d prices; %d value %.2f -> %.2f bn USD.'
          % (code, break_year + 1, break_year, base_year, before / 1e9, now / 1e9))
    return values


def load_regions(iso, wb_income, region_overrides):
    """Return the regions used for imputation.

    Args:
        iso: ISO table from ``utils.load_iso``.
        wb_income: World Bank table from ``utils.load_wb_income``.
        region_overrides: Dict of ISO3 -> (subregion, UN region) for countries the ISO table gives no region
            (``consts.REGION_OVERRIDES``, also used by step 04).

    Returns:
        DataFrame with alpha-3, iso_name, Continent (UN region, e.g. "Africa") and Region (World Bank region).
    """
    regions = iso[['alpha-3', 'name', 'sub-region', 'region']].rename(
        columns={'name': 'iso_name', 'sub-region': 'Region', 'region': 'Continent'})
    regions = regions.replace({'Region': {'': np.nan}, 'Continent': {'': np.nan}})
    for code, (_, region) in region_overrides.items():
        regions.loc[regions['alpha-3'] == code, 'Continent'] = region
    world_bank = wb_income.dropna(subset=['Region']).drop_duplicates('alpha-3')
    return regions.drop(columns='Region').merge(world_bank[['alpha-3', 'Region']], on='alpha-3', how='left')


def impute_by_region(table, value_column, source_column, donors, regions, label, min_countries):
    """Fill missing values with the median of the donor countries in the same region.

    The region is the World Bank region; with fewer than ``min_countries`` donors there, the UN region
    (continent); else the global median.

    Args:
        table: DataFrame with alpha-3, ``value_column`` and ``source_column`` (and optionally Region, Continent).
        value_column: Column to fill.
        source_column: Column that records where each value comes from.
        donors: Donor countries (alpha-3, ``value_column``), one row per country.
        regions: Regions (alpha-3, Region, Continent).
        label: Name of the value, for the printed medians.
        min_countries: Fewest donors for a regional median.

    Returns:
        Tuple (copy of ``table`` with the gaps filled and labelled, table of the medians by level).
    """
    donors = donors.dropna(subset=[value_column]).drop_duplicates('alpha-3').merge(regions, on='alpha-3', how='left')
    by_region = donors.groupby('Region')[value_column].agg(['median', 'count'])
    by_continent = donors.groupby('Continent')[value_column].agg(['median', 'count'])
    global_median = donors[value_column].median()
    out = table.copy()
    if 'Region' not in out:
        out = out.merge(regions[['alpha-3', 'Region', 'Continent']], on='alpha-3', how='left')
    missing = out[value_column].isna()
    from_region = out.loc[missing, 'Region'].map(by_region.loc[by_region['count'] >= min_countries, 'median'])
    from_continent = out.loc[missing, 'Continent'].map(
        by_continent.loc[by_continent['count'] >= min_countries, 'median'])
    out.loc[missing, value_column] = from_region.fillna(from_continent).fillna(global_median)
    out.loc[missing, source_column] = np.where(
        from_region.notna(), 'median of ' + out.loc[missing, 'Region'].astype(str) + ' (n='
        + out.loc[missing, 'Region'].map(by_region['count']).fillna(0).astype(int).astype(str) + ')',
        np.where(from_continent.notna(), 'median of ' + out.loc[missing, 'Continent'].astype(str) + ' (n='
                 + out.loc[missing, 'Continent'].map(by_continent['count']).fillna(0).astype(int).astype(str) + ')',
                 'global median (n=%d)' % len(donors)))
    summary = pd.concat([by_region.reset_index().rename(columns={'Region': 'group'}).assign(level='region'),
                         by_continent.reset_index().rename(columns={'Continent': 'group'}).assign(level='UN region'),
                         pd.DataFrame([{'group': 'World', 'median': global_median, 'count': len(donors),
                                        'level': 'global'}])],
                        ignore_index=True)
    summary['used_if_needed'] = (summary['count'] >= min_countries) | (summary['level'] == 'global')
    summary = summary.rename(columns={'median': 'median_' + value_column, 'count': 'n_countries'})
    print('  %s medians:\n%s' % (label, summary.round(2).to_string(index=False)))
    return out, summary


def add_smallholder_share(panel, smallholder_share, smallholder_share_panel, regions, min_countries):
    """Add the smallholder share a of each country and year.

    Args:
        panel: Crop value panel with alpha-3 and Year.
        smallholder_share: Shares of step 02 (alpha-3, a_pct, a_source, a_year, a_upper_bound_pct).
        smallholder_share_panel: Yearly path of step 03 for RuLIS countries (alpha-3, Year, a_pct, a_path_source).
        regions: Regions from ``load_regions``.
        min_countries: Fewest donors for a regional median.

    Returns:
        Tuple (panel with smallholder_share_pct, smallholder_share_source and smallholder_share_year, table of the
        medians used for imputation).
    """
    shares = smallholder_share[['alpha-3', 'a_pct', 'a_source', 'a_year', 'a_upper_bound_pct']]
    countries = pd.DataFrame({'alpha-3': panel['alpha-3'].unique()}).merge(shares, on='alpha-3', how='left')
    countries, summary = impute_by_region(countries, 'a_pct', 'a_source', shares[['alpha-3', 'a_pct']],
                                          regions[['alpha-3', 'Region', 'Continent']], 'Smallholder share a (%)',
                                          min_countries)
    capped = countries['a_upper_bound_pct'].notna() & (countries['a_pct'] > countries['a_upper_bound_pct'])
    countries.loc[capped, 'a_pct'] = countries.loc[capped, 'a_upper_bound_pct']
    countries.loc[capped, 'a_source'] = 'Lowder upper bound (smallest census class starts above 2 ha)'
    if capped.any():
        print('  Imputed smallholder share capped by the Lowder upper bound: %s'
              % sorted(countries.loc[capped, 'alpha-3']))
    panel = panel.merge(countries[['alpha-3', 'a_pct', 'a_source', 'a_year']], on='alpha-3', how='left')
    if len(smallholder_share_panel):
        panel = panel.merge(smallholder_share_panel[['alpha-3', 'Year', 'a_pct', 'a_path_source']]
                            .rename(columns={'a_pct': '_a_t'}), on=['alpha-3', 'Year'], how='left')
        on_path = panel['_a_t'].notna()
        panel.loc[on_path, 'a_pct'] = panel.loc[on_path, '_a_t']
        panel.loc[on_path, 'a_source'] = panel.loc[on_path, 'a_path_source']
        panel = panel.drop(columns=['_a_t', 'a_path_source'])
    panel = panel.rename(columns={'a_pct': 'smallholder_share_pct', 'a_source': 'smallholder_share_source',
                                  'a_year': 'smallholder_share_year'})
    return panel, summary


def add_own_share(panel, own_share_panel, overrides, regions, base_year, min_countries):
    """Add the own-consumption share o of each country and year.

    Args:
        panel: Crop value panel with alpha-3 and Year.
        own_share_panel: Yearly own-consumption share of step 03 (alpha-3, Year, own_share_pct, share_source,
            own_share_basis, nearest_survey_year).
        overrides: Dict of ISO3 -> (share %, note) for countries without a survey (``consts.OWN_SHARE_OVERRIDES``).
        regions: Regions from ``load_regions``.
        base_year: Year of the donors' values.
        min_countries: Fewest donors for a regional median.

    Returns:
        Tuple (panel with own_share_pct, own_con_source, own_share_basis and nearest_survey_year, table of the
        medians used for imputation).
    """
    panel = panel.merge(own_share_panel[['alpha-3', 'Year', 'own_share_pct', 'share_source', 'own_share_basis',
                                         'nearest_survey_year']], on=['alpha-3', 'Year'], how='left')
    panel = panel.rename(columns={'share_source': 'own_con_source'})
    for code, (value, note) in overrides.items():
        rows = (panel['alpha-3'] == code) & panel['own_share_pct'].isna()
        panel.loc[rows, 'own_share_pct'] = value
        panel.loc[rows, 'own_con_source'] = 'set: ' + note
        if rows.any():
            print('  Own-consumption share set for %s: %.1f%% (%s)' % (code, value, note))
    donors = own_share_panel[(own_share_panel['Year'] == base_year)].dropna(subset=['own_share_pct'])[
        ['alpha-3', 'own_share_pct']]
    return impute_by_region(panel, 'own_share_pct', 'own_con_source', donors,
                            regions[['alpha-3', 'Region', 'Continent']],
                            'Own-consumption share o (%%), donors = surveyed countries in %d' % base_year,
                            min_countries)


def load_income_groups(path, gni_year, sheet, codes):
    """Read the World Bank income group of every economy from the classification based on one year's GNI per capita.

    Args:
        path: World Bank historical classification by income (OGHIST): one column per fiscal year, the row
            "Bank's fiscal year" with its label and the row "Data for calendar year" with the year of the GNI per
            capita it is based on; one row per economy with its ISO3 code and the codes L, LM, UM or H.
        gni_year: Year of the GNI per capita (2019 selects FY21, published July 2020).
        sheet: Sheet with the classification (``consts.WB_INCOME_SHEET``).
        codes: Dict of code -> income group name (``consts.WB_INCOME_CODES``); other entries ('..', empty) mean
            not classified.

    Returns:
        Tuple (dict of ISO3 -> income group, for the economies classified that year; fiscal year label).

    Raises:
        ValueError: No classification in the file is based on ``gni_year``.
    """
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    labels = raw[1].astype(str).str.strip().str.lower()
    fiscal_years = raw.loc[labels.str.match(r'bank.s fiscal year')].iloc[0]
    year_row = labels.index[labels.str.match('data for calendar year')][0]
    gni_years = pd.to_numeric(raw.loc[year_row], errors='coerce')
    if gni_year not in set(gni_years.dropna()):
        raise ValueError('%s has no income classification based on GNI per capita of %s (GNI years %d-%d); '
                         'set INCOME_GROUP_YEAR.' % (path.name, gni_year, gni_years.min(), gni_years.max()))
    column = gni_years.index[gni_years == gni_year][0]
    economies = raw.loc[year_row + 1:, [0, column]]
    economies = economies[economies[0].astype(str).str.fullmatch('[A-Z]{3}')]
    groups = economies[column].astype(str).str.strip().str.rstrip('*').map(codes)
    classified = groups.notna()
    return dict(zip(economies.loc[classified, 0], groups[classified])), fiscal_years[column]


def exclude_income_groups(panel, income_groups, groups, additions, base_year):
    """Add each country's World Bank income group and leave out the countries of the given groups.

    Args:
        panel: Own-consumption panel with alpha-3, Year and own_con2.
        income_groups: Dict of ISO3 -> World Bank income group, from ``load_income_groups``.
        groups: Income groups to leave out (``consts.EXCLUDE_INCOME_GROUPS``); () keeps every country.
        additions: Dict of ISO3 -> income group for countries the World Bank classification gives none
            (``consts.INCOME_GROUP_ADDITIONS``); used only where it has no group.
        base_year: GEP base year.

    Returns:
        Tuple (panel without those countries, with the column income_group; base-year rows of the countries left
        out, empty if none).

    Raises:
        ValueError: A group in ``groups`` does not occur in the World Bank classification.
    """
    income_group = dict(income_groups)
    for code, group in additions.items():
        if pd.isna(income_group.get(code)):
            income_group[code] = group
    unknown = sorted(set(groups) - set(income_group.values()))
    if unknown:
        raise ValueError('EXCLUDE_INCOME_GROUPS has %s, not a World Bank income group (groups: %s).'
                         % (unknown, sorted(set(income_group.values()))))
    panel = panel.copy()
    panel['income_group'] = panel['alpha-3'].map(income_group)
    drop = panel['income_group'].isin(groups)
    excluded = panel[drop]
    excluded_base = excluded[excluded['Year'] == base_year]
    if groups:
        print('  Scope: %s left out: %d countries, %.1f bn USD own consumption in %d (largest: %s)'
              % (list(groups), excluded['alpha-3'].nunique(), excluded_base['own_con2'].sum() / 1e9, base_year,
                 ', '.join('%s %.1f' % (code, value / 1e9) for code, value in
                           excluded_base.sort_values('own_con2', ascending=False)[['alpha-3', 'own_con2']]
                           .head(5).values)))
    return panel[~drop], excluded_base


def source_kind(labels):
    """Group the source labels of a or o into kinds for the summary table.

    Args:
        labels: Series of source labels.

    Returns:
        Series of kinds: RuLIS paths become 'rulis', regional and global medians 'imputed: ...', capped shares
        'imputed, capped by Lowder upper bound', overrides 'set from another source'; other labels stay.
    """
    return (labels.str.replace(r'^RuLIS .*', 'rulis', regex=True)
            .str.replace(r'^median of .*', 'imputed: regional median', regex=True)
            .str.replace(r'^global median.*', 'imputed: global median', regex=True)
            .str.replace(r'^Lowder upper bound.*', 'imputed, capped by Lowder upper bound', regex=True)
            .str.replace(r'^set: .*', 'set from another source', regex=True))


def base_year_summary(base):
    """Sum the base-year own consumption by region, by source of a and by source of o.

    Args:
        base: Base-year rows of the panel (Region, smallholder_share_source, own_con_source, own_con2).

    Returns:
        DataFrame with group (region or source kind), own_consumption_usd, countries, by (what the group is) and
        share_of_total_pct.
    """
    base = base.copy()
    base['a_kind'] = source_kind(base['smallholder_share_source'])
    base['o_kind'] = source_kind(base['own_con_source'])
    summary = pd.concat([
        base.groupby('Region', dropna=False)['own_con2'].agg(['sum', 'count']).assign(by='Region'),
        base.groupby('a_kind')['own_con2'].agg(['sum', 'count']).assign(by='smallholder share source'),
        base.groupby('o_kind')['own_con2'].agg(['sum', 'count']).assign(by='own-consumption share source')])
    summary = summary.rename(columns={'sum': 'own_consumption_usd', 'count': 'countries'}).reset_index()
    summary = summary.rename(columns={'index': 'group'})
    summary['share_of_total_pct'] = 100 * summary['own_consumption_usd'] / base['own_con2'].sum()
    return summary


def run(smallholder_share, smallholder_share_panel, own_share_panel, commercial_by_crop):
    """Compute smallholder own consumption for every country and year.

    Args:
        smallholder_share: Shares of step 02.
        smallholder_share_panel: Yearly smallholder share of step 03.
        own_share_panel: Yearly own-consumption share of step 03.
        commercial_by_crop: Crop table of step 04 (alpha-3, item_code, Year, production_t, gross_value_usd).

    Returns:
        Dict with ``own_consumption_panel`` (every country and year), ``own_consumption_base_year``,
        ``own_consumption_summary`` (base-year totals by region and source), ``own_consumption_share_imputation``
        (the medians used for imputation) and ``own_consumption_excluded`` (base-year rows of the countries left
        out by ``consts.EXCLUDE_INCOME_GROUPS``).
    """
    base_year = consts.BASE_YEAR
    measured_sources = ['observed', 'survey year (fitted line)']
    columns = ['Country', 'Year', 'alpha-3', 'Region', 'crop_value_usd', 'crop_value_source',
               'smallholder_share_pct', 'smallholder_share_source', 'smallholder_share_year',
               'own_share_pct', 'own_con_source', 'own_share_basis', 'nearest_survey_year',
               'own_con', 'own_con2', 'own_con2_%d' % base_year, 'crop_value_usd_%d' % base_year]

    iso = load_iso(input_path('iso'))
    wb_income = load_wb_income(input_path('wb_income'))
    regions = load_regions(iso, wb_income, consts.REGION_OVERRIDES).drop_duplicates('alpha-3')
    print('  Regions: World Bank regions (%s), UN regions as second level.' % input_path('wb_income').name)

    crops = commercial_by_crop[['alpha-3', 'item_code', 'Year', 'production_t', 'gross_value_usd']]
    crops = crops[crops['production_t'] > 0]
    values = crop_value_panel(read_crop_value_usd(input_path('production_value'), iso), consts.V_SOURCE,
                              consts.V_BREAK_FIX, crops, base_year)
    panel = values[values['Year'].between(consts.OC_FIRST_YEAR, consts.OC_LAST_YEAR)].copy()
    panel = panel.merge(regions, on='alpha-3', how='left')
    panel['Country'] = panel['iso_name']
    print('05: crop production value for %d countries, %d-%d (V_SOURCE = %r, V_BREAK_FIX = %s); rows by source: %s'
          % (panel['alpha-3'].nunique(), consts.OC_FIRST_YEAR, consts.OC_LAST_YEAR, consts.V_SOURCE,
             consts.V_BREAK_FIX, panel['crop_value_source'].value_counts().to_dict()))

    panel, a_summary = add_smallholder_share(panel, smallholder_share, smallholder_share_panel, regions,
                                             consts.MIN_COUNTRIES_FOR_REGIONAL_MEDIAN)
    panel, o_summary = add_own_share(panel, own_share_panel, consts.OWN_SHARE_OVERRIDES, regions, base_year,
                                     consts.MIN_COUNTRIES_FOR_REGIONAL_MEDIAN)
    imputation = pd.concat([a_summary.assign(term='smallholder share a'),
                            o_summary.assign(term='own-consumption share o')], ignore_index=True)

    panel['own_con2'] = (panel['crop_value_usd'] * panel['smallholder_share_pct'] / 100.0
                         * panel['own_share_pct'] / 100.0)
    panel['own_con'] = np.where(panel['own_con_source'].isin(measured_sources), panel['own_con2'], np.nan)
    panel = deflate(panel, ['own_con2', 'crop_value_usd'], load_cpi(input_path('cpi'), base_year), consts.DEFLATOR,
                    base_year)
    out = panel.loc[panel['own_con2'].notna(), columns].sort_values(['alpha-3', 'Year'])

    gni_year = base_year if consts.INCOME_GROUP_YEAR is None else consts.INCOME_GROUP_YEAR
    income_groups, fiscal_year = load_income_groups(input_path('wb_income_history'), gni_year, consts.WB_INCOME_SHEET,
                                                    consts.WB_INCOME_CODES)
    print('  Income groups: World Bank classification %s, based on GNI per capita of %d (%s).'
          % (fiscal_year, gni_year, input_path('wb_income_history').name))
    tables = {}
    out, tables['own_consumption_excluded'] = exclude_income_groups(out, income_groups, consts.EXCLUDE_INCOME_GROUPS,
                                                                    consts.INCOME_GROUP_ADDITIONS, base_year)
    base = out[out['Year'] == base_year].copy()
    summary = base_year_summary(base)
    print('05: %d country-years, %d countries. %d: smallholder own consumption %.1f bn USD in %d countries '
          '(%.1f%% of crop production value).'
          % (len(out), out['alpha-3'].nunique(), base_year, base['own_con2'].sum() / 1e9, len(base),
             100 * base['own_con2'].sum() / base['crop_value_usd'].sum()))
    print('  %d by source (bn USD, countries, %% of total):\n%s'
          % (base_year, summary.assign(own_consumption_usd=summary['own_consumption_usd'] / 1e9).round(1)
             .to_string(index=False)))
    tables.update({'own_consumption_panel': out, 'own_consumption_base_year': base,
                   'own_consumption_summary': summary, 'own_consumption_share_imputation': imputation})
    return tables

