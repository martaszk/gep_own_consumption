"""Step 01: own-consumption share o from the RuLIS surveys.

One row per RuLIS survey (country x year) with the own-consumption share of farms below ``consts.SMALL_FARM_HA``
and the land of farms below that size in the surveyed households (used by step 02).

Sources (both FAO RuLIS, Rural Livelihoods Information System):

- ``Rural_Livelihoods_Indicators_E_All_Data_Normalized.csv``: FAOSTAT bulk download, read first.
- ``FAO_data2.csv``: an earlier extract; it fills the survey x group x variable cells the FAOSTAT file lacks.

Groups: N national, R rural, U urban, SF small-scale food producers, NSF the other farm households. RuLIS
small-scale food producers are defined relative to each country (bottom 40% of land, livestock and revenue,
SDG 2.3), not by farm size. To match Lowder and Ricciardi, the share of each group's land on farms below the
cut-off is estimated from the group's mean and standard deviation of cultivated area, assuming lognormal farm
sizes within the group::

    land_g    = households_g x mean cultivated area_g                         (ha)
    F_g       = share of land_g on farms below the cut-off (lognormal, area-weighted)
    land_lt2  = land_SF x F_SF + land_NSF x F_NSF
    own_lt2   = (land_SF F_SF own_SF + land_NSF F_NSF own_NSF) / land_lt2

own_lt2 is land-weighted: value per ha is taken as equal in the two groups, because RuLIS value per ha is
unreliable.

Households per group: FAOSTAT gives them for SF and NSF; where one is missing it is derived from the other and
the share of small-scale producers among agricultural households. Where that share is missing too, the median
of the country's other surveys (else of all surveys) is used. own_lt2 needs only the relative land of the two
groups, so it can be computed without household counts.

own_share_pct follows ``consts.OWN_SHARE_BASIS``. A survey that lacks it takes another RuLIS share (national,
then small-scale, then the mean of rural and urban) times the country's median ratio between the two (else the
median ratio over all surveys), so a country's series stays on one basis. own_share_basis records what was used.
"""
import math

import numpy as np
import pandas as pd

import consts
from utils import attach_iso3_by_name, input_path, iso3_lookup, load_iso, load_wb_income, read_semicolon_or_comma


def read_rulis(faostat_path, old_path, lookup):
    """Read both RuLIS files as one long table.

    The FAOSTAT bulk file comes first; FAO_data2 only fills the survey x group x variable cells it lacks.

    Args:
        faostat_path: FAOSTAT RuLIS bulk file (normalized layout).
        old_path: Earlier RuLIS extract (``FAO_data2.csv``).
        lookup: Normalised country name -> ISO3, from ``utils.iso3_lookup``.

    Returns:
        DataFrame with columns Country, Year, group, var, value, sd, file and alpha-3; one row per survey, group
        and variable.
    """
    faostat = pd.read_csv(faostat_path, encoding='utf-8', low_memory=False)
    faostat = faostat[faostat['Indicator Code'].isin(consts.RULIS_CODES)
                      & faostat['Qualifier Code'].isin(consts.RULIS_GROUPS)].copy()
    faostat['Country'] = faostat['Survey'].str.rsplit(' - ', n=1).str[0].str.strip()
    faostat['Year'] = pd.to_numeric(faostat['Survey'].str.rsplit(' - ', n=1).str[1], errors='coerce')
    faostat['var'] = faostat['Indicator Code'].map(consts.RULIS_CODES)
    faostat['group'] = faostat['Qualifier Code'].map(consts.RULIS_GROUPS)
    faostat['Value'] = pd.to_numeric(faostat['Value'], errors='coerce')
    keys = ['Country', 'Year', 'group', 'var']
    values = faostat[faostat['Element'] == 'Value'][keys + ['Value']]
    sds = faostat[faostat['Element'] == 'Standard Deviation'][keys + ['Value']]
    values = values.merge(sds.rename(columns={'Value': 'sd'}), on=keys, how='left')
    parts = [values.rename(columns={'Value': 'value'}).assign(file='FAOSTAT RuLIS')]
    print('  FAOSTAT RuLIS (%s): %d surveys in %d countries.'
          % (faostat_path.name, faostat['Survey'].nunique(), faostat['Country'].nunique()))

    old = read_semicolon_or_comma(old_path)
    old = old.drop(columns=[c for c in old.columns if 'unnamed' in str(c).lower()])
    old = old[old['Disaggregation'].isin(consts.RULIS_OLD_GROUPS)].copy()
    indicator = old['Indicator'].astype(str)
    old['var'] = np.where(indicator.str.contains('own consumption'), 'own',
                          np.where(indicator.str.contains('cultivated land'), 'cultivated', None))
    old = old.dropna(subset=['var'])
    old['group'] = old['Disaggregation'].map(consts.RULIS_OLD_GROUPS)
    for column in ['Value', 'Standard Deviation']:
        old[column] = pd.to_numeric(old[column].astype(str).str.replace(',', '.'), errors='coerce')
    parts.append(old.rename(columns={'Value': 'value', 'Standard Deviation': 'sd'})
                 [['Country', 'Year', 'group', 'var', 'value', 'sd']].assign(file='FAO_data2'))

    long = pd.concat(parts, ignore_index=True).dropna(subset=['value', 'Year'])
    long['Year'] = long['Year'].astype(int)
    long = attach_iso3_by_name(long, 'Country', lookup, 'RuLIS')
    return long.drop_duplicates(['alpha-3', 'Year', 'group', 'var'], keep='first')


