"""
The three scenario modes, as pure functions that return plots + diagnostics.
"""

import numpy as np

from . import plots, sites
from .bathymetry import prepare_bathymetry
from .bellhop_runner import run_bellhop, tl_diagnostics
from .environment import write_env
from .errors import InputError
from .geometry import calculate_terminus_points, compass_to_math_bearing
from .progress import RunProgress
from .ssp import profile_for_plot

# Bathymetry, environment, Bellhop, reading TL, plotting.
STEPS_PER_RUN = 5


def _single_run(ssp_file, x, y, bearing, raylength, source_depth, freq, progress, label=""):
    """Bathymetry -> env -> Bellhop for one source position and depth."""
    dist_km = raylength / 1000.0
    progress.step(f"{label}Bathymetry")
    bathy_range, bathy_depth = prepare_bathymetry(x, y, bearing, raylength, source_depth)
    progress.step(f"{label}Environment")
    env_info = write_env(
        ssp_file=ssp_file,
        freq=freq,
        source_depth=source_depth,
        dist_km=dist_km,
        deepest_bathy=float(np.max(bathy_depth)),
    )
    progress.step(f"{label}Bellhop")
    tl, process = run_bellhop(progress, label)
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


def run_standard(params, ssp_file, progress):
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
        progress,
    )
    tl = run["tl"]
    env = run["env"]

    if params.receiver_depth > env.max_model_depth:
        raise InputError(
            f"Receiver depth ({params.receiver_depth} m) is below the deepest "
            f"modelled receiver ({env.max_model_depth:g} m) on this slice."
        )

    progress.step("Plotting")
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
            env.receiver_depth_step,
            params.range_m,
            params.source_level,
            params.ambient_level,
            params.frequency,
        ),
        plots.ssp_figure(ssp_depth, ssp_speed, str(ssp_file)),
    ]

    return {
        "plots": figures,
        "diagnostics": run["diagnostics"],
        "notes": env.notes,
        "receiver_spacing_m": round(env.receiver_depth_step, 3),
    }


def run_ranges(params, ssp_file, progress):
    """Same bearing and depth, source stepped 0 / +1 km / +2 km along track."""
    bearing = compass_to_math_bearing(params.bearing)
    figures = []
    diagnostics = []
    notes = []

    x, y = _source_metres(params)
    offsets = ((0, ""), (5000, " +5km"), (10000, " +10km"))
    for index, (offset_m, label) in enumerate(offsets, start=1):
        run_label = f"Run {index}/{len(offsets)}: "
        start_x, start_y, _ = calculate_terminus_points(
            x, y, bearing, offset_m, kind="PCS"
        )
        # The env is rewritten per run so the model depth matches each slice's bathymetry.
        run = _single_run(
            ssp_file,
            start_x,
            start_y,
            bearing,
            params.range_m,
            params.source_depth,
            params.frequency,
            progress,
            run_label,
        )
        progress.step(f"{run_label}Plotting")
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


def run_depths(params, ssp_file, progress):
    """Same slice, source depth stepped by +50 m twice."""
    bearing = compass_to_math_bearing(params.bearing)
    figures = []
    diagnostics = []
    notes = []

    x, y = _source_metres(params)
    steps = (0, 50, 100)
    for index, step in enumerate(steps, start=1):
        run_label = f"Run {index}/{len(steps)}: "
        source_depth = params.source_depth + step
        run = _single_run(
            ssp_file,
            x,
            y,
            bearing,
            params.range_m,
            source_depth,
            params.frequency,
            progress,
            run_label,
        )
        progress.step(f"{run_label}Plotting")
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


def _with_progress(title, number_of_runs, mode):
    """Wrap a mode so each request draws its own progress bar in the terminal."""
    def run(params, ssp_file):
        with RunProgress(title, number_of_runs * STEPS_PER_RUN) as progress:
            return mode(params, ssp_file, progress)
    return run


MODES = {
    "standard": _with_progress("Standard run", 1, run_standard),
    "ranges": _with_progress("Ranges run (3 source positions)", 3, run_ranges),
    "depths": _with_progress("Depths run (3 source depths)", 3, run_depths),
}
