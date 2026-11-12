"""Checks of the pipeline results, run by ``run.py`` after the last step.

Hard checks must pass: a failure makes ``run.py`` end with exit code 1. Flags point at results worth a look; they
do not fail the run. The checks run on the tables in memory; checks whose tables were not computed (``run.py
--until``) are skipped.
"""
import numpy as np

import consts


class CheckLog:
    """Collect and print the results of hard checks and flags."""

    def __init__(self):
        """Start with no failures and no flags."""
        self.failures = []
        self.flags = []

    def hard(self, passed, message):
        """Record a hard check.

        Args:
            passed: Whether the check passed.
            message: What was checked.
        """
        print(('  PASS  ' if passed else '  FAIL  ') + message)
        if not passed:
            self.failures.append(message)

    def flag(self, condition, message, detail=None):
        """Record a flag when its condition holds.

        Args:
            condition: Whether there is something to look at.
            message: What it is.
            detail: Optional object printed below the message.
        """
        if condition:
            self.flags.append(message)
            print('  FLAG  ' + message)
            if detail is not None:
                print('        ' + str(detail).replace('\n', '\n        '))


def first_codes(codes):
    """Return the first codes of a group in alphabetical order, for printing.

    Args:
        codes: Series of ISO3 codes.

    Returns:
        List of at most ``consts.CHECK_ROWS_SHOWN`` codes.
    """
    return sorted(codes)[:consts.CHECK_ROWS_SHOWN]


