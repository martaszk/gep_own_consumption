"""Run the crop provision GEP pipeline from the input files to the results.

Usage::

    python run.py                          all steps; results in results/<YYYY-MM-DD_HH-MM>/
    python run.py --no-intermediates       do not write the intermediate tables
    python run.py --until 5                run steps 01-05 only
    python run.py --no-validate            skip the checks of validate.py
    python run.py --set NAME=VALUE         override a value of consts.py for this run (repeatable)
    python run.py --set DICT.KEY=VALUE     override one entry of a dict of consts.py, e.g. INPUTS.prices=file.csv
    python run.py --tag NAME               append _NAME to the name of the run folder

VALUE is read as a Python literal (1.2, None, False, (), {'EGY': 2018}, 'cwon'); anything else is taken as text,
so ``--set METHOD=cwon`` works as well. The steps pass their tables on in memory. Each run folder holds
``intermediates/`` (tables passed between steps; file names start with the number of the step that made them),
``outputs/`` (results) and ``run_settings.yaml`` (every value of consts.py, the overrides, versions, checks).
The exit code is 1 when a hard check of validate.py fails.
"""
import argparse
import ast
import datetime
import difflib
import platform
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import yaml
from matplotlib.figure import Figure

import consts
import step_01_rulis_own_share
import step_02_smallholder_share
import step_03_yearly_share_paths
import step_04_commercial_crop_provision
import step_05_own_consumption
import step_06_gep_panel
import step_07_paper_outputs
import validate


def pipeline_steps():
    """Return the steps in the order they run.

    Returns:
        List of (step number, module, keys of the tables that the module's ``run`` takes, in order).
    """
    return [(1, step_01_rulis_own_share, []),
            (2, step_02_smallholder_share, ['rulis_surveys']),
            (3, step_03_yearly_share_paths, ['own_share_observed', 'smallholder_share',
                                             'smallholder_share_rulis_surveys']),
            (4, step_04_commercial_crop_provision, []),
            (5, step_05_own_consumption, ['smallholder_share', 'smallholder_share_panel', 'own_share_panel',
                                          'commercial_by_crop']),
            (6, step_06_gep_panel, ['own_consumption_panel', 'commercial_by_country']),
            (7, step_07_paper_outputs, ['subsistence', 'crop_provision_panel'])]


def parse_args():
    """Read the command line.

    Returns:
        argparse Namespace with no_intermediates, until, no_validate, set and tag.
    """
    steps = [number for number, _, _ in pipeline_steps()]
    parser = argparse.ArgumentParser(description='Run the crop provision GEP pipeline.')
    parser.add_argument('--no-intermediates', action='store_true', help='do not write the intermediate tables')
    parser.add_argument('--until', type=int, choices=steps, default=steps[-1], help='last step to run')
    parser.add_argument('--no-validate', action='store_true', help='skip the checks of validate.py')
    parser.add_argument('--set', action='append', default=[], metavar='NAME=VALUE',
                        help='override a value of consts.py for this run; NAME.KEY=VALUE for one dict entry')
    parser.add_argument('--tag', help='text appended to the name of the run folder')
    return parser.parse_args()


def parse_value(text):
    """Read an override value as a Python literal, or as text if it is not one.

    Args:
        text: Value as given on the command line.

    Returns:
        The literal (number, None, bool, tuple, list, dict, quoted text) or the text itself.
    """
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text


def same_form(current, value):
    """Give an override the type of the value it replaces where the two differ only in form.

    Args:
        current: Value in consts.py.
        value: Value from the command line.

    Returns:
        ``value`` as a Path, tuple or set where ``current`` is one, otherwise unchanged.
    """
    if isinstance(current, Path) and isinstance(value, str):
        return Path(value)
    if isinstance(current, tuple) and isinstance(value, list):
        return tuple(value)
    if isinstance(current, (set, frozenset)) and isinstance(value, (list, tuple)):
        return set(value)
    return value


