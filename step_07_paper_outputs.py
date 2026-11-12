"""Step 07: tables, figure and map of the subsistence GEP for the paper; coverage statistics on the console.

All of them come from the subsistence GEP of step 06, in the same run, in base-year USD (``gep_value_<base year>``),
and count only the country-years that have a GEP value (countries without a CWON rental rate have none). The map
colors each ee_r264 region by the base-year GEP of the country whose ISO3 code is the region's own code
(``ee_r264_label``), in five quantile classes of the countries with a value.
"""
import sqlite3
from contextlib import closing
from pathlib import Path as FilePath

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.collections import PatchCollection
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path

import consts
from utils import input_path


def key_statistics(valued, column, base_year):
    """Return table 1: number of countries and observations, years, base-year and average annual global GEP.

    Args:
        valued: Subsistence GEP rows with a value in ``column`` (Country, Year, ``column``).
        column: GEP column in base-year USD.
        base_year: GEP base year.

    Returns:
        DataFrame with columns Metric and Value (text).
    """
    annual = valued.groupby('Year')[column].sum()
    base_gep = valued.loc[valued['Year'] == base_year, column].sum() / 1e9
    return pd.DataFrame({
        'Metric': ['Number of countries',
                   'Total observations (country-years)',
                   'Years covered',
                   '%d Global GEP (billions %d USD)' % (base_year, base_year),
                   'Average annual global GEP (billions %d USD)' % base_year],
        'Value': [str(valued['Country'].nunique()),
                  str(len(valued)),
                  f"{valued['Year'].min()}-{valued['Year'].max()}",
                  f'${base_gep:.2f}',
                  f'${annual.mean() / 1e9:.2f}']})


def top_countries(valued, column, base_year, count):
    """Return table 2: the countries with the largest base-year GEP.

    Args:
        valued: Subsistence GEP rows with a value in ``column`` (Country, Year, ``column``).
        column: GEP column in base-year USD.
        base_year: GEP base year.
        count: Number of countries.

    Returns:
        DataFrame with Rank, Country and the GEP in billions as text ('$1.23').
    """
    label = '%d GEP (billions %d USD)' % (base_year, base_year)
    base = valued[valued['Year'] == base_year]
    top = base.nlargest(count, column)[['Country', column]].reset_index(drop=True)
    top.insert(0, 'Rank', range(1, len(top) + 1))
    top[label] = [f'${value / 1e9:.2f}' for value in top[column]]
    return top[['Rank', 'Country', label]]


def appendix_table(valued, column, base_year):
    """Return table 3: every country's first and last year with GEP and the percent change between them.

    Args:
        valued: Subsistence GEP rows with a value in ``column`` (Country, Year, ``column``).
        column: GEP column in base-year USD.
        base_year: GEP base year, for the column labels.

    Returns:
        DataFrame sorted by Country with First Year, First GEP, Last Year, Last GEP (base-year USD, rounded) and
        Percent Change (inf where the first value is 0 and the last is not).
    """
    rows = []
    for country in sorted(valued['Country'].unique()):
        values = valued[valued['Country'] == country].sort_values('Year')
        first_gep, last_gep = values[column].iloc[0], values[column].iloc[-1]
        if first_gep > 0:
            change = ((last_gep - first_gep) / first_gep) * 100
        else:
            change = 0 if last_gep == 0 else np.inf
        rows.append({'Country': country,
                     'First Year': int(values['Year'].iloc[0]),
                     'First GEP (%d USD)' % base_year: int(round(first_gep)),
                     'Last Year': int(values['Year'].iloc[-1]),
                     'Last GEP (%d USD)' % base_year: int(round(last_gep)),
                     'Percent Change': change})
    return pd.DataFrame(rows).sort_values('Country').reset_index(drop=True)


def coverage_statistics(valued):
    """Return the number of countries by the number of years with a GEP value, as text.

    Args:
        valued: Subsistence GEP rows with a GEP value (Country, Year).

    Returns:
        Text block.
    """
    years = valued.groupby('Country')['Year'].nunique()
    return (f"\nCountry Coverage:\n"
            f"- Countries with 1 year of data: {(years == 1).sum()}\n"
            f"- Countries with 2 years of data: {(years == 2).sum()}\n"
            f"- Countries with 3+ years of data: {(years >= 3).sum()}\n"
            f"- Total countries: {valued['Country'].nunique()}\n")