def group_column(table, var, group):
    """Return column (var, group) of a pivoted RuLIS table, or an empty column if no survey has it.

    Args:
        table: RuLIS table pivoted to columns (var, group).
        var: Variable name, e.g. 'own'.
        group: RuLIS group code, e.g. 'SF'.

    Returns:
        Series on the index of ``table``.
    """
    if (var, group) in table.columns:
        return table[(var, group)]
    return pd.Series(np.nan, index=table.index)


def survey_table(long):
    """Arrange the RuLIS terms the method uses as one row per survey.

    Args:
        long: Long RuLIS table from ``read_rulis``.

    Returns:
        DataFrame indexed by alpha-3 and Year with Country, own_<group> (own-consumption share, %) for N, R, U,
        SF and NSF, cultivated_mean_<group>, cultivated_sd_<group> (ha) and households_<group> for SF and NSF, and
        ssfp_share_pct (small-scale producers, % of agricultural households). A mean cultivated area of 0 means
        "not reported" and becomes NaN.
    """
    values = long.pivot_table(index=['alpha-3', 'Year'], columns=['var', 'group'], values='value', aggfunc='first')
    sds = long.pivot_table(index=['alpha-3', 'Year'], columns=['var', 'group'], values='sd', aggfunc='first')
    surveys = pd.DataFrame(index=values.index)
    surveys['Country'] = long.groupby(['alpha-3', 'Year'])['Country'].first()
    for group in ['N', 'R', 'U', 'SF', 'NSF']:
        surveys['own_%s' % group] = group_column(values, 'own', group)
    for group in ['SF', 'NSF']:
        surveys['cultivated_mean_%s' % group] = group_column(values, 'cultivated', group).replace(0, np.nan)
        surveys['cultivated_sd_%s' % group] = group_column(sds, 'cultivated', group)
        surveys['households_%s' % group] = group_column(values, 'hh', group)
    surveys['ssfp_share_pct'] = group_column(values, 'ssfp_share', 'N')
    return surveys


def fill_small_scale_share(surveys):
    """Fill the share of small-scale producers among agricultural households where a survey lacks it.

    The median of the country's other surveys is used, else the median of all surveys.

    Args:
        surveys: Survey table from ``survey_table``.

    Returns:
        Copy of ``surveys`` with ssfp_share_pct filled and the column ssfp_share_source ('reported',
        "median of the country's other surveys", 'median of all surveys').
    """
    surveys = surveys.copy()
    surveys['ssfp_share_source'] = np.where(surveys['ssfp_share_pct'].notna(), 'reported', None)
    country_median = surveys.groupby(level='alpha-3')['ssfp_share_pct'].transform('median')
    fill = surveys['ssfp_share_pct'].isna() & country_median.notna()
    surveys.loc[fill, 'ssfp_share_pct'] = country_median[fill]
    surveys.loc[fill, 'ssfp_share_source'] = "median of the country's other surveys"
    fill = surveys['ssfp_share_pct'].isna()
    surveys.loc[fill, 'ssfp_share_pct'] = surveys['ssfp_share_pct'].median()
    surveys.loc[fill, 'ssfp_share_source'] = 'median of all surveys'
    return surveys