def apply_override(assignment):
    """Apply one ``--set`` to consts.py for this run.

    Args:
        assignment: 'NAME=VALUE', or 'NAME.KEY=VALUE' for one entry of a dict.

    Returns:
        Tuple (what was set: 'NAME' or 'NAME.KEY', the value now in consts.py).

    Raises:
        SystemExit: The assignment is malformed or names a value consts.py does not have.
    """
    if '=' not in assignment:
        raise SystemExit(f'--set needs NAME=VALUE, got {assignment!r}')
    target, text = assignment.split('=', 1)
    target = target.strip()
    name, _, key_text = target.partition('.')
    names = [n for n in vars(consts) if n.isupper()]
    if name not in names:
        close = difflib.get_close_matches(name.upper(), names, n=3)
        raise SystemExit(f'--set: consts.py has no {name!r}' + (f'; did you mean {close}?' if close else ''))
    value = parse_value(text.strip())
    current = getattr(consts, name)
    if not key_text:
        setattr(consts, name, same_form(current, value))
        return target, getattr(consts, name)
    if not isinstance(current, dict):
        raise SystemExit(f'--set {target}: {name} is not a dict')
    key = parse_value(key_text)
    if key not in current:
        print(f'Note: --set {target} adds a new key to {name}')
    entries = dict(current)
    entries[key] = same_form(entries.get(key), value)
    setattr(consts, name, entries)
    return target, entries[key]


def create_run_folder(results_dir, tag, intermediates):
    """Create the folder of this run.

    The name is the date and time of the start (``consts.RUN_FOLDER_FORMAT``); if a folder of the same minute
    exists, seconds are added.

    Args:
        results_dir: Folder of all runs.
        tag: Text appended to the name, or None.
        intermediates: Whether to create the intermediates folder.

    Returns:
        Path of the new folder.

    Raises:
        SystemExit: A folder of the same second exists.
    """
    now = datetime.datetime.now()
    suffix = f'_{tag}' if tag else ''
    folder = Path(results_dir) / (now.strftime(consts.RUN_FOLDER_FORMAT) + suffix)
    if folder.exists():
        folder = Path(results_dir) / (now.strftime(consts.RUN_FOLDER_FORMAT_SECONDS) + suffix)
    if folder.exists():
        raise SystemExit(f'{folder} exists already')
    (folder / 'outputs').mkdir(parents=True)
    if intermediates:
        (folder / 'intermediates').mkdir()
    return folder


def result_path(run_dir, key):
    """Return the file of a step result in the run folder.

    Args:
        run_dir: Run folder.
        key: Key in ``consts.INTERMEDIATES`` or ``consts.OUTPUTS``.

    Returns:
        Path; ``{base_year}`` in the file name is filled in.

    Raises:
        KeyError: The key is in neither dict.
    """
    if key in consts.INTERMEDIATES:
        return Path(run_dir) / 'intermediates' / consts.INTERMEDIATES[key].format(base_year=consts.BASE_YEAR)
    if key in consts.OUTPUTS:
        return Path(run_dir) / 'outputs' / consts.OUTPUTS[key].format(base_year=consts.BASE_YEAR)
    raise KeyError(f'{key} is in neither consts.INTERMEDIATES nor consts.OUTPUTS')


def write_result(path, value):
    """Write one step result: a table as CSV, a text as a text file, a figure as PNG.

    Args:
        path: File to write; a figure gets the extension .png added.
        value: DataFrame, str or matplotlib Figure.

    Returns:
        List of the files written.

    Raises:
        TypeError: Any other type of value.
    """
    if isinstance(value, pd.DataFrame):
        value.to_csv(path, index=False)
        return [path]
    if isinstance(value, str):
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(value)
        return [path]
    if isinstance(value, Figure):
        png = path.with_name(path.name + '.png')
        value.savefig(png, dpi=consts.FIGURE_DPI)
        plt.close(value)
        return [png]
    raise TypeError(f'cannot write a {type(value).__name__} to {path}')


