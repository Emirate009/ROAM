"""Bathymetry slice extraction and .bty file writing."""

from functools import lru_cache

import matplotlib.tri as mtri
import numpy as np
import pandas as pd
from scipy.spatial import Delaunay

from . import config
from .errors import InputError
from .geometry import calculate_terminus_points

RESOLUTION = 30  # number of samples along the slice


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


def bathymetry_slice(x, y, bearing, raylength, resolution=RESOLUTION):
    """Interpolate depth along the scenario slice.

    Returns (bathy_range_m, bathy_depth_m), both length `resolution`.
    Raises InputError if the slice leaves the gridded area.
    """
    end_x, end_y, _ = calculate_terminus_points(x, y, bearing, raylength, kind="PCS")

    # linspace instead of arange: guarantees exactly `resolution` samples and
    # avoids zero-step / mismatched-length special cases
    x_line = np.linspace(x, end_x, resolution)
    y_line = np.linspace(y, end_y, resolution)
    line_xy = np.column_stack((x_line, y_line))

    bathy_depth = _interpolate_depth(line_xy)

    if np.isnan(bathy_depth).any():
        raise InputError(
            "Insufficient bathymetry data for this scenario. "
            "Move the source inside the gridded area or shorten the range."
        )

    bathy_range = np.linspace(0.0, raylength, resolution)
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