def check_own_consumption(log, observed, shares, panel, candidates):
    """Check the own-consumption chain: survey shares (steps 01, 03), smallholder share (02) and panel (05).

    Args:
        log: ``CheckLog``.
        observed: Observed own-consumption shares of step 01.
        shares: Yearly own-consumption shares of step 03.
        panel: Own-consumption panel of step 05.
        candidates: Smallholder-share candidates of step 02.
    """
    first, last, base_year = consts.OC_FIRST_YEAR, consts.OC_LAST_YEAR, consts.BASE_YEAR
    print('\n== Own consumption: structure')
    for name, table in [('observed shares', observed), ('yearly shares', shares), ('panel', panel)]:
        log.hard(not table.duplicated(['alpha-3', 'Year']).any(), f'{name}: unique alpha-3 x Year')
    log.hard(panel['Year'].between(first, last).all(), f'panel years within {first}-{last}')
    log.hard(panel['own_con2'].notna().all() and (panel['own_con2'] >= 0).all(), 'own_con2 present and >= 0')
    log.flag((panel['own_con2'] == 0).any(), 'own_con2 = 0 (smallholder share 0)',
             sorted(panel.loc[panel['own_con2'] == 0, 'alpha-3'].unique()))
    log.flag(panel['Region'].isna().any(), 'countries without a Region',
             sorted(panel.loc[panel['Region'].isna(), 'alpha-3'].unique()))
    log.flag(panel['income_group'].isna().any(), 'countries without an income group (never excluded)',
             sorted(panel.loc[panel['income_group'].isna(), 'alpha-3'].unique()))

    print('\n== Own consumption: ranges')
    for column in ['own_share_pct', 'smallholder_share_pct']:
        log.hard(panel[column].between(0, 100).all(), f'{column} in [0, 100]')
    log.hard((panel['own_con2'] <= panel['crop_value_usd']).all(), 'own consumption <= crop production value')
    high = panel['own_con2'] / panel['crop_value_usd'] > consts.CHECK_MAX_OWN_SHARE_OF_VALUE
    log.flag(high.any(), f'own consumption > {consts.CHECK_MAX_OWN_SHARE_OF_VALUE:.0%} of crop value',
             panel.loc[high, ['alpha-3', 'Year']].groupby('alpha-3')['Year'].agg(['min', 'max']))

    print('\n== Own consumption: own_con2 = crop value x a x o')
    recomputed = panel['crop_value_usd'] * panel['smallholder_share_pct'] * panel['own_share_pct'] / 1e4
    log.hard(np.allclose(recomputed, panel['own_con2'], rtol=consts.CHECK_RTOL), 'own_con2 reproduces')
    nonzero = panel[panel['own_con2'] > 0]
    factor_own = nonzero[f'own_con2_{base_year}'] / nonzero['own_con2']
    factor_value = nonzero[f'crop_value_usd_{base_year}'] / nonzero['crop_value_usd']
    log.hard(np.allclose(factor_own, factor_value, equal_nan=True),
             f'{base_year}-USD factor same for own_con2 and crop value')
    if consts.DEFLATOR == 'us_cpi':
        by_year = nonzero.assign(factor=factor_own).groupby('Year')['factor']
        log.hard(((by_year.max() - by_year.min()) < consts.CHECK_RTOL).all(), f'one {base_year}-USD factor per year')
    deflated = panel[f'own_con2_{base_year}'].notna()
    base_rows = deflated & (panel['Year'] == base_year)
    log.hard(np.allclose(panel.loc[base_rows, f'own_con2_{base_year}'], panel.loc[base_rows, 'own_con2']),
             f'{base_year}-USD factor = 1 in {base_year}')
    log.flag(not deflated.all(), f'no {base_year}-USD value (no CPI for the country and year)',
             sorted(panel.loc[~deflated, 'alpha-3'].unique()))
    observed_rows = panel['own_con_source'].isin(['observed', 'survey year (fitted line)'])
    log.hard(panel.loc[~observed_rows, 'own_con'].isna().all()
             and np.allclose(panel.loc[observed_rows, 'own_con'], panel.loc[observed_rows, 'own_con2']),
             'own_con only in survey years and equal to own_con2')

    print('\n== Own consumption: yearly path (step 03) vs surveys (step 01)')
    merged = shares.merge(observed[['alpha-3', 'Year', 'own_share_pct']], on=['alpha-3', 'Year'], how='left',
                          suffixes=('', '_survey'))
    survey_years = merged[merged['share_source'] == 'observed']
    log.hard(np.allclose(survey_years['own_share_pct'], survey_years['own_share_pct_survey']),
             'survey years equal the survey values')
    held = shares[shares['share_source'] == 'held from nearest survey'].merge(
        observed.rename(columns={'Year': 'nearest_survey_year', 'own_share_pct': 'survey_value'})
        [['alpha-3', 'nearest_survey_year', 'survey_value']], on=['alpha-3', 'nearest_survey_year'], how='left')
    log.hard(held['survey_value'].notna().all() and np.allclose(held['own_share_pct'], held['survey_value']),
             'held years equal the nearest survey')
    not_linear = []
    for code, rows in shares[shares['share_source'] == 'interpolated between surveys'].groupby('alpha-3'):
        surveys = observed[observed['alpha-3'] == code].set_index('Year')['own_share_pct']
        for _, row in rows.iterrows():
            before = surveys.index[surveys.index < row['Year']].max()
            after = surveys.index[surveys.index > row['Year']].min()
            line = surveys[before] + (surveys[after] - surveys[before]) * (row['Year'] - before) / (after - before)
            if abs(line - row['own_share_pct']) > consts.CHECK_INTERPOLATION_TOLERANCE:
                not_linear.append((code, row['Year']))
    log.hard(not not_linear, f'interpolation is linear between surveys {not_linear[:5]}')
    longest_hold = shares.groupby('alpha-3')['years_to_nearest_survey'].max()
    log.flag((longest_hold > consts.CHECK_MAX_YEARS_HELD).any(),
             f'share held > {consts.CHECK_MAX_YEARS_HELD} years from a survey',
             longest_hold[longest_hold > consts.CHECK_MAX_YEARS_HELD].sort_values(ascending=False).to_dict())
    jumps = observed.sort_values(['alpha-3', 'Year']).copy()
    jumps['jump_pts'] = jumps.groupby('alpha-3')['own_share_pct'].diff()
    jumps['prev_year'] = jumps.groupby('alpha-3')['Year'].shift()
    jumps = jumps[jumps['jump_pts'].abs() > consts.CHECK_MAX_SURVEY_JUMP]
    log.flag(len(jumps) > 0, f'own share jumps > {consts.CHECK_MAX_SURVEY_JUMP} points between consecutive surveys',
             jumps[['alpha-3', 'prev_year', 'Year', 'jump_pts', 'own_share_pct']].round(1).to_string(index=False))

    print('\n== Own consumption: the panel (step 05) carries the yearly shares (step 03)')
    carried = panel.merge(shares[['alpha-3', 'Year', 'own_share_pct']], on=['alpha-3', 'Year'],
                          suffixes=('', '_step03')).dropna(subset=['own_share_pct_step03'])
    log.hard(np.allclose(carried['own_share_pct'], carried['own_share_pct_step03']),
             'surveyed country-years keep their own share (years beyond MAX_SURVEY_AGE are imputed)')
    print('        surveyed countries outside the panel (income groups excluded, or no crop value V): '
          + str(sorted(set(shares['alpha-3']) - set(panel['alpha-3']))))
    donors = shares.loc[shares['Year'] == base_year, ['alpha-3', 'own_share_pct']].dropna().drop_duplicates('alpha-3')
    global_median = donors['own_share_pct'].median()
    global_rows = panel[panel['own_con_source'].str.startswith('global median', na=False)]
    log.hard(global_rows.empty or np.allclose(global_rows['own_share_pct'], global_median),
             f'global-median rows use {global_median:.2f} (median of the surveyed countries in {base_year})')
    africa = panel[(panel['Region'] == 'Middle East & North Africa')
                   & panel['own_con_source'].str.contains('Africa \\(', na=False)]
    log.flag(len(africa) > 0, 'MENA countries imputed with the Africa median (dominated by Sub-Saharan surveys)',
             sorted(africa['alpha-3'].unique()))

    print('\n== Own consumption: year coverage')
    span = panel.groupby('alpha-3')['Year'].agg(['min', 'max', 'count'])
    gaps = span[(span['max'] - span['min'] + 1) != span['count']]
    log.flag(not gaps.empty, 'years missing inside a country series (crop value V missing; expected with '
             "V_SOURCE = 'faostat')", list(gaps.index))
    partial = span['count'] < last - first + 1
    log.flag(partial.any(), 'countries with partial year coverage (crop value V missing)',
             span[partial].to_dict('index'))

    print(f'\n== Own consumption: concentration in {base_year}')
    base = panel[panel['Year'] == base_year]
    total = base['own_con2'].sum()
    top = (base.set_index('alpha-3')['own_con2'] / total * 100).sort_values(ascending=False).head(5).round(1)
    print(f'        total {total / 1e9:.2f} bn USD, {len(base)} countries; top-5 share of total: {top.to_dict()}')
    imputed = base[base['own_con_source'].str.contains('median', na=False)]['own_con2'].sum() / total * 100
    print(f'        own share imputed (median) for {imputed:.1f}% of the {base_year} value')

    print('\n== Smallholder share (step 02)')
    chosen = candidates.dropna(subset=['a_pct'])
    log.hard(chosen['a_pct'].between(0, 100).all(), 'a in [0, 100]')
    bounded = chosen.dropna(subset=['a_upper_bound_pct'])
    above = bounded['a_pct'] > bounded['a_upper_bound_pct']
    log.flag(above.any(), 'a above its Lowder upper bound',
             bounded.loc[above, ['alpha-3', 'a_pct', 'a_upper_bound_pct']])
    wide = chosen[(chosen['a_source'] == 'ricciardi_area')
                  & (chosen['ric_area_coverage'] > consts.CHECK_MAX_AREA_COVERAGE)]
    log.flag(len(wide) > 0, f'ricciardi_area used where census area > {consts.CHECK_MAX_AREA_COVERAGE} x FAO cropland',
             wide[['alpha-3', 'ric_year', 'ric_area_coverage', 'a_pct', 'rulis', 'lowder']].round(2)
             .to_string(index=False))
    sources = chosen[['rulis', 'lowder', 'ricciardi_observed', 'ricciardi_area']]
    spread = sources.max(axis=1) - sources.min(axis=1)
    disagree = chosen[(spread > consts.CHECK_MAX_SOURCE_SPREAD) & (sources.notna().sum(axis=1) >= 2)]
    log.flag(len(disagree) > 0, f'sources disagree by > {consts.CHECK_MAX_SOURCE_SPREAD} points',
             disagree[['alpha-3', 'a_source', 'a_pct', 'ricciardi_observed', 'ricciardi_area', 'rulis', 'lowder']]
             .round(1).to_string(index=False))
    old = chosen[chosen['a_year'] < consts.CHECK_OLD_SOURCE_YEAR]
    log.flag(len(old) > 0, f'a from a source before {consts.CHECK_OLD_SOURCE_YEAR}',
             dict(zip(old['alpha-3'], old['a_year'].astype(int))))


