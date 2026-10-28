"""All matplotlib figures, rendered headlessly to base64 PNG.
"""

import base64
import io
from functools import lru_cache

import matplotlib

matplotlib.use("Agg")  # no GUI backend on a server

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from shapely import MultiPoint, concave_hull  # noqa: E402

from . import sites  # noqa: E402
from .bathymetry import load_grid_frame  # noqa: E402
from .geometry import calculate_terminus_points  # noqa: E402
from scipy.ndimage import uniform_filter1d

DPI = 110


def _encode(fig, title, tight=True):
    """
    tight=False keeps the canvas at exactly figsize*dpi pixels, so a pixel
    bounding box captured before saving (see overview_map_figure) still lines
    up with the saved PNG. bbox_inches='tight' crops after the fact and would
    invalidate that mapping.
    """
    buffer = io.BytesIO()
    kwargs = {"format": "png", "dpi": DPI}
    if tight:
        kwargs["bbox_inches"] = "tight"
    fig.savefig(buffer, **kwargs)
    plt.close(fig)
    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode("ascii")
    return {"title": title, "image": f"data:image/png;base64,{encoded}"}


def transmission_loss_figure(title, tl, bathy_range, bathy_depth, source_depth, dist_km):
    fig, ax = plt.subplots(figsize=(12, 6))

    deepest_model_depth = int(np.ceil(max(bathy_depth) + 1))
    range_m = dist_km * 1000.0

    image = ax.imshow(
        tl,
        vmin=40,
        vmax=90,
        cmap="jet_r",
        aspect="auto",
        extent=[0, range_m, deepest_model_depth, 0],
    )
    ax.fill_between(bathy_range, bathy_depth, deepest_model_depth, color="0.4")
    fig.colorbar(image, ax=ax, label="Transmission loss (dB)")
    ax.plot(0, source_depth, marker="<", markersize=16, color="k")
    ax.set_xlim(0, range_m)
    ax.set_ylim(deepest_model_depth, 0)
    ax.set_xlabel("Range (m)")
    ax.set_ylabel("Depth (m)")
    ax.set_title(title)

    return _encode(fig, title)


def ssp_figure(ssp_depth, ssp_speed, label):
    fig, ax = plt.subplots(figsize=(5, 7))
    ax.plot(ssp_speed, [-d for d in ssp_depth])
    ax.set_xlabel("Sound speed (m/s)")
    ax.set_ylabel("Depth (m)")
    ax.set_title(f"SSP: {label}")
    ax.grid(alpha=0.3)
    return _encode(fig, f"SSP: {label}")


def tl_slice_figure(tl, receiver_depth, receiver_depth_step, raylength_m, source_level, ambient_level, frequency):
    """TL versus range at one receiver depth, with the figure-of-merit line."""
    row = int(round(receiver_depth / receiver_depth_step))
    row = max(0, min(row, tl.shape[0] - 1))

    tl_db = [-value for value in tl[row]]

    fig, ax = plt.subplots(figsize=(10, 5))
    slice_x = np.linspace(0, raylength_m, tl.shape[1])

    fom = -(source_level - ambient_level)

    # Average the TL curve to reduce noise and get a more stable figure-of-merit.
    spacing = np.median(np.diff(slice_x))
    window = max(1, round(50 / spacing))

    tl_db_smooth = -np.asarray(tl[row], dtype=float)

    valid = np.isfinite(tl_db_smooth)

    tl_db_smooth[~valid] = np.interp(
        slice_x[~valid],
        slice_x[valid],
        tl_db_smooth[valid]
    )

    smoothed_tl = uniform_filter1d(
        tl_db_smooth,
        size=window,
    )

    smoothed_detected = smoothed_tl >= fom

    # Farthest detectable point after smoothing
    smoothed_indices = np.where(smoothed_detected)[0]
    smoothed_range = (
        slice_x[smoothed_indices[-1]]
        if len(smoothed_indices) else np.nan
    )

    ax.plot(slice_x, tl_db, label="Transmission Loss")
    ax.plot(slice_x, smoothed_tl, label=f"Smoothed Transmission Loss", color="orange")
    ax.plot([0, raylength_m], [fom, fom], color="red", label=f"Figure of Merit: {fom:.1f} dB")
    ax.plot([smoothed_range], [fom], 'ro', markersize=6, label=f"Detectable Range: {smoothed_range:.1f} m")

    ax.set_xlabel("Range (m)")
    ax.set_ylabel("Transmission loss (dB)")
    ax.set_title(f"TL at {receiver_depth} metres and {frequency} Hz")
    ax.legend(loc="lower left")
    ax.grid(alpha=0.3)
    return _encode(fig, f"TL at {receiver_depth} m")