def yaml_value(value):
    """Convert a value of consts.py into plain YAML data.

    Args:
        value: Any value of consts.py.

    Returns:
        The value with paths as text, tuples and sets as lists (sets sorted) and dict keys kept.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(yaml_value(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [yaml_value(item) for item in value]
    if isinstance(value, dict):
        return {key: yaml_value(item) for key, item in value.items()}
    return value


def git_state():
    """Return the commit of the code and whether tracked files have changes not yet committed.

    Returns:
        Tuple (commit hash, True/False), or (None, None) outside a git repository.
    """
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=consts.ROOT, capture_output=True, text=True,
                                check=True).stdout.strip()
        changes = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=consts.ROOT,
                                 capture_output=True, text=True, check=True).stdout.strip()
        return commit, bool(changes)
    except (OSError, subprocess.CalledProcessError):
        return None, None


def package_versions():
    """Return the versions of the packages the pipeline uses.

    Returns:
        Dict of package name -> version (None if not installed).
    """
    packages = ['pandas', 'numpy', 'matplotlib', 'shapely', 'openpyxl', 'PyYAML']
    versions = {}
    for package in packages:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def write_run_settings(run_dir, run_info):
    """Write ``run_settings.yaml``: how the run went and every value of consts.py it used.

    Args:
        run_dir: Run folder.
        run_info: Dict describing the run (times, command, overrides, status, checks).
    """
    commit, changes = git_state()
    run_info = dict(run_info, git_commit=commit, git_uncommitted_changes=changes, python=platform.python_version(),
                    platform=platform.platform(), packages=package_versions())
    settings = {name: yaml_value(value) for name, value in vars(consts).items() if name.isupper()}
    with open(Path(run_dir) / consts.RUN_SETTINGS_FILE, 'w', encoding='utf-8') as handle:
        yaml.safe_dump({'run': run_info, 'settings': settings}, handle, sort_keys=False, allow_unicode=True,
                       default_flow_style=None, width=120)


def main():
    """Run the steps, write their results, run the checks and record the settings of the run."""
    args = parse_args()
    overrides = dict(apply_override(assignment) for assignment in args.set)
    for target, value in overrides.items():
        print(f'Override: {target} = {value!r}')
    run_dir = create_run_folder(consts.RESULTS_DIR, args.tag, not args.no_intermediates)
    print(f'Run folder: {run_dir}')
    started = datetime.datetime.now()
    run_info = {'folder': str(run_dir), 'started': started.strftime('%Y-%m-%d %H:%M:%S'),
                'command': ' '.join(['python'] + sys.argv), 'overrides': yaml_value(overrides),
                'last_step': args.until, 'intermediates_written': not args.no_intermediates,
                'status': 'failed', 'checks': None}
    tables = {}
    try:
        for number, module, inputs in pipeline_steps():
            if number > args.until:
                break
            print('\n=== ' + module.__doc__.strip().splitlines()[0])
            step_start = time.perf_counter()
            results = module.run(*[tables[key] for key in inputs])
            for key, value in results.items():
                if not (args.no_intermediates and key in consts.INTERMEDIATES):
                    write_result(result_path(run_dir, key), value)
            tables.update(results)
            print(f'--- step {number:02d} done in {time.perf_counter() - step_start:.1f} s')
        if not args.no_validate:
            print('\n=== Checks (validate.py)')
            failures, flags = validate.run_checks(tables)
            run_info['checks'] = {'hard_failures': failures, 'flags': flags}
        run_info['status'] = 'completed'
    finally:
        finished = datetime.datetime.now()
        run_info['finished'] = finished.strftime('%Y-%m-%d %H:%M:%S')
        run_info['duration_s'] = round((finished - started).total_seconds(), 1)
        write_run_settings(run_dir, run_info)
    print(f'\nResults: {run_dir}')
    checks = run_info['checks']
    sys.exit(1 if checks and checks['hard_failures'] else 0)


if __name__ == '__main__':
    main()