def check_crop_provision(log, subsistence, commercial, panel, by_crop, own_consumption):
    """Check subsistence GEP (step 06), commercial GEP (step 04) and the crop provision panel (step 06).

    Args:
        log: ``CheckLog``.
        subsistence: Subsistence GEP of step 06.
        commercial: Commercial country-year table of step 04.
        panel: Crop provision panel of step 06.
        by_crop: Commercial crop table of step 04.
        own_consumption: Own-consumption panel of step 05.
    """
    base_year, target_year = consts.BASE_YEAR, consts.CWON_TARGET_YEAR
    published_rent = consts.CWON_PUBLISHED_2020_WEALTH_BN / consts.CWON_ANNUITY_FACTOR
    large = consts.CHECK_LARGE_COUNTRY_USD
    print('\n== Crop provision: structure')
    for name, table in [('subsistence', subsistence), ('commercial', commercial), ('panel', panel)]:
        log.hard(not table.duplicated(['alpha-3', 'Year']).any(), f'{name}: unique alpha-3 x Year')
    for name, table in [('subsistence', subsistence), ('commercial', commercial)]:
        log.hard(table['rental_rate'].dropna().between(0, 1).all(), f'{name}: rental rate in [0, 1]')

    print('\n== Subsistence GEP (step 06)')
    rated = subsistence.dropna(subset=['rental_rate'])
    log.hard(np.allclose(rated['gep_value'], rated['own_con2'] * rated['rental_rate']),
             'gep_value = own_con2 x rental_rate')
    no_rate = subsistence[subsistence['rental_rate'].isna()]
    log.flag(len(no_rate) > 0, 'subsistence country-years without a CWON rental rate (no GEP)',
             no_rate.groupby('alpha-3')['Year'].agg(['min', 'max', 'count']).to_dict('index'))
    matched = subsistence.merge(own_consumption[['alpha-3', 'Year', 'own_con2']], on=['alpha-3', 'Year'],
                                how='outer', suffixes=('', '_step05'), indicator=True)
    log.hard((matched['_merge'] == 'both').all(), 'subsistence has exactly the country-years of step 05')
    both = matched[matched['_merge'] == 'both']
    log.hard(np.allclose(both['own_con2'], both['own_con2_step05']), 'own_con2 equals step 05')

    print('\n== Commercial GEP (step 04)')
    rated = commercial.dropna(subset=['rental_rate'])
    log.hard(np.allclose(rated['gep_value'], rated['gross_value_usd'] * rated['rental_rate'],
                         rtol=consts.CHECK_RTOL_ROUNDED), 'country gep_value = gross value x rental rate')
    annuity = (1 - (1 + consts.DISCOUNT) ** -consts.HORIZON) / consts.DISCOUNT
    log.hard(np.allclose(rated['crop_wealth_usd'], rated['gep_value'] * annuity, rtol=consts.CHECK_RTOL),
             f'crop wealth = rent x {annuity:.3f} (DISCOUNT, HORIZON)')
    log.flag(abs(annuity / consts.CWON_ANNUITY_FACTOR - 1) > consts.CHECK_RTOL_WEALTH,
             f'asset value factor {annuity:.3f} differs from CWON 2024 ({consts.CWON_ANNUITY_FACTOR})')
    target_rent = commercial.loc[commercial['Year'] == target_year, 'gep_value'].sum() / 1e9
    deviation = 100 * (target_rent / published_rent - 1)
    print(f'        {target_year} rent {target_rent:.1f} bn vs CWON published {published_rent:.1f} bn '
          f'({deviation:+.1f}%)')
    log.flag(abs(deviation) > consts.CHECK_MAX_CWON_DEVIATION_PCT,
             f'commercial {target_year} more than {consts.CHECK_MAX_CWON_DEVIATION_PCT}% from CWON published')
    yearly = commercial.sort_values(['alpha-3', 'Year']).copy()
    yearly['yoy'] = yearly.groupby('alpha-3')['gross_value_usd'].pct_change()
    jumps = yearly[(yearly['yoy'].abs() > consts.CHECK_MAX_YEAR_CHANGE) & (yearly['gross_value_usd'] > large)
                   & yearly['Year'].between(consts.OC_FIRST_YEAR, consts.OC_LAST_YEAR)]
    jumps = jumps.assign(gross_value_bn=jumps['gross_value_usd'] / 1e9)
    log.flag(len(jumps) > 0, f'gross value changes > {consts.CHECK_MAX_YEAR_CHANGE:.0%} year on year '
             f'(countries > {large / 1e9:g} bn USD)',
             jumps[['alpha-3', 'Year', 'gross_value_bn', 'yoy']].round(2).head(25).to_string(index=False))
    base = commercial[commercial['Year'] == base_year]
    base = base.assign(reg_share=base['gross_value_regional_price_usd'] / base['gross_value_usd'],
                       gross_value_bn=base['gross_value_usd'] / 1e9)
    regional = base[(base['reg_share'] > consts.CHECK_MAX_REGIONAL_SHARE) & (base['gross_value_usd'] > large)]
    log.flag(len(regional) > 0, f'{base_year}: > {consts.CHECK_MAX_REGIONAL_SHARE:.0%} of a country gross value '
             f'from regional or world prices (countries > {large / 1e9:g} bn USD)',
             regional[['alpha-3', 'gross_value_bn', 'reg_share']].sort_values('gross_value_bn', ascending=False)
             .round(2).to_string(index=False))

    print('\n== Commercial GEP (step 04): crops')
    valued = by_crop.dropna(subset=['gep_value'])
    log.hard(np.allclose(valued['gep_value'], valued['gross_value_usd'] * valued['rental_rate'],
                         rtol=consts.CHECK_RTOL_ROUNDED), 'crop gep_value = gross value x rental rate')
    sums = valued.groupby(['alpha-3', 'Year'])['gep_value'].sum().rename('sum_crops').reset_index()
    summed = commercial.merge(sums, on=['alpha-3', 'Year'], how='left')
    log.hard(np.allclose(summed['gep_value'], summed['sum_crops'], rtol=consts.CHECK_RTOL_ROUNDED),
             'country GEP = sum of crops')
    base_crops = by_crop[by_crop['Year'] == base_year]
    regional = base_crops[base_crops['gross_value_fao_reported_usd'].notna()
                          & base_crops['price_source'].isin(consts.REGIONAL_PRICE_SOURCES)]
    regional = regional.assign(ratio=regional['gross_value_usd'] / regional['gross_value_fao_reported_usd'])
    log.flag(len(regional) > 0, f'{base_year}: FAO reports a value but a regional/world price was used (largest '
             'first; cause: unit value missing, a single-year series dropped, or USD/SLC mismatch)',
             regional.nlargest(consts.CHECK_ROWS_SHOWN, 'gross_value_usd')
             [['alpha-3', 'crop', 'price_source', 'gross_value_usd', 'gross_value_fao_reported_usd', 'ratio']]
             .round(2).to_string(index=False))
    unit = base_crops[(base_crops['price_source'] == 'FAO unit value')
                      & base_crops['gross_value_fao_reported_usd'].notna()]
    unit = unit.assign(ratio=unit['gross_value_usd'] / unit['gross_value_fao_reported_usd'])
    off = unit[(unit['ratio'] - 1).abs() > consts.CHECK_MAX_UNIT_VALUE_GAP]
    log.flag(len(off) > 0, f'{base_year}: unit-value crops > {consts.CHECK_MAX_UNIT_VALUE_GAP:.0%} from the FAO '
             'reported value (outlier rule, interpolation, or forward-filled production)',
             off.nlargest(consts.CHECK_ROWS_SHOWN, 'gross_value_usd')
             [['alpha-3', 'crop', 'gross_value_usd', 'gross_value_fao_reported_usd', 'ratio']]
             .round(2).to_string(index=False))

    print('\n== Subsistence vs commercial (same country-year)')
    joined = subsistence.merge(commercial, on=['alpha-3', 'Year'], how='left', suffixes=('_s', '_c'))
    both = joined.dropna(subset=['rental_rate_s', 'rental_rate_c'])
    log.hard(np.allclose(both['rental_rate_s'], both['rental_rate_c']), 'same rental rate in steps 06 and 04')
    no_commercial = joined[joined['gross_value_usd'].isna()]
    log.flag(len(no_commercial) > 0, "subsistence country-years without a commercial value (METHOD = 'cwon' "
             'ends in the CWON target year)', no_commercial.groupby('Year')['alpha-3'].nunique().to_dict())
    joined = joined.dropna(subset=['gross_value_usd'])
    joined['sub_share'] = joined['own_con2'] / joined['gross_value_usd']
    log.hard((joined['sub_share'] <= 1).all(), 'own consumption <= commercial gross value')
    high = joined['sub_share'] > consts.CHECK_MAX_OWN_SHARE_OF_VALUE
    log.flag(high.any(), f'own consumption > {consts.CHECK_MAX_OWN_SHARE_OF_VALUE:.0%} of commercial gross value',
             joined.loc[high, ['alpha-3', 'Year', 'sub_share']].groupby('alpha-3')['sub_share'].max().round(2)
             .to_dict())
    values = own_consumption[['alpha-3', 'Year', 'crop_value_usd']].merge(
        commercial[['alpha-3', 'Year', 'gross_value_usd']], on=['alpha-3', 'Year'], how='inner')
    values['ratio'] = values['crop_value_usd'] / values['gross_value_usd']
    base_values = values[values['Year'] == base_year]
    print(f'        {base_year} V (step 05) / gross value (step 04): median {base_values["ratio"].median():.2f}, '
          f'range {base_values["ratio"].min():.2f}-{base_values["ratio"].max():.2f}, {len(base_values)} countries')
    apart = (base_values['ratio'] - 1).abs() > consts.CHECK_MAX_VALUE_RATIO_GAP
    log.flag(apart.any(), f'{base_year}: crop value V (step 05) and gross value (step 04) differ by '
             f'> {consts.CHECK_MAX_VALUE_RATIO_GAP:.0%}',
             base_values.loc[apart, ['alpha-3', 'crop_value_usd', 'gross_value_usd', 'ratio']]
             .assign(crop_value_usd=base_values['crop_value_usd'] / 1e9,
                     gross_value_usd=base_values['gross_value_usd'] / 1e9).round(2).to_string(index=False))
    missing = sorted(set(commercial.loc[commercial['Year'] == base_year, 'alpha-3'])
                     - set(own_consumption.loc[own_consumption['Year'] == base_year, 'alpha-3']))
    print(f'        countries with commercial value but no own consumption in {base_year}: {len(missing)} '
          '(expected: income groups excluded; check low and lower-middle income ones): ' + str(missing))

    print('\n== Crop provision panel (step 06)')
    totals = panel.dropna(subset=['gep_crop_total'])
    log.hard(np.allclose(totals['gep_crop_total_minus_subsistence'],
                         totals['gep_crop_total'] - totals['gep_crop_subsistence'].fillna(0)),
             'total - subsistence adds up')
    log.hard(not (totals['subsistence_share'] > 1).any(), 'subsistence share <= 1')
    base = panel[panel['Year'] == base_year]
    print(f'        {base_year}: total {base["gep_crop_total"].sum() / 1e9:.2f} bn, subsistence '
          f'{base["gep_crop_subsistence"].sum() / 1e9:.2f} bn, subsistence share (countries with both) median '
          f'{base["subsistence_share"].median():.3f}')
    orphan = panel[panel['gep_crop_total'].isna() & panel['gep_crop_subsistence'].notna()]
    log.flag(len(orphan) > 0, 'panel rows with subsistence but no total (total - subsistence is empty there)',
             orphan.groupby('Year')['alpha-3'].apply(first_codes).to_dict())


def run_checks(tables):
    """Run the checks whose tables are available.

    Args:
        tables: Dict of the tables returned by the steps, by key.

    Returns:
        Tuple (number of hard failures, number of flags).
    """
    log = CheckLog()
    own_keys = ['own_share_observed', 'own_share_panel', 'own_consumption_panel', 'smallholder_share_candidates']
    crop_keys = ['subsistence', 'commercial_by_country', 'crop_provision_panel', 'commercial_by_crop',
                 'own_consumption_panel']
    if all(key in tables for key in own_keys):
        check_own_consumption(log, *[tables[key] for key in own_keys])
    if all(key in tables for key in crop_keys):
        check_crop_provision(log, *[tables[key] for key in crop_keys])
    print(f'\n{len(log.failures)} hard failures, {len(log.flags)} flags.')
    return len(log.failures), len(log.flags)
