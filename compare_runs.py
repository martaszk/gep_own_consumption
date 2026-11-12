"""Compare the result files of two pipeline runs.

Usage::

    python compare_runs.py RUN_A RUN_B [--rtol 1e-9] [--ignore PATTERN ...] [--brief]

Files are paired by their path relative to the run folder. Each pair gets one status:

- ``IDENTICAL``: the two files are the same byte for byte.
- ``EQUAL``: CSV files with the same columns, the same rows in the same order, the same text values and the
  same empty cells, whose numbers differ by at most ``rtol`` (relative difference).
- ``DIFFERENT``: anything else. The details say which columns differ, in how many cells, by how much, and
  give the first rows concerned.
- ``MISSING``: the file exists in only one of the two runs.

The settings file of a run (``run_settings.yaml``) is not given a status. The settings whose values differ
between the two runs are listed instead.

The exit code is 1 when at least one pair is ``DIFFERENT`` or ``MISSING``, otherwise 0.
"""
import argparse
import fnmatch
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

import consts


def file_hash(path):
    """Return the SHA-256 hex digest of a file.

    Args:
        path: File to hash.

    Returns:
        Hex digest string.
    """
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def list_files(run_dir, ignore):
    """List the files of a run folder by relative path.

    Args:
        run_dir: Run folder.
        ignore: Glob patterns (matched against the relative path with forward slashes) of files to skip.

    Returns:
        Dict mapping relative path (forward slashes) to absolute ``Path``.
    """
    files = {}
    for path in sorted(Path(run_dir).rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(run_dir).as_posix()
        if any(fnmatch.fnmatch(rel, pattern) for pattern in ignore):
            continue
        files[rel] = path
    return files


def read_table(path):
    """Read a result CSV file so that only empty cells count as missing values.

    Args:
        path: CSV file.

    Returns:
        DataFrame. Text such as ``NA`` (the ISO code of Namibia) stays text.
    """
    return pd.read_csv(path, keep_default_na=False, na_values=[''], low_memory=False)


def row_labels(table, mask):
    """Describe the first rows selected by a mask, for messages.

    Args:
        table: DataFrame the mask refers to.
        mask: Boolean array, one value per row.

    Returns:
        Text naming up to ``consts.COMPARE_ROWS_SHOWN`` rows by their line number in the file (the header is
        line 1) and the values of the first ``consts.COMPARE_KEY_COLUMNS`` columns that do not hold floats.
    """
    key_columns = [c for c in table.columns if not pd.api.types.is_float_dtype(table[c])][:consts.COMPARE_KEY_COLUMNS]
    labels = []
    for position in np.flatnonzero(mask)[:consts.COMPARE_ROWS_SHOWN]:
        values = ', '.join(f'{c}={table[c].iat[position]}' for c in key_columns)
        labels.append(f'line {position + 2} ({values})' if values else f'line {position + 2}')
    return '; '.join(labels)


def compare_column(table_a, table_b, column, rtol):
    """Compare one column of two tables of the same length.

    Integer columns must match exactly, float columns within ``rtol``, all other columns as text.
    Missing values must sit in the same rows.

    Args:
        table_a: Table from run A.
        table_b: Table from run B.
        column: Column present in both tables.
        rtol: Relative tolerance for float columns.

    Returns:
        ``None`` when the column matches, otherwise a one-line description of the differences.
    """
    a, b = table_a[column], table_b[column]
    numeric = pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b)
    if numeric and pd.api.types.is_integer_dtype(a) and pd.api.types.is_integer_dtype(b):
        differs = (a != b).to_numpy()
        if not differs.any():
            return None
        return f'{column}: {differs.sum()} integer cells differ; {row_labels(table_a, differs)}'
    if numeric:
        x, y = a.to_numpy(float), b.to_numpy(float)
        missing_x, missing_y = np.isnan(x), np.isnan(y)
        differs = ~np.isclose(x, y, rtol=rtol, atol=0.0, equal_nan=True) | (missing_x != missing_y)
        if not differs.any():
            return None
        both = differs & ~missing_x & ~missing_y
        with np.errstate(divide='ignore', invalid='ignore'):
            relative = np.abs(x[both] - y[both]) / np.maximum(np.abs(x[both]), np.abs(y[both]))
        largest = f'{np.nanmax(relative):.3g}' if relative.size else 'n/a'
        return (f'{column}: {differs.sum()} cells differ (largest relative difference {largest}, '
                f'empty in one run only: {(missing_x != missing_y).sum()}); {row_labels(table_a, differs)}')
    text_a = a.astype(object).where(a.notna(), '<empty>').astype(str).to_numpy()
    text_b = b.astype(object).where(b.notna(), '<empty>').astype(str).to_numpy()
    differs = text_a != text_b
    if not differs.any():
        return None
    first = int(np.flatnonzero(differs)[0])
    note = '' if a.dtype == b.dtype else f' (column type {a.dtype} vs {b.dtype})'
    return (f'{column}: {differs.sum()} text cells differ{note}, first: {text_a[first]!r} vs {text_b[first]!r}; '
            f'{row_labels(table_a, differs)}')