def derive_households(surveys, share_limits):
    """Derive the households of one farm group from the other where only one is reported.

    With p the small-scale share of agricultural households: SF = NSF x p / (1 - p) and NSF = SF x (1 - p) / p.

    Args:
        surveys: Survey table with households_SF, households_NSF and a filled ssfp_share_pct (%).
        share_limits: (lowest, highest) small-scale share, as a fraction, for which a group is derived.

    Returns:
        Copy of ``surveys`` with the households filled and the column households_source.
    """
    surveys = surveys.copy()
    share = surveys['ssfp_share_pct'] / 100.0
    usable = share.between(*share_limits)
    surveys['households_source'] = np.where(surveys['households_SF'].notna() & surveys['households_NSF'].notna(),
                                            'reported', None)
    derive_sf = surveys['households_SF'].isna() & surveys['households_NSF'].notna() & usable
    derive_nsf = surveys['households_NSF'].isna() & surveys['households_SF'].notna() & usable
    surveys.loc[derive_sf, 'households_SF'] = surveys.loc[derive_sf, 'households_NSF'] * share / (1 - share)
    surveys.loc[derive_nsf, 'households_NSF'] = surveys.loc[derive_nsf, 'households_SF'] * (1 - share) / share
    surveys.loc[derive_sf | derive_nsf, 'households_source'] = 'one group derived from small-scale share'
    return surveys


def share_of_land_below(mean, sd, cut):
    """Return the share of a group's land on farms below a size cut-off, for lognormal farm sizes.

    The share is area-weighted: it is the first-moment distribution of the lognormal at the cut-off.

    Args:
        mean: Mean cultivated area per household of the group (ha).
        sd: Standard deviation of the cultivated area (ha).
        cut: Farm-size cut-off (ha).

    Returns:
        Share between 0 and 1. NaN if the mean is missing or not positive. Without a usable standard deviation,
        1.0 if the mean is below the cut-off, else 0.0.
    """
    if not (np.isfinite(mean) and mean > 0):
        return np.nan
    if not (np.isfinite(sd) and sd > 0):
        return 1.0 if mean < cut else 0.0
    sigma2 = math.log(1.0 + (sd / mean) ** 2)
    sigma = math.sqrt(sigma2)
    mu = math.log(mean) - sigma2 / 2.0
    z = (math.log(cut) - mu - sigma2) / sigma
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def land_below_cutoff(surveys, cut, share_limits):
    """Compute the land on farms below the cut-off and the own-consumption share of those farms.

    The groups' own-consumption shares are weighted by their land below the cut-off. The weights need only the
    relative land of the groups, so without household counts they come from the small-scale share.

    Args:
        surveys: Survey table after ``derive_households``.
        cut: Farm-size cut-off (ha).
        share_limits: (lowest, highest) small-scale share, as a fraction, usable as relative weight.

    Returns:
        Copy of ``surveys`` with land_<group>_ha, F_lt2_<group>, household_land_ha, land_lt2_ha,
        lt2_share_of_household_land_pct and own_lt2 (%).
    """
    surveys = surveys.copy()
    for group in ['SF', 'NSF']:
        surveys['land_%s_ha' % group] = surveys['households_%s' % group] * surveys['cultivated_mean_%s' % group]
        surveys['F_lt2_%s' % group] = [share_of_land_below(mean, sd, cut) for mean, sd in
                                       zip(surveys['cultivated_mean_%s' % group], surveys['cultivated_sd_%s' % group])]
    surveys['household_land_ha'] = surveys['land_SF_ha'] + surveys['land_NSF_ha']
    surveys['land_lt2_ha'] = surveys['land_SF_ha'] * surveys['F_lt2_SF'] + surveys['land_NSF_ha'] * surveys['F_lt2_NSF']
    surveys['lt2_share_of_household_land_pct'] = 100 * surveys['land_lt2_ha'] / surveys['household_land_ha']

    share = surveys['ssfp_share_pct'] / 100.0
    weight_sf = surveys['land_SF_ha'] * surveys['F_lt2_SF']
    weight_nsf = surveys['land_NSF_ha'] * surveys['F_lt2_NSF']
    relative = surveys['households_SF'].isna() & share.between(*share_limits)
    weight_sf = weight_sf.where(~relative, share * surveys['cultivated_mean_SF'] * surveys['F_lt2_SF'])
    weight_nsf = weight_nsf.where(~relative, (1 - share) * surveys['cultivated_mean_NSF'] * surveys['F_lt2_NSF'])
    surveys['own_lt2'] = ((weight_sf * surveys['own_SF'] + weight_nsf * surveys['own_NSF'])
                          / (weight_sf + weight_nsf))
    return surveys