@lru_cache(maxsize=1)
def _land_boundary():
    """Concave hull of the shallow (<50 m) grid points in lon/lat, cached -- it is slow."""
    frame = load_grid_frame()
    land_points = frame.loc[frame["Depth"] < 50, ["Long", "Lat"]].to_numpy()
    hull = concave_hull(MultiPoint(land_points), ratio=0.2)
    lons, lats = hull.exterior.xy
    return np.asarray(lons), np.asarray(lats)


# Map padding around the survey boundary, in degrees (~20 km each way at 49N).
MAP_PAD_LON = 0.3
MAP_PAD_LAT = 0.2


def _map_extent():
    """Lon/lat axis limits: the survey boundary plus MAP_PAD_LON / MAP_PAD_LAT."""
    lon_lims = [min(sites.BOUNDARY_LON) - MAP_PAD_LON, max(sites.BOUNDARY_LON) + MAP_PAD_LON]
    lat_lims = [min(sites.BOUNDARY_LAT) - MAP_PAD_LAT, max(sites.BOUNDARY_LAT) + MAP_PAD_LAT]
    return lon_lims, lat_lims


def overview_map_figure(lat=None, lon=None, bearing=None, raylength=None):
    """
    The bathymetry / survey-area map in lon/lat, optionally with the source
    and bearing line.

    The source is plotted directly. The bearing-line end point is computed in
    local metres, the same way the bathymetry slice is, so the preview line
    matches the slice the model actually uses.
    """
    lon_lims, lat_lims = _map_extent()
    frame = load_grid_frame()
    # Keep a little grid beyond the axes so the triangulation reaches the edges.
    frame = frame[
        (frame["Long"] > lon_lims[0] - MAP_PAD_LON / 2)
        & (frame["Long"] < lon_lims[1] + MAP_PAD_LON / 2)
        & (frame["Lat"] > lat_lims[0] - MAP_PAD_LAT / 2)
        & (frame["Lat"] < lat_lims[1] + MAP_PAD_LAT / 2)
    ]

    fig, ax = plt.subplots(figsize=(10, 8), dpi=DPI)
    ax.set_xlim(*lon_lims)
    ax.set_ylim(*lat_lims)
    ax.set_autoscale_on(False)

    tpc = ax.tripcolor(frame["Long"], frame["Lat"], frame["Depth"], cmap="Blues", shading="flat")

    boundary_lon, boundary_lat = _land_boundary()
    ax.plot(boundary_lon, boundary_lat, color="black", lw=0.5)
    ax.fill(boundary_lon, boundary_lat, color="lightgray", alpha=0.5)

    colorbar = fig.colorbar(tpc, ax=ax, label="Depth (m)")
    colorbar.ax.invert_yaxis()

    ax.plot(sites.BOUNDARY_LON, sites.BOUNDARY_LAT, lw=1, color="red")

    if lat is not None and lon is not None:
        ax.plot([lon], [lat], marker="+", markersize=15, mew=2, color="red")
        if bearing is not None and raylength:
            x, y = sites.lonlat_to_local_metres(lon, lat)
            end_x, end_y, _ = calculate_terminus_points(x, y, bearing, raylength, "PCS")
            end_lon, end_lat = sites.local_metres_to_lonlat(end_x, end_y)
            ax.plot(
                [lon, end_lon],
                [lat, end_lat],
                color="red",
                alpha=0.6,
                linestyle="dashed",
                lw=2,
            )

    ax.set_xlabel("Longitude (°)")
    ax.set_ylabel("Latitude (°)")
    ax.set_title("WCFA Acoustic Modelling")
    # Equal ground distance per degree at the map's mid-latitude.
    ax.set_aspect(1 / np.cos(np.radians(np.mean(lat_lims))), adjustable="box")

    fig.tight_layout()
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axes_bbox = ax.get_window_extent(renderer=renderer)
    fig_width_px, fig_height_px = fig.canvas.get_width_height()
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()

    result = _encode(fig, "Survey area", tight=False)
    result["image_size"] = {"width": fig_width_px, "height": fig_height_px}
    result["data_bounds"] = {
        "lon_min": float(xlim[0]), "lon_max": float(xlim[1]),
        "lat_min": float(ylim[0]), "lat_max": float(ylim[1]),
    }
    # Pixel box of the plotted axes within the PNG, top-left origin (matches
    # the coordinate system a browser reports from a click on an <img>).
    result["pixel_bounds"] = {
        "left": float(axes_bbox.x0),
        "right": float(axes_bbox.x1),
        "top": float(fig_height_px - axes_bbox.y1),
        "bottom": float(fig_height_px - axes_bbox.y0),
    }
    return result
