"""Step 03: yearly values of the survey-based shares, ``consts.OC_FIRST_YEAR`` to ``consts.OC_LAST_YEAR``.

- o, the own-consumption share of small farms (step 01), for every country RuLIS surveyed;
- a, the smallholder share, for countries whose share comes from RuLIS (step 02), when
  ``consts.A_TIME_VARYING`` is set, so it moves between surveys instead of staying at one survey's value.

Shares are filled, not values: step 05 multiplies them by each year's crop production value.

``consts.TIME_PATH``:

- 'interpolate': survey years keep their value; years between two surveys are interpolated linearly; years
  before the first and after the last survey hold the nearest survey's value.
- 'linear_fit': a straight line through all of a country's surveys (smooths noisy series such as Nigeria
  2013-2019), held at the line's value of the first and last survey year outside the survey years. A country
  with one survey holds it for all years.

``consts.MAX_SURVEY_AGE``: years further than this from every survey are left empty (step 05 gives them the
regional median); None keeps the nearest survey's value for every year.

The same rule gives every year, so the base-year value used for GEP is the base-year point of the trend panel.
"""
import numpy as np
import pandas as pd

import consts


def yearly_path(survey_years, survey_values, years, time_path, max_age):
    """Return one country's yearly values and their labels from its survey values.

    Args:
        survey_years: Years of the surveys.
        survey_values: Share (%) of each survey; several values in one year are averaged.
        years: Array of the panel years.
        time_path: 'interpolate' or 'linear_fit' (``consts.TIME_PATH``).
        max_age: Years from the nearest survey beyond which a year is left empty, or None.

    Returns:
        Tuple of arrays, one value per panel year: share (%, 0-100, NaN beyond ``max_age``), source label,
        nearest survey year, years to the nearest survey.

    Raises:
        ValueError: Unknown ``time_path``.
    """
    order = np.argsort(survey_years)
    observed_years = np.asarray(survey_years, dtype=float)[order]
    observed_values = np.asarray(survey_values, dtype=float)[order]
    unique_years = np.unique(observed_years)
    observed_values = np.array([observed_values[observed_years == year].mean() for year in unique_years])
    observed_years = unique_years
    first, last = observed_years.min(), observed_years.max()
    inside = (years > first) & (years < last)
    if time_path == 'linear_fit' and len(observed_years) >= 2:
        slope, intercept = np.polyfit(observed_years, observed_values, 1)
        values = intercept + slope * np.clip(years, first, last)
        sources = np.where(np.isin(years, observed_years), 'survey year (fitted line)',
                           np.where(inside, 'fitted line', 'held (fitted line at nearest survey)'))
    elif time_path in ('interpolate', 'linear_fit'):
        values = np.interp(years, observed_years, observed_values)        # holds the end values outside
        sources = np.where(np.isin(years, observed_years), 'observed',
                           np.where(inside, 'interpolated between surveys', 'held from nearest survey'))
    else:
        raise ValueError("TIME_PATH must be 'interpolate' or 'linear_fit'")
    distance = np.min(np.abs(years[:, None] - observed_years[None, :]), axis=1)
    nearest = observed_years[np.argmin(np.abs(years[:, None] - observed_years[None, :]), axis=1)]
    values = np.clip(values, 0, 100)
    if max_age is not None:
        far = distance > max_age
        values = np.where(far, np.nan, values)
        sources = np.where(far, 'more than %d years from a survey' % max_age, sources)
    return values, sources, nearest.astype(int), distance.astype(int)


