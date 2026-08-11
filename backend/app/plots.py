"""All matplotlib figures, rendered headlessly to base64 PNG.

Every function returns {"title": str, "image": "data:image/png;base64,..."} so
the React app can drop it straight into an <img src=...>.
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

DPI = 110


def _encode(fig, title, tight=True):
    """tight=False keeps the canvas at exactly figsize*dpi pixels, so a pixel
    bounding box captured before saving (see overview_map_figure) still lines
    up with the saved PNG. bbox_inches='tight' crops after the fact and would
    invalidate that mapping."""
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
        vmin=30,
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


def tl_slice_figure(tl, receiver_depth, raylength_m, source_level, ambient_level):
    """TL versus range at one receiver depth, with the figure-of-merit line."""
    row = int(round(receiver_depth))
    row = max(0, min(row, tl.shape[0] - 1))

    fig, ax = plt.subplots(figsize=(10, 5))
    slice_x = np.linspace(0, raylength_m, tl.shape[1])
    ax.plot(slice_x, [-value for value in tl[row]], label="Transmission loss")

    fom = -(source_level - ambient_level)
    ax.plot([0, raylength_m], [fom, fom], color="red", linewidth=3, label="Figure of merit")

    ax.set_xlabel("Range (m)")
    ax.set_ylabel("Transmission loss (dB)")
    ax.set_title(f"TL at {receiver_depth} metres")
    ax.legend(loc="lower left")
    ax.grid(alpha=0.3)
    return _encode(fig, f"TL at {receiver_depth} m")


@lru_cache(maxsize=1)
def _land_boundary():
    """Concave hull of the shallow (<50 m) grid points, cached -- it is slow."""
    frame = load_grid_frame()
    land_points = frame[frame["Depth"] < 50].to_numpy()
    hull = concave_hull(MultiPoint(land_points[:, 3:5]), ratio=0.2)
    xs, ys = hull.exterior.xy
    return np.asarray(xs), np.asarray(ys)


@lru_cache(maxsize=1)
def _map_extent():
    x, y = sites.boundary_local_metres()
    return (
        [float(min(x)) - 30000, float(max(x)) + 30000],
        [float(min(y)) - 30000, float(max(y)) + 30000],
    )


def overview_map_figure(x=None, y=None, bearing=None, raylength=None):
    """The bathymetry / survey-area map that used to be embedded in the tk window.

    Optionally draws the source marker and the bearing line. Also returns the
    pixel <-> data-coordinate mapping for the axes, so the frontend can turn a
    click on the <img> into an (x, y) in metres.
    """
    x_bounds, y_bounds = _map_extent()
    frame = load_grid_frame()
    frame = frame[
        (frame["x"] > x_bounds[0])
        & (frame["x"] < x_bounds[1])
        & (frame["y"] > y_bounds[0])
        & (frame["y"] < y_bounds[1])
    ]

    fig, ax = plt.subplots(figsize=(10, 8), dpi=DPI)
    ax.set_xlim(x_bounds[0] + 10000, x_bounds[1] - 10000)
    ax.set_ylim(y_bounds[0] + 10000, y_bounds[1] - 10000)
    ax.set_autoscale_on(False)

    tpc = ax.tripcolor(frame["x"], frame["y"], frame["Depth"], cmap="Blues", shading="flat")

    boundary_x, boundary_y = _land_boundary()
    ax.plot(boundary_x, boundary_y, color="black", lw=0.5)
    ax.fill(boundary_x, boundary_y, color="lightgray", alpha=0.5)

    colorbar = fig.colorbar(tpc, ax=ax, label="Depth (m)")
    colorbar.ax.invert_yaxis()

    survey_x, survey_y = sites.boundary_local_metres()
    ax.plot(survey_x, survey_y, lw=1, color="red")

    if x is not None and y is not None:
        ax.plot([x], [y], marker="+", markersize=15, mew=2, color="red")
        if bearing is not None and raylength:
            end_x, end_y, _ = calculate_terminus_points(x, y, bearing, raylength, "PCS")
            ax.plot(
                [x, end_x],
                [y, end_y],
                color="red",
                alpha=0.6,
                linestyle="dashed",
                lw=2,
            )

    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("WCFA Acoustic Modelling")
    ax.set_aspect(1, adjustable="box")

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
        "x_min": xlim[0], "x_max": xlim[1], "y_min": ylim[0], "y_max": ylim[1],
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
