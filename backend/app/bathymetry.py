"""Bathymetry slice extraction and .bty file writing."""

from functools import lru_cache

import matplotlib.tri as mtri
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import Delaunay

from . import config
from .errors import InputError
from .geometry import calculate_terminus_points

BATHY_STEP_M = 100.0  # spacing of bathymetry samples along the slice (grid is ~150-250 m)
# Sampling the triangulated grid every 100 m leaves sharp kinks wherever the
# slice crosses a triangle edge (e.g. +11 deg to -13 deg within 200 m). Bellhop's
# Gaussian beams blow up on such kinks: on one 80 km slice, rays reflected back
# off the slope returned 27x stronger than the direct path, painting bands of
# TL < 40 dB at 50 km. Smoothing at the grid's own scale removes the kinks
# without losing features the grid actually resolves.
BATHY_SMOOTH_SIGMA_M = 300.0


@lru_cache(maxsize=1)
def load_grid():
    """Read the 150 m bathymetric grid once and cache it.

    Returns (xy, depth) where xy is an (N, 2) array of projected metres.
    """
    df = pd.read_table(
        config.GRID_FILE,
        usecols=[2, 3, 4],
        names=["Depth", "x", "y"],
        delimiter=" ",
        header=0,
    )
    xy = np.column_stack((df["x"].to_numpy(), df["y"].to_numpy()))
    return xy, df["Depth"].to_numpy()


@lru_cache(maxsize=1)
def _depth_interpolator():
    """Linear interpolator over the grid's Delaunay triangulation, built once (~1 s).

    Same triangles and values as griddata(method="linear"), but griddata
    re-triangulates on every call and SciPy's point search takes 8-16 s on
    this irregular grid; matplotlib's trapezoid-map search takes ~1 ms.
    """
    xy, depth_data = load_grid()
    tri = Delaunay(xy)
    triangulation = mtri.Triangulation(xy[:, 0], xy[:, 1], triangles=tri.simplices)
    return mtri.LinearTriInterpolator(triangulation, depth_data)


def _interpolate_depth(points):
    """Depth at each (x, y) point; NaN outside the gridded area."""
    depth = _depth_interpolator()(points[:, 0], points[:, 1])
    return np.ma.filled(depth.astype(float), np.nan)


def water_depth_at(x, y):
    """Water depth (m) at one point in local metres, or None outside the grid."""
    depth = float(_interpolate_depth(np.array([[x, y]]))[0])
    return None if np.isnan(depth) else depth


@lru_cache(maxsize=1)
def load_grid_frame():
    """Full grid as a DataFrame (lat/lon/depth/x/y) for the overview map."""
    return pd.read_csv(
        config.GRID_FILE,
        delimiter=" ",
        names=["Lat", "Long", "Depth", "x", "y"],
        header=0,
        skipinitialspace=True,
    )


def bathymetry_slice(x, y, bearing, raylength, step=BATHY_STEP_M):
    """Interpolate depth along the scenario slice, every `step` metres from the source.

    Samples sit at the same ranges whatever the slice length, so a 40 km run
    sees the same seabed over its first 10 km as a 10 km run does. A fixed
    sample count did not: 30 samples over 40 km missed features near the source.

    Returns (bathy_range_m, bathy_depth_m).
    Raises InputError if the slice leaves the gridded area.
    """
    end_x, end_y, _ = calculate_terminus_points(x, y, bearing, raylength, kind="PCS")

    bathy_range = np.arange(0.0, raylength, step)
    bathy_range = np.append(bathy_range, float(raylength))  # always end at the last receiver
    fraction = bathy_range / raylength
    line_xy = np.column_stack((x + fraction * (end_x - x), y + fraction * (end_y - y)))

    bathy_depth = _interpolate_depth(line_xy)

    if np.isnan(bathy_depth).any():
        raise InputError(
            "Insufficient bathymetry data for this scenario. "
            "Move the source inside the gridded area or shorten the range."
        )

    bathy_depth = gaussian_filter1d(bathy_depth, BATHY_SMOOTH_SIGMA_M / step, mode="nearest")
    return bathy_range, bathy_depth


def write_bty(bathy_range, bathy_depth, path=None):
    """Write the Bellhop bathymetry file. Ranges are written in km."""
    path = path or config.BTY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as btyfile:
        btyfile.write("'L'\n")
        btyfile.write(f"{len(bathy_depth)}\n")
        for r, d in zip(bathy_range, bathy_depth):
            btyfile.write(f"{r / 1000.0} {d}\n")
    return path


def prepare_bathymetry(x, y, bearing, raylength, source_depth):
    """Main function to extract the bathymetry slice and write the .bty file."""
    bathy_range, bathy_depth = bathymetry_slice(x, y, bearing, raylength)

    if source_depth > float(np.max(bathy_depth)):
        raise InputError(
            f"Source depth ({source_depth} m) cannot exceed the water depth "
            f"({float(np.max(bathy_depth)):.1f} m) along this slice."
        )

    write_bty(bathy_range, bathy_depth)
    return bathy_range, bathy_depth
