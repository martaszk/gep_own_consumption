"""Helpers used by more than one step of the pipeline: input paths, file readers, country matching, rental rates
and the CPI deflator.
"""
import csv
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

import consts


def input_path(key):
    """Return the path of an input file.

    Args:
        key: Key of the file in ``consts.INPUTS``.

    Returns:
        ``Path`` of the file in ``consts.INPUT_DIR``.
    """
    return Path(consts.INPUT_DIR) / consts.INPUTS[key]


def read_semicolon_or_comma(path, **kwargs):
    """Read a CSV file separated by ';' or ',' (whichever the header uses more), in UTF-8 or Latin-1.

    Args:
        path: CSV file.
        **kwargs: Passed on to ``pandas.read_csv``.

    Returns:
        DataFrame.
    """
    with open(path, encoding='utf-8-sig') as handle:
        header = handle.readline()
    sep = ';' if header.count(';') > header.count(',') else ','
    try:
        return pd.read_csv(path, sep=sep, encoding='utf-8-sig', **kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(path, sep=sep, encoding='latin-1', **kwargs)


def read_fao_csv(path, **kwargs):
    """Read a FAOSTAT bulk CSV file, which has shipped both in UTF-8 and in Latin-1.

    Args:
        path: CSV file.
        **kwargs: Passed on to ``pandas.read_csv``.

    Returns:
        DataFrame.
    """
    try:
        return pd.read_csv(path, encoding='utf-8', **kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding='latin-1', **kwargs)


def normalize_name(name):
    """Normalise a country name for matching: ASCII, lower case, '&' as 'and', other symbols as single spaces.

    Args:
        name: Country name (missing values allowed).

    Returns:
        Normalised name; '' for a missing value.
    """
    if pd.isna(name):
        return ''
    text = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode('ascii')
    text = text.lower().strip().replace('&', ' and ')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', text)).strip()


def load_iso(path):
    """Read the ISO 3166 country table.

    Rows are read one by one and anchored on their "ISO 3166-2:XX" field, so the file reads with ',' or ';' as
    separator and with names whose commas a spreadsheet turned into separators ("Iran; Islamic Republic of"),
    which would otherwise shift every later column.

    Args:
        path: The ISO table (columns name, alpha-2, alpha-3, country-code, iso_3166-2, region, sub-region,
            intermediate-region, ...).

    Returns:
        DataFrame with columns ``name``, ``alpha-3``, ``m49`` (numeric, NaN if unreadable), ``region``,
        ``sub-region`` and ``intermediate-region`` ('' where the table has no value).
    """
    with open(path, encoding='utf-8-sig', newline='') as handle:
        lines = handle.read().splitlines()
    delimiter = ';' if lines[0].count(';') > lines[0].count(',') else ','
    rows = []
    for fields in csv.reader(lines[1:], delimiter=delimiter):
        anchor = next((i for i, value in enumerate(fields) if value.strip().startswith('ISO 3166-2:')), None)
        if anchor is None or anchor < 4:
            continue
        after = [value.strip() for value in fields[anchor + 1:]] + ['', '', '']
        rows.append({'name': ', '.join(value.strip() for value in fields[:anchor - 3] if value.strip()),
                     'alpha-3': fields[anchor - 2].strip(),
                     'm49': pd.to_numeric(fields[anchor - 1].strip(), errors='coerce'),
                     'region': after[0],
                     'sub-region': after[1],
                     'intermediate-region': after[2]})
    return pd.DataFrame(rows)


def load_wb_income(path):
    """Read the World Bank country table: names and regions.

    The income groups of this file (one classification, FY25) are not used; step 05 takes the groups from the World
    Bank historical classification.

    Args:
        path: ``WBincomegroup.csv`` (columns Country, Code, Region, ...).

    Returns:
        DataFrame with columns ``alpha-3``, ``wb_name`` and ``Region``; rows without a code are dropped.
    """
    table = read_semicolon_or_comma(path)
    table = table.rename(columns={'Code': 'alpha-3', 'Country': 'wb_name'})
    return table[['alpha-3', 'wb_name', 'Region']].dropna(subset=['alpha-3'])


def iso3_lookup(iso, wb_income, aliases):
    """Build the lookup from normalised country name to ISO3 code.

    Names of the ISO table come first, World Bank names fill names the ISO table lacks, and the aliases override
    both.

    Args:
        iso: ISO table from ``load_iso``.
        wb_income: World Bank table from ``load_wb_income``.
        aliases: Dict of normalised name -> ISO3 code for names neither table resolves.

    Returns:
        Dict of normalised name -> ISO3 code.
    """
    lookup = {normalize_name(name): code for name, code in zip(iso['name'], iso['alpha-3'])}
    for name, code in zip(wb_income['wb_name'], wb_income['alpha-3']):
        lookup.setdefault(normalize_name(name), code)
    lookup.update(aliases)
    return lookup


def codes_for_names(names, lookup):
    """Return the ISO3 code of each country name, normalising every distinct name once.

    Args:
        names: Series of country names.
        lookup: Dict of normalised name -> ISO3 code from ``iso3_lookup``.

    Returns:
        Series of ISO3 codes on the index of ``names``; missing where a name has no code.
    """
    codes = {name: lookup.get(normalize_name(name)) for name in pd.unique(names)}
    return names.map(codes)


def attach_iso3_by_name(table, column, lookup, label):
    """Add the ISO3 code of each row from a column of country names; rows whose name has no code are dropped.

    Args:
        table: DataFrame with a column of country names.
        column: Name of that column.
        lookup: Dict of normalised name -> ISO3 code from ``iso3_lookup``.
        label: Name of the source, used in the printed list of names without a code.

    Returns:
        Copy of ``table`` with a column ``alpha-3``, without the rows whose name did not match.
    """
    table = table.copy()
    table['alpha-3'] = codes_for_names(table[column], lookup)
    missing = sorted(table.loc[table['alpha-3'].isna(), column].dropna().astype(str).unique())
    if missing:
        print('  %s: %d names without ISO3 (dropped; regional aggregates are expected here): %s%s'
              % (label, len(missing), missing[:40], ' ...' if len(missing) > 40 else ''))
    return table.dropna(subset=['alpha-3'])


def load_rental_rates(path):
    """Read the CWON 2024 cropland rental rates as one row per country and year.

    Args:
        path: ``land_ef_regional_cropland_rental_rates_new.csv`` (columns wb_code, yr1995 ... yr2020).

    Returns:
        DataFrame with columns ``alpha-3``, ``Year`` and ``rental_rate`` (share of the value of production);
        country-years without a rate are dropped.

    Raises:
        ValueError: The table lists a country twice.
    """
    rates = pd.read_csv(path, encoding='latin-1')
    if rates['wb_code'].duplicated().any():
        raise ValueError('The CWON rental-rate table lists a country twice.')
    year_columns = [c for c in rates.columns if re.fullmatch(r'yr\d{4}', c)]
    rates = rates.melt(id_vars=['wb_code'], value_vars=year_columns, var_name='Year', value_name='rental_rate')
    rates['Year'] = rates['Year'].str[2:].astype(int)
    return rates.rename(columns={'wb_code': 'alpha-3'}).dropna(subset=['rental_rate'])


def attach_rental_rates(table, rates):
    """Add each country-year's CWON rental rate.

    After the last year of the rate table the country's last rate is held; before its first year there is no rate.

    Args:
        table: DataFrame with columns ``alpha-3`` and ``Year``.
        rates: Rental rates from ``load_rental_rates``.

    Returns:
        Copy of ``table`` with the columns ``rental_rate`` and ``rental_rate_source`` ('CWON2024 annual',
        'CWON2024 <last year> held' or empty).
    """
    first, last = rates['Year'].min(), rates['Year'].max()
    table = table.copy()
    table['rate_year'] = table['Year'].clip(upper=last)
    table = table.merge(rates.rename(columns={'Year': 'rate_year'}), on=['alpha-3', 'rate_year'], how='left')
    table.loc[table['Year'] < first, 'rental_rate'] = np.nan
    table['rental_rate_source'] = np.where(table['rental_rate'].isna(), None,
                                           np.where(table['Year'] > last, 'CWON2024 %d held' % last,
                                                    'CWON2024 annual'))
    return table.drop(columns='rate_year')


def load_cpi(path, base_year):
    """Build a CPI index per country (base year = 100) from World Bank annual inflation rates.

    The index is chained forwards and backwards from the base year. A missing inflation rate counts as 0%.
    Countries without the base year, or with fewer than two years, get no index.

    Args:
        path: ``CPI_WB.csv`` (World Bank FP.CPI.TOTL.ZG, ';' separated, one column per year).
        base_year: Year in which the index is 100.

    Returns:
        DataFrame with columns ``alpha-3``, ``Year`` and ``CPI``.
    """
    raw = pd.read_csv(path, delimiter=';', encoding='utf-8-sig')
    meta = ['Series Name', 'Series Code', 'Country Name', 'Country Code']
    long = raw.melt(id_vars=meta, var_name='Year', value_name='Inflation_Rate')
    long['Year'] = pd.to_numeric(long['Year'].astype(str).str.extract(r'(\d{4})')[0], errors='coerce')
    long = long.dropna(subset=['Year'])
    long['Year'] = long['Year'].astype(int)
    long['Inflation_Rate'] = pd.to_numeric(long['Inflation_Rate'], errors='coerce').fillna(0)
    parts = []
    for _, country in long.groupby('Country Code'):
        country = country.sort_values('Year').reset_index(drop=True)
        if len(country) < 2 or base_year not in set(country['Year']):
            continue
        base = int(np.flatnonzero(country['Year'].to_numpy() == base_year)[0])
        factor = 1 + country['Inflation_Rate'].to_numpy(dtype=float) / 100
        index = np.empty(len(country))
        # chained year by year from the base year: forwards x (1 + rate), backwards / (1 + rate of the later year)
        index[base:] = np.multiply.accumulate(np.concatenate(([100.0], factor[base + 1:])))
        index[:base + 1] = np.divide.accumulate(np.concatenate(([100.0], factor[base:0:-1])))[::-1]
        country['CPI'] = index
        parts.append(country)
    return pd.concat(parts)[['Country Code', 'Year', 'CPI']].rename(columns={'Country Code': 'alpha-3'})


def deflate(table, columns, cpi, deflator, base_year):
    """Restate current-USD columns in base-year USD.

    Args:
        table: DataFrame with columns ``Year`` (and ``alpha-3`` for ``'country_cpi'``) and the value columns.
        columns: Value columns to restate.
        cpi: CPI index from ``load_cpi``.
        deflator: ``'us_cpi'`` (US CPI for every country) or ``'country_cpi'`` (each country's own CPI).
        base_year: Base year of the CPI index.

    Returns:
        ``table`` with the columns ``CPI``, ``CPI_<base_year>`` (100) and ``<column>_<base_year>`` for each
        value column.

    Raises:
        ValueError: Unknown ``deflator``.
    """
    if deflator == 'us_cpi':
        us = cpi[cpi['alpha-3'] == 'USA'][['Year', 'CPI']]
        table = table.merge(us, on='Year', how='left')
    elif deflator == 'country_cpi':
        table = table.merge(cpi, on=['alpha-3', 'Year'], how='left')
    else:
        raise ValueError("DEFLATOR must be 'us_cpi' or 'country_cpi'")
    table['CPI_%d' % base_year] = 100.0
    for column in columns:
        table['%s_%d' % (column, base_year)] = table[column] * 100.0 / table['CPI']
    return table