def compare_csv(path_a, path_b, rtol):
    """Compare two CSV files cell by cell.

    Args:
        path_a: File from run A.
        path_b: File from run B.
        rtol: Relative tolerance for float columns.

    Returns:
        Tuple ``(status, details)``: status ``EQUAL`` or ``DIFFERENT`` and a list of messages.
    """
    table_a, table_b = read_table(path_a), read_table(path_b)
    details = []
    if list(table_a.columns) != list(table_b.columns):
        only_a = [c for c in table_a.columns if c not in table_b.columns]
        only_b = [c for c in table_b.columns if c not in table_a.columns]
        if only_a:
            details.append(f'columns only in A: {only_a}')
        if only_b:
            details.append(f'columns only in B: {only_b}')
        if not only_a and not only_b:
            details.append('same columns in a different order')
    if len(table_a) != len(table_b):
        details.append(f'rows: {len(table_a)} in A, {len(table_b)} in B')
        return 'DIFFERENT', details
    for column in [c for c in table_a.columns if c in table_b.columns]:
        message = compare_column(table_a, table_b, column, rtol)
        if message:
            details.append(message)
    return ('DIFFERENT' if details else 'EQUAL'), details


def compare_text(path_a, path_b):
    """Compare two text files line by line.

    Args:
        path_a: File from run A.
        path_b: File from run B.

    Returns:
        Tuple ``('DIFFERENT', details)`` naming the first differing line.
    """
    lines_a = Path(path_a).read_text(encoding='utf-8', errors='replace').splitlines()
    lines_b = Path(path_b).read_text(encoding='utf-8', errors='replace').splitlines()
    for number, (line_a, line_b) in enumerate(zip(lines_a, lines_b), start=1):
        if line_a != line_b:
            return 'DIFFERENT', [f'first difference in line {number}: {line_a[:consts.COMPARE_TEXT_SHOWN]!r} vs '
                                 f'{line_b[:consts.COMPARE_TEXT_SHOWN]!r}']
    if len(lines_a) != len(lines_b):
        return 'DIFFERENT', [f'lines: {len(lines_a)} in A, {len(lines_b)} in B']
    return 'DIFFERENT', ['line endings or encoding differ']


def compare_pair(path_a, path_b, rtol):
    """Compare two files of the same relative path.

    Args:
        path_a: File from run A.
        path_b: File from run B.
        rtol: Relative tolerance for float columns of CSV files.

    Returns:
        Tuple ``(status, details)``.
    """
    if file_hash(path_a) == file_hash(path_b):
        return 'IDENTICAL', []
    suffix = Path(path_a).suffix.lower()
    if suffix == '.csv':
        return compare_csv(path_a, path_b, rtol)
    if suffix in consts.COMPARE_TEXT_SUFFIXES:
        return compare_text(path_a, path_b)
    return 'DIFFERENT', ['binary files differ']


