"""The three scenario modes, as pure functions that return plots + diagnostics.

These replace run_standard / run_ranges / run_depths, which used to read
tkinter widgets and end in plt.show().
"""

import numpy as np

from . import plots, sites
from .bathymetry import prepare_bathymetry
from .bellhop_runner import run_bellhop, tl_diagnostics
from .environment import write_env
from .errors import InputError
from .geometry import calculate_terminus_points, compass_to_math_bearing
from .ssp import profile_for_plot


def _single_run(ssp_file, x, y, bearing, raylength, source_depth, freq):
    """Bathymetry -> env -> Bellhop for one source position and depth."""
    dist_km = raylength / 1000.0
    bathy_range, bathy_depth = prepare_bathymetry(x, y, bearing, raylength, source_depth)
    env_info = write_env(
        ssp_file=ssp_file,
        freq=freq,
        source_depth=source_depth,
        dist_km=dist_km,
        deepest_bathy=float(np.max(bathy_depth)),
    )
    tl, process = run_bellhop()
    return {
        "tl": tl,
        "bathy_range": bathy_range,
        "bathy_depth": bathy_depth,
        "env": env_info,
        "dist_km": dist_km,
        "diagnostics": tl_diagnostics(tl),
        "process": process,
    }


def _source_metres(params):
    """Source lat/lon -> local metres, which the bathymetry slice works in."""
    return sites.lonlat_to_local_metres(params.lon, params.lat)


def run_standard(params, ssp_file):
    """TL heatmap + SSP profile + TL-versus-range slice at the receiver depth."""
    bearing = compass_to_math_bearing(params.bearing)
    x, y = _source_metres(params)
    run = _single_run(
        ssp_file,
        x,
        y,
        bearing,
        params.range_m,
        params.source_depth,
        params.frequency,
    )
    tl = run["tl"]

    if params.receiver_depth >= tl.shape[0]:
        raise InputError(
            f"Receiver depth ({params.receiver_depth} m) is below the deepest "
            f"modelled receiver ({tl.shape[0] - 1} m) on this slice."
        )

    ssp_depth, ssp_speed = profile_for_plot(ssp_file)

    figures = [
        plots.transmission_loss_figure(
            "Bellhop - WG",
            tl,
            run["bathy_range"],
            run["bathy_depth"],
            params.source_depth,
            run["dist_km"],
        ),
        plots.tl_slice_figure(
            tl,
            params.receiver_depth,
            params.range_m,
            params.source_level,
            params.ambient_level,
        ),
        plots.ssp_figure(ssp_depth, ssp_speed, str(ssp_file)),
    ]

    return {
        "plots": figures,
        "diagnostics": run["diagnostics"],
        "notes": run["env"].notes,
        "receiver_spacing_m": round(
            float(np.max(run["bathy_depth"])) / max(tl.shape[0] - 1, 1), 3
        ),
    }


def run_ranges(params, ssp_file):
    """Same bearing and depth, source stepped 0 / +1 km / +2 km along track."""
    bearing = compass_to_math_bearing(params.bearing)
    figures = []
    diagnostics = []
    notes = []

    x, y = _source_metres(params)
    for offset_m, label in ((0, ""), (5000, " +5km"), (10000, " +10km")):
        start_x, start_y, _ = calculate_terminus_points(
            x, y, bearing, offset_m, kind="PCS"
        )
        # The original reused a stale .env here; the env is rewritten per run so
        # the model depth matches each slice's bathymetry.
        run = _single_run(
            ssp_file,
            start_x,
            start_y,
            bearing,
            params.range_m,
            params.source_depth,
            params.frequency,
        )
        figures.append(
            plots.transmission_loss_figure(
                f"Bellhop - WG{label}",
                run["tl"],
                run["bathy_range"],
                run["bathy_depth"],
                params.source_depth,
                run["dist_km"],
            )
        )
        diagnostics.append(run["diagnostics"])
        notes.extend(run["env"].notes)

    return {"plots": figures, "diagnostics": diagnostics, "notes": notes}


def run_depths(params, ssp_file):
    """Same slice, source depth stepped by +50 m twice."""
    bearing = compass_to_math_bearing(params.bearing)
    figures = []
    diagnostics = []
    notes = []

    x, y = _source_metres(params)
    for step in (0, 50, 100):
        source_depth = params.source_depth + step
        run = _single_run(
            ssp_file,
            x,
            y,
            bearing,
            params.range_m,
            source_depth,
            params.frequency,
        )
        figures.append(
            plots.transmission_loss_figure(
                f"Bellhop - WG @ {source_depth}m",
                run["tl"],
                run["bathy_range"],
                run["bathy_depth"],
                source_depth,
                run["dist_km"],
            )
        )
        diagnostics.append(run["diagnostics"])
        notes.extend(run["env"].notes)

    return {"plots": figures, "diagnostics": diagnostics, "notes": notes}


MODES = {
    "standard": run_standard,
    "ranges": run_ranges,
    "depths": run_depths,
}
