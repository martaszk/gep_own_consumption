"""Step 06: subsistence GEP and the crop provision panel.

GEP_subsistence = own consumption (own_con2, step 05) x CWON 2024 land rental rate: nature's contribution is the
land rent share of the value of production. Rental rates and the deflator are the ones of the commercial step
(``utils.attach_rental_rates``, ``utils.deflate``), so both parts of crop provision use the same ones: CWON 2024
annual country x year rates (1995-2020; later years hold the last rate), and values restated in base-year USD
(``consts.DEFLATOR``).

Crop provision panel: FAO production includes what households eat themselves, so the commercial value of step 04
is a total. The panel reports the total, the subsistence part and total - subsistence per country and year.
"""
import pandas as pd

import consts
from utils import attach_rental_rates, deflate, input_path, load_cpi, load_iso, load_rental_rates


def subsistence_gep(own_consumption_panel, rental_rates):
    """Compute the subsistence GEP of every country and year.

    Args:
        own_consumption_panel: Panel of step 05 (Country, Year, alpha-3, own_con, own_con2).
        rental_rates: Rental rates from ``utils.load_rental_rates``.

    Returns:
        DataFrame with Country, Year, alpha-3, own_con, own_con2, rental_rate, rental_rate_source and gep_value
        (current USD).
    """
    columns = ['Country', 'Year', 'alpha-3', 'own_con', 'own_con2', 'rental_rate', 'rental_rate_source', 'gep_value']
    subsistence = attach_rental_rates(own_consumption_panel, rental_rates)
    subsistence['gep_value'] = subsistence['own_con2'] * subsistence['rental_rate']
    return subsistence[columns]


def crop_provision_panel(commercial_by_country, subsistence, cpi, countries, deflator, base_year):
    """Put commercial (total) and subsistence crop provision side by side per country and year.

    Args:
        commercial_by_country: Country-year table of step 04 (alpha-3, Year, gross_value_usd, gep_value).
        subsistence: Subsistence GEP from ``subsistence_gep``.
        cpi: CPI index from ``utils.load_cpi``.
        countries: ISO table from ``utils.load_iso`` (alpha-3, name).
        deflator: ``consts.DEFLATOR``.
        base_year: ``consts.BASE_YEAR``.

    Returns:
        DataFrame sorted by alpha-3 and Year with gross_value_total, gep_crop_total, own_con2, gep_crop_subsistence,
        gep_crop_total_minus_subsistence (a missing subsistence counts as 0), subsistence_share, CPI_<base_year>,
        the three GEP columns in base-year USD and Country.
    """
    panel = commercial_by_country[['alpha-3', 'Year', 'gross_value_usd', 'gep_value']].rename(
        columns={'gross_value_usd': 'gross_value_total', 'gep_value': 'gep_crop_total'})
    panel = panel.merge(subsistence[['alpha-3', 'Year', 'own_con2', 'gep_value']].rename(
        columns={'gep_value': 'gep_crop_subsistence'}), on=['alpha-3', 'Year'], how='outer')
    for column in ['own_con2', 'gep_crop_subsistence']:
        panel[column] = pd.to_numeric(panel[column], errors='coerce')
    panel['gep_crop_total_minus_subsistence'] = panel['gep_crop_total'] - panel['gep_crop_subsistence'].fillna(0)
    panel['subsistence_share'] = panel['gep_crop_subsistence'] / panel['gep_crop_total']
    panel = deflate(panel, ['gep_crop_total', 'gep_crop_subsistence', 'gep_crop_total_minus_subsistence'], cpi,
                    deflator, base_year)
    panel = panel.drop(columns=['CPI'])
    panel = panel.merge(countries[['alpha-3', 'name']].rename(columns={'name': 'Country'}), on='alpha-3', how='left')
    return panel.sort_values(['alpha-3', 'Year'])


def run(own_consumption_panel, commercial_by_country):
    """Compute the subsistence GEP and the crop provision panel.

    Args:
        own_consumption_panel: Panel of step 05.
        commercial_by_country: Country-year table of step 04.

    Returns:
        Dict with ``subsistence`` (subsistence GEP in current USD with CPI, CPI_<base year> and
        gep_value_<base year>) and ``crop_provision_panel``.
    """
    base_year = consts.BASE_YEAR
    subsistence = subsistence_gep(own_consumption_panel, load_rental_rates(input_path('rental_rates')))
    cpi = load_cpi(input_path('cpi'), base_year)
    base = subsistence[subsistence['Year'] == base_year]
    print('Subsistence GEP %d: %.2f bn USD, %d countries.'
          % (base_year, base['gep_value'].sum() / 1e9, base.loc[base['gep_value'].notna(), 'alpha-3'].nunique()))

    panel = crop_provision_panel(commercial_by_country, subsistence, cpi, load_iso(input_path('iso')),
                                 consts.DEFLATOR, base_year)
    base = panel[panel['Year'] == base_year]
    print('Panel %d: total %.2f bn, subsistence %.2f bn, total - subsistence %.2f bn USD; '
          'subsistence above total in %d countries.'
          % (base_year, base['gep_crop_total'].sum() / 1e9, base['gep_crop_subsistence'].sum() / 1e9,
             base['gep_crop_total_minus_subsistence'].sum() / 1e9, int((base['subsistence_share'] > 1).sum())))
    return {'subsistence': deflate(subsistence, ['gep_value'], cpi, consts.DEFLATOR, base_year),
            'crop_provision_panel': panel}