def settings_differences(path_a, path_b):
    """List the settings whose values differ between two run settings files.

    Args:
        path_a: ``run_settings.yaml`` of run A.
        path_b: ``run_settings.yaml`` of run B.

    Returns:
        List of lines ``NAME: value A -> value B``.
    """
    settings_a = yaml.safe_load(Path(path_a).read_text(encoding='utf-8')).get('settings', {})
    settings_b = yaml.safe_load(Path(path_b).read_text(encoding='utf-8')).get('settings', {})
    lines = []
    for name in sorted(set(settings_a) | set(settings_b)):
        value_a, value_b = settings_a.get(name, '<not set>'), settings_b.get(name, '<not set>')
        if value_a != value_b:
            lines.append(f'{name}: {value_a!r} -> {value_b!r}')
    return lines


def compare_runs(run_a, run_b, rtol, ignore=(), brief=False):
    """Compare all files of two run folders and print one status line per file.

    Args:
        run_a: First run folder.
        run_b: Second run folder.
        rtol: Relative tolerance for numbers in CSV files.
        ignore: Glob patterns of relative paths to skip.
        brief: Print only files that are ``DIFFERENT`` or ``MISSING``.

    Returns:
        Dict mapping each status to the number of files with that status.
    """
    files_a = list_files(run_a, list(ignore) + [consts.RUN_SETTINGS_FILE])
    files_b = list_files(run_b, list(ignore) + [consts.RUN_SETTINGS_FILE])
    counts = {'IDENTICAL': 0, 'EQUAL': 0, 'DIFFERENT': 0, 'MISSING': 0}
    for rel in sorted(set(files_a) | set(files_b)):
        if rel not in files_a or rel not in files_b:
            status, details = 'MISSING', [f'only in {"B" if rel not in files_a else "A"}']
        else:
            status, details = compare_pair(files_a[rel], files_b[rel], rtol)
        counts[status] += 1
        if brief and status in ('IDENTICAL', 'EQUAL'):
            continue
        print(f'{status:<10} {rel}')
        for line in details:
            print(f'           {line}')
    settings_a, settings_b = Path(run_a) / consts.RUN_SETTINGS_FILE, Path(run_b) / consts.RUN_SETTINGS_FILE
    if settings_a.is_file() and settings_b.is_file():
        lines = settings_differences(settings_a, settings_b)
        print(f'Settings that differ: {len(lines)}')
        for line in lines:
            print(f'           {line}')
    print('Summary: ' + ', '.join(f'{status} {number}' for status, number in counts.items()))
    return counts


def main():
    """Parse the command line, compare the two runs and exit with code 1 if anything differs."""
    parser = argparse.ArgumentParser(description='Compare the result files of two pipeline runs.')
    parser.add_argument('run_a', help='first run folder, e.g. results/2026-11-11_16-05')
    parser.add_argument('run_b', help='second run folder')
    parser.add_argument('--rtol', type=float, default=consts.COMPARE_RTOL,
                        help=f'relative tolerance for numbers in CSV files (default {consts.COMPARE_RTOL})')
    parser.add_argument('--ignore', nargs='*', default=[], help='glob patterns of relative paths to skip')
    parser.add_argument('--brief', action='store_true', help='print only files that differ or are missing')
    args = parser.parse_args()
    for folder in (args.run_a, args.run_b):
        if not Path(folder).is_dir():
            parser.error(f'not a folder: {folder}')
    counts = compare_runs(args.run_a, args.run_b, args.rtol, args.ignore, args.brief)
    sys.exit(1 if counts['DIFFERENT'] or counts['MISSING'] else 0)


if __name__ == '__main__':
    main()
