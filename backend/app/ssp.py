"""Sound speed profile selection, download and reading."""

import os
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .errors import InputError


def _load_getSSP():
    """Import the Ocean Navigator helper lazily; it is only needed for the
    'use current SSP' path and pulls in network dependencies."""
    try:
        from ocean_navigator_api_script_csv import getSSP

        return getSSP
    except ImportError:
        return None


def read_ssp(ssp_file):
    """Return (depth, speed) arrays from a CTD csv (columns 0 and 4)."""
    ssp = pd.read_table(
        ssp_file,
        delimiter=",",
        usecols=[0, 4],
        names=["depth", "speed"],
        skipinitialspace=True,
        header=0,
    )
    depth = ssp["depth"].to_numpy(dtype=float, copy=True)
    speed = ssp["speed"].to_numpy(dtype=float, copy=True)
    if depth.size == 0:
        raise InputError(f"SSP file {ssp_file} contains no samples.")
    return depth, speed


def determine_ssp(date_string, ssp_dir=None):
    """Pick the archived CTD cast closest to `date_string` (yyyymmdd).

    Falls back to any cast from the same month if nothing is within 14 days.

    Fixes a bug in the original: `abs(difference < 14)` compared a bool, so the
    14-day window never applied. It is now `abs(difference) < 14`.
    """
    ssp_dir = Path(ssp_dir or config.SSP_DIR)
    if not ssp_dir.is_dir():
        raise InputError(f"SSP directory not found: {ssp_dir}")

    try:
        date_selected = int(date_string)
        month_selected = int(str(date_string)[4:6])
    except (TypeError, ValueError):
        raise InputError("SSP date must be in yyyymmdd form, e.g. 20230619.")

    best_date = None
    best_file = None
    month_match = None

    for file_name in sorted(os.listdir(ssp_dir)):
        try:
            stamp = file_name.split(".")[0]
            month = int(stamp[4:6])
            file_date = int(stamp[0:8])
        except (ValueError, IndexError):
            continue

        difference = date_selected - file_date

        if abs(difference) < 14:
            if best_date is None or abs(difference) < abs(date_selected - best_date):
                best_date = file_date
                best_file = file_name

        if month == month_selected and month_match is None:
            month_match = file_name

    chosen = best_file or month_match
    if chosen is None:
        raise InputError(
            f"No archived SSP found near {date_string} in {ssp_dir}."
        )
    return ssp_dir / chosen


def fetch_current_ssp(lat, lon, ssp_dir=None):
    """Download a fresh profile via the Ocean Navigator API and return its path.

    Returns the path to the newest file in the SSP directory.
    """
    getSSP = _load_getSSP()
    if getSSP is None:
        raise InputError(
            "ocean_navigator_api_script_csv is not importable, so the current "
            "SSP cannot be downloaded. Untick 'Use current SSP'."
        )

    ssp_dir = Path(ssp_dir or config.SSP_DIR)
    getSSP([lat, lon])

    files = [f for f in ssp_dir.iterdir() if f.is_file()]
    if not files:
        raise InputError(f"No SSP file appeared in {ssp_dir} after download.")

    return max(files, key=lambda f: f.stat().st_mtime)


def delete_ssp(path):
    """Remove a downloaded profile; silently ignore a missing file."""
    try:
        Path(path).unlink()
        return True
    except FileNotFoundError:
        return False


def resolve_ssp(use_current, date_string, lat=None, lon=None):
    """Return (path, is_temporary) for the profile this run should use."""
    if use_current:
        if lat is None or lon is None:
            raise InputError("Current SSP requires a source position.")
        return fetch_current_ssp(lat, lon), False
    return determine_ssp(date_string), False


def profile_for_plot(ssp_file):
    """Depth/speed arrays for the SSP figure, cleaned the way the GUI did."""
    depth, speed = read_ssp(ssp_file)
    depth = np.asarray(depth, dtype=float)
    speed = np.asarray(speed, dtype=float)
    if depth.size > 5:
        depth[0] = 0.0
        speed[0] = speed[5]
    return depth, speed