def panel(table, value_column, out_column, source_column, years, time_path, max_age):
    """Build the yearly path of a share for every country in a survey table.

    Args:
        table: Survey table with alpha-3, Year and ``value_column``.
        value_column: Column with the survey share (%).
        out_column: Name of the yearly share column.
        source_column: Name of the column with the source label of each year.
        years: Array of the panel years.
        time_path: 'interpolate' or 'linear_fit'.
        max_age: Years from the nearest survey beyond which a year is left empty, or None.

    Returns:
        DataFrame with alpha-3, Year, ``out_column``, ``source_column``, nearest_survey_year and
        years_to_nearest_survey; one row per country and panel year.
    """
    parts = []
    for code, surveys in table.dropna(subset=[value_column]).groupby('alpha-3'):
        values, sources, nearest, distance = yearly_path(surveys['Year'].to_numpy(), surveys[value_column].to_numpy(),
                                                         years, time_path, max_age)
        parts.append(pd.DataFrame({'alpha-3': code, 'Year': years, out_column: values, source_column: sources,
                                   'nearest_survey_year': nearest, 'years_to_nearest_survey': distance}))
    return pd.concat(parts, ignore_index=True)


def most_common(values):
    """Return the most frequent value of a Series (the first one on ties).

    Args:
        values: Series.

    Returns:
        The most frequent value.
    """
    return values.value_counts().index[0]


def run(own_share_observed, smallholder_share, smallholder_share_rulis_surveys):
    """Build the yearly own-consumption share of surveyed countries and the yearly smallholder share of RuLIS countries.

    Args:
        own_share_observed: Observed shares of step 01 (alpha-3, Year, own_share_pct, own_share_basis).
        smallholder_share: Smallholder share of step 02 (alpha-3, a_source).
        smallholder_share_rulis_surveys: Smallholder share per RuLIS survey of step 02 (alpha-3, Year, a_pct).

    Returns:
        Dict with ``own_share_panel`` (alpha-3, Year, own_share_pct, share_source, nearest_survey_year,
        years_to_nearest_survey, own_share_basis) and ``smallholder_share_panel`` (alpha-3, Year, a_pct,
        a_path_source, nearest_survey_year, years_to_nearest_survey; empty without ``consts.A_TIME_VARYING``).
    """
    years = np.arange(consts.OC_FIRST_YEAR, consts.OC_LAST_YEAR + 1)
    own = panel(own_share_observed, 'own_share_pct', 'own_share_pct', 'share_source', years, consts.TIME_PATH,
                consts.MAX_SURVEY_AGE)
    own['own_share_basis'] = own['alpha-3'].map(own_share_observed.groupby('alpha-3')['own_share_basis']
                                                .agg(most_common))
    print('03: own-consumption share, %d surveyed countries, %d-%d (TIME_PATH = %s): %s'
          % (own['alpha-3'].nunique(), consts.OC_FIRST_YEAR, consts.OC_LAST_YEAR, consts.TIME_PATH,
             own['share_source'].value_counts().to_dict()))

    rulis_countries = smallholder_share.loc[smallholder_share['a_source'] == 'rulis', 'alpha-3']
    columns = ['alpha-3', 'Year', 'a_pct', 'a_path_source', 'nearest_survey_year', 'years_to_nearest_survey']
    if consts.A_TIME_VARYING and len(rulis_countries):
        surveys = smallholder_share_rulis_surveys[smallholder_share_rulis_surveys['alpha-3'].isin(rulis_countries)]
        smallholder = panel(surveys, 'a_pct', 'a_pct', 'a_path_source', years, consts.TIME_PATH,
                            consts.MAX_SURVEY_AGE)
        smallholder['a_path_source'] = 'RuLIS ' + smallholder['a_path_source']
        surveys_per_country = surveys.groupby('alpha-3')['Year'].nunique()
        print('03: smallholder share over time for %d RuLIS countries (%d with 2+ surveys)'
              % (smallholder['alpha-3'].nunique(), (surveys_per_country >= 2).sum()))
    else:
        smallholder = pd.DataFrame(columns=columns)
        print('03: smallholder share held constant (A_TIME_VARYING = %s)' % consts.A_TIME_VARYING)
    return {'own_share_panel': own, 'smallholder_share_panel': smallholder[columns]}