def plot_global_gep(valued, column, base_year):
    """Plot the global subsistence GEP per year, in base-year USD.

    Args:
        valued: Subsistence GEP rows with a value in ``column`` (Year, ``column``).
        column: GEP column in base-year USD.
        base_year: GEP base year, for the axis label.

    Returns:
        matplotlib Figure.
    """
    size, color, line_width, marker_size = (11, 5.5), '#1b7837', 2.5, 5
    title_size, label_size, grid_color, grid_width = 15, 12, '#d9d9d9', 0.8
    annual = valued.groupby('Year')[column].sum() / 1e9
    figure, axes = plt.subplots(figsize=size)
    axes.plot(annual.index, annual.values, color=color, linewidth=line_width, marker='o', markersize=marker_size)
    axes.set_title('Global Subsistence-Crop GEP Over Time', fontsize=title_size)
    axes.set_xlabel('Year', fontsize=label_size)
    axes.set_ylabel('Global GEP (billion %d USD)' % base_year, fontsize=label_size)
    axes.set_xlim(annual.index.min(), annual.index.max())
    axes.grid(axis='y', color=grid_color, linewidth=grid_width)
    axes.spines['top'].set_visible(False)
    axes.spines['right'].set_visible(False)
    figure.tight_layout()
    return figure


def gpkg_wkb(blob):
    """Return the WKB geometry inside a GeoPackage geometry blob.

    Args:
        blob: Geometry as a GeoPackage stores it (bytes): an 8-byte header, an optional envelope, then WKB.

    Returns:
        bytes of the WKB geometry.
    """
    header_size = 8
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}  # bytes of the envelope by its indicator (flag bits 1-3)
    envelope = (blob[3] >> 1) & 0b111
    return blob[header_size + envelope_sizes[envelope]:]