def select_own_share(surveys, basis, cut):
    """Choose the own-consumption share of each survey on one basis, bridging surveys that lack it.

    A survey without the chosen share takes another RuLIS share times the ratio between the two: the median
    over the country's surveys that have both, else over all surveys. For the basis 'lt2ha' the national share
    bridges first, because its ratio to own_lt2 has the narrowest spread.

    Args:
        surveys: Survey table after ``land_below_cutoff``.
        basis: 'lt2ha', 'small_scale' or 'national' (``consts.OWN_SHARE_BASIS``).
        cut: Farm-size cut-off (ha), for the label of the 'lt2ha' basis.

    Returns:
        Copy of ``surveys`` with own_RU (mean of rural and urban), own_share_pct (%, at most 100) and
        own_share_basis.
    """
    columns_by_basis = {'lt2ha': ('own_lt2', ['own_N', 'own_SF', 'own_RU']),
                        'small_scale': ('own_SF', ['own_N', 'own_RU']),
                        'national': ('own_N', ['own_RU'])}
    surveys = surveys.copy()
    surveys['own_RU'] = surveys[['own_R', 'own_U']].mean(axis=1, skipna=False)
    target, fallbacks = columns_by_basis[basis]
    label = {'own_lt2': 'farms < %g ha' % cut, 'own_SF': 'small-scale food producers',
             'own_N': 'national', 'own_RU': 'mean of rural and urban'}
    surveys['own_share_pct'] = surveys[target]
    surveys['own_share_basis'] = np.where(surveys[target].notna(), label[target], None)
    ratios = []
    for column in fallbacks:
        ratio = surveys[target] / surveys[column]
        ratio_country = ratio.groupby(level='alpha-3').transform('median')
        ratio_global = ratio.median()
        ratios.append((label[column], round(float(ratio_global), 3), int(ratio.notna().sum())))
        take = surveys['own_share_pct'].isna() & surveys[column].notna()
        use_country = take & ratio_country.notna()
        surveys.loc[use_country, 'own_share_pct'] = surveys.loc[use_country, column] * ratio_country[use_country]
        surveys.loc[use_country, 'own_share_basis'] = label[target] + ' (from ' + label[column] + ' x country ratio)'
        use_global = take & ratio_country.isna() & np.isfinite(ratio_global)
        surveys.loc[use_global, 'own_share_pct'] = surveys.loc[use_global, column] * ratio_global
        surveys.loc[use_global, 'own_share_basis'] = label[target] + ' (from ' + label[column] + ' x global ratio)'
    surveys['own_share_pct'] = surveys['own_share_pct'].clip(upper=100)
    print('    ratios used to bridge to the %s basis: %s' % (label[target], ratios))
    return surveys


def run():
    """Build the RuLIS survey table and the observed own-consumption shares.

    Returns:
        Dict with ``rulis_surveys`` (one row per survey with all terms) and ``own_share_observed`` (alpha-3,
        Country, Year, own_share_pct, own_share_basis; the surveys that have a share).
    """
    lookup = iso3_lookup(load_iso(input_path('iso')), load_wb_income(input_path('wb_income')), consts.ISO3_ALIASES)
    long = read_rulis(input_path('rulis_faostat'), input_path('rulis_old'), lookup)
    print('01: RuLIS merged: %d surveys in %d countries (cells by file: %s).'
          % (long[['alpha-3', 'Year']].drop_duplicates().shape[0], long['alpha-3'].nunique(),
             long['file'].value_counts().to_dict()))

    surveys = survey_table(long)
    surveys = fill_small_scale_share(surveys)
    surveys = derive_households(surveys, consts.SMALL_SCALE_SHARE_LIMITS)
    surveys = land_below_cutoff(surveys, consts.SMALL_FARM_HA, consts.SMALL_SCALE_SHARE_LIMITS)
    surveys = select_own_share(surveys, consts.OWN_SHARE_BASIS, consts.SMALL_FARM_HA).reset_index()
    observed = surveys.dropna(subset=['own_share_pct'])[['alpha-3', 'Country', 'Year', 'own_share_pct',
                                                         'own_share_basis']]

    print('01: %d surveys with an own-consumption share (%d countries); basis: %s'
          % (len(observed), observed['alpha-3'].nunique(), observed['own_share_basis'].value_counts().to_dict()))
    print('    %d surveys with land on farms < %g ha (used by step 02); households: %s'
          % (surveys['land_lt2_ha'].notna().sum(), consts.SMALL_FARM_HA,
             surveys['households_source'].value_counts().to_dict()))
    both = surveys.dropna(subset=['own_lt2', 'own_N'])
    if len(both):
        print('    own share, farms < %g ha minus national: median %+.1f points (%d surveys)'
              % (consts.SMALL_FARM_HA, (both['own_lt2'] - both['own_N']).median(), len(both)))
    return {'rulis_surveys': surveys, 'own_share_observed': observed}