def read_regions(path, excluded):
    """Read the ee_r264 regions and their outlines from the GeoPackage with sqlite3 (no GDAL needed).

    Args:
        path: ee_r264 GeoPackage: one layer of multipolygons in longitude and latitude (EPSG:4326).
        excluded: ee_r264 labels to leave out.

    Returns:
        DataFrame with ee_r264_label and geometry (shapely), one row per region.
    """
    layer, label, geometry = 'ee_r264_correspondence', 'ee_r264_label', 'geom'
    with closing(sqlite3.connect(FilePath(path).resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        rows = connection.execute(f'SELECT {label}, {geometry} FROM {layer}').fetchall()
    regions = pd.DataFrame({'ee_r264_label': [row[0] for row in rows],
                            'geometry': shapely.from_wkb([gpkg_wkb(row[1]) for row in rows])})
    return regions[~regions['ee_r264_label'].isin(excluded)].reset_index(drop=True)


def equal_earth(coordinates):
    """Project longitude and latitude to the Equal Earth projection (Šavrič, Patterson & Jenny 2019), unit sphere.

    Args:
        coordinates: Array (n, 2) of longitude and latitude in degrees.

    Returns:
        Array (n, 2) of x and y.
    """
    a1, a2, a3, a4 = 1.340264, -0.081106, 0.000893, 0.003796
    longitude, latitude = np.radians(coordinates[:, 0]), np.radians(coordinates[:, 1])
    theta = np.arcsin(np.sqrt(3) / 2 * np.sin(latitude))
    theta2, theta6 = theta ** 2, theta ** 6
    x = 2 * np.sqrt(3) * longitude * np.cos(theta) / (3 * (a1 + 3 * a2 * theta2 + theta6 * (7 * a3 + 9 * a4 * theta2)))
    y = theta * (a1 + a2 * theta2 + theta6 * (a3 + a4 * theta2))
    return np.column_stack([x, y])


def region_paths(outlines):
    """Return one matplotlib Path per region, holes included, built with array operations.

    matplotlib fills a path by the nonzero rule, so each polygon's outer ring is turned counter-clockwise and its
    holes clockwise; otherwise a hole (such as Lesotho in South Africa) would be filled.

    Args:
        outlines: Array of shapely Polygons or MultiPolygons.

    Returns:
        List of matplotlib Paths in the order of ``outlines``; each ring starts with MOVETO and ends on its first
        point.
    """
    parts, region_of_part = shapely.get_parts(outlines, return_index=True)
    rings, part_of_ring = shapely.get_rings(parts, return_index=True)
    outer = np.r_[True, part_of_ring[1:] != part_of_ring[:-1]]  # the first ring of each polygon is the outer one
    flip = shapely.is_ccw(rings) != outer
    rings[flip] = shapely.reverse(rings[flip])
    coordinates, ring_of_point = shapely.get_coordinates(rings, return_index=True)
    codes = np.full(len(coordinates), Path.LINETO, dtype=Path.code_type)
    codes[np.r_[True, ring_of_point[1:] != ring_of_point[:-1]]] = Path.MOVETO
    region_of_point = region_of_part[part_of_ring[ring_of_point]]
    splits = np.searchsorted(region_of_point, np.arange(1, len(outlines)))
    return [Path(points, point_codes)
            for points, point_codes in zip(np.split(coordinates, splits), np.split(codes, splits))]


def million_text(value):
    """Return a USD value in million USD, to three significant digits ('0.378', '36.5', '4750').

    Args:
        value: Value in USD.

    Returns:
        Text.
    """
    return np.format_float_positional(value / 1e6, precision=3, fractional=False, trim='-')


def plot_gep_map(valued, regions, column, base_year):
    """Map the base-year subsistence GEP of each country in five quantile classes.

    Each region takes the class of the country whose ISO3 code is its own code (``ee_r264_label``); regions of
    countries without a base-year GEP are gray.

    Args:
        valued: Subsistence GEP rows with a value in ``column`` (alpha-3, Year, ``column``).
        regions: ee_r264 regions (ee_r264_label, geometry in longitude and latitude).
        column: GEP column in base-year USD.
        base_year: GEP base year.

    Returns:
        matplotlib Figure, in the Equal Earth projection.
    """
    size, title_size, legend_size = (11, 5.5), 15, 9
    class_colors = ['#8cc27f', '#62a95a', '#3c8f3e', '#1b7837', '#0b5224']  # one green, light to dark
    missing_color, edge_color, edge_width = '#dcdcdc', '#ffffff', 0.2
    gep = valued.loc[valued['Year'] == base_year].set_index('alpha-3')[column]
    classes, edges = pd.qcut(gep, len(class_colors), labels=False, retbins=True)
    region_class = regions['ee_r264_label'].map(classes)
    colors = [missing_color if np.isnan(number) else class_colors[int(number)] for number in region_class]
    outlines = shapely.transform(regions['geometry'].values, equal_earth)
    figure, axes = plt.subplots(figsize=size)
    axes.add_collection(PatchCollection([PathPatch(path) for path in region_paths(outlines)],
                                        facecolors=colors, edgecolors=edge_color, linewidths=edge_width))
    axes.autoscale_view()
    axes.set_aspect('equal')
    axes.set_axis_off()
    axes.set_title('Subsistence-Crop GEP by Country, %d' % base_year, fontsize=title_size)
    labels = [f'{million_text(low)}–{million_text(high)}' for low, high in zip(edges[:-1], edges[1:])]
    handles = [Patch(facecolor=color, label=label) for color, label in zip(class_colors, labels)]
    handles.append(Patch(facecolor=missing_color, label='Not estimated'))
    axes.legend(handles=handles, title='Million %d USD' % base_year, loc='lower left', frameon=False,
                fontsize=legend_size, title_fontsize=legend_size)
    figure.tight_layout()
    unmapped = sorted(set(gep.index) - set(regions['ee_r264_label']))
    print(f'07: map of {region_class.notna().sum()} countries with GEP' +
          (f'; not on the map: {", ".join(unmapped)}' if unmapped else ''))
    return figure


def run(subsistence):
    """Build the paper tables, figure and map, and print the coverage statistics.

    Args:
        subsistence: Subsistence GEP of step 06 (Country, alpha-3, Year, gep_value_<base year>).

    Returns:
        Dict with ``table_key_statistics``, ``table_top_countries``, ``table_appendix``, ``figure_global_gep`` and
        ``figure_gep_map`` (matplotlib Figures).
    """
    base_year = consts.BASE_YEAR
    column = 'gep_value_%d' % base_year
    valued = subsistence.dropna(subset=[column])
    statistics = key_statistics(valued, column, base_year)
    coverage = coverage_statistics(valued)
    print('07: %s countries, %s %s; %s' % (statistics['Value'].iloc[0], statistics['Metric'].iloc[3],
                                          statistics['Value'].iloc[3], coverage.strip().replace('\n', '; ')))
    regions = read_regions(input_path('ee_r264'), consts.MAP_EXCLUDED_REGIONS)
    return {'table_key_statistics': statistics,
            'table_top_countries': top_countries(valued, column, base_year, consts.TOP_COUNTRIES),
            'table_appendix': appendix_table(valued, column, base_year),
            'figure_global_gep': plot_global_gep(valued, column, base_year),
            'figure_gep_map': plot_gep_map(valued, regions, column, base_year)}
