"""
The four scenario modes, as pure functions that return plots + diagnostics.
"""

import numpy as np

from . import plots, sites
from .bathymetry import prepare_bathymetry
from .bellhop_runner import (
    IMPLAUSIBLE_MAX_FRACTION,
    implausible_tl_fraction,
    implausible_tl_warning,
    run_bellhop,
    tl_diagnostics,
)
from .environment import SWEEP_MAX_NUMBER_OF_RANGES, sweep_receiver_depth_step, write_env
from .errors import InputError, ModelError
from .geometry import calculate_terminus_points, compass_to_math_bearing
from .progress import RunProgress
from .ssp import profile_for_plot

# Bathymetry, environment, Bellhop, reading TL, plotting.
STEPS_PER_RUN = 5
# A sweep's single run: bathymetry, environment, Bellhop, reading TL; then one plot per depth.
SWEEP_SETUP_STEPS = 4


def _single_run(ssp_file, x, y, bearing, raylength, source_depth, freq, progress, label="", title="Bellhop - WG"):
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
        "warning": implausible_tl_warning(
            implausible_tl_fraction(tl, dist_km, bathy_range, bathy_depth), title
        ),
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
        "warnings": [run["warning"]] if run["warning"] else [],
        "receiver_spacing_m": round(env.receiver_depth_step, 3),
    }


def run_ranges(params, ssp_file, progress):
    """Same bearing and depth, source stepped 0 / +1 km / +2 km along track."""
    bearing = compass_to_math_bearing(params.bearing)
    figures = []
    diagnostics = []
    notes = []
    warnings = []

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
            title=f"Bellhop - WG{label}",
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
        if run["warning"]:
            warnings.append(run["warning"])

    return {"plots": figures, "diagnostics": diagnostics, "notes": notes, "warnings": warnings}


def run_depths(params, ssp_file, progress):
    """Same slice, source depth stepped by +50 m twice."""
    bearing = compass_to_math_bearing(params.bearing)
    figures = []
    diagnostics = []
    notes = []
    warnings = []

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
            title=f"Bellhop - WG @ {source_depth}m",
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
        if run["warning"]:
            warnings.append(run["warning"])

    return {"plots": figures, "diagnostics": diagnostics, "notes": notes, "warnings": warnings}


def run_sweep(params, ssp_file, progress):
    """One Bellhop run covering many source depths, rendered as frames to step through.

    Every frame is a full Bellhop solution for its depth (nothing is
    interpolated), drawn on an identical canvas so switching frames in the
    browser only moves the source and the field. The receiver grid is sized
    for the plot rather than the other modes' grid (see SWEEP_* in
    environment.py) to keep the run short.
    """
    bearing = compass_to_math_bearing(params.bearing)
    x, y = _source_metres(params)
    dist_km = params.range_m / 1000.0
    depths = np.round(
        np.linspace(params.sweep_min_depth, params.sweep_max_depth, params.sweep_count), 1
    )

    progress.step("Bathymetry")
    bathy_range, bathy_depth = prepare_bathymetry(
        x, y, bearing, params.range_m, float(depths[-1])
    )
    # The source sits at range 0, so it must be above the seabed there, not
    # just above the deepest point along the slice.
    water_depth_at_source = float(bathy_depth[0])
    if depths[-1] >= water_depth_at_source:
        raise InputError(
            f"Deepest sweep depth ({depths[-1]:g} m) must be shallower than the "
            f"water depth at the source ({water_depth_at_source:.1f} m)."
        )

    progress.step("Environment")
    deepest_bathy = float(np.max(bathy_depth))
    env_info = write_env(
        ssp_file=ssp_file,
        freq=params.frequency,
        source_depth=depths,
        dist_km=dist_km,
        deepest_bathy=deepest_bathy,
        max_ranges=SWEEP_MAX_NUMBER_OF_RANGES,
        depth_step=sweep_receiver_depth_step(dist_km, deepest_bathy),
    )
    progress.step("Bellhop")
    tl_stack, _process = run_bellhop(progress)

    empty = [f"{depth:g}" for depth, tl in zip(depths, tl_stack) if not np.isfinite(tl).any()]
    if empty:
        raise ModelError(
            f"Bellhop returned no sound field for source depth(s) {', '.join(empty)} m. "
            "A source at or very near the surface is cancelled by its reflection; "
            "start the sweep a little below the surface."
        )

    if params.receiver_depth > env_info.max_model_depth:
        raise InputError(
            f"Receiver depth ({params.receiver_depth} m) is below the deepest "
            f"modelled receiver ({env_info.max_model_depth:g} m) on this slice."
        )

    fractions = implausible_tl_fraction(tl_stack, dist_km, bathy_range, bathy_depth)
    worst = int(np.argmax(fractions))
    affected = [f"{depth:g}" for depth, f in zip(depths, fractions) if f > IMPLAUSIBLE_MAX_FRACTION]
    sweep_warning = implausible_tl_warning(
        fractions[worst], f"Source depth(s) {', '.join(affected)} m (worst at {depths[worst]:g} m)"
    )

    # One TL axis for every slice, so stepping through depths compares like with like.
    row = int(round(params.receiver_depth / env_info.receiver_depth_step))
    row = max(0, min(row, tl_stack.shape[1] - 1))
    slice_db = -tl_stack[:, row, :]
    slice_db = slice_db[np.isfinite(slice_db)]
    fom = -(params.source_level - params.ambient_level)
    slice_ylim = (
        min(float(np.percentile(slice_db, 0.5)), fom) - 5,
        max(float(np.max(slice_db)), fom) + 5,
    )

    frames = []
    for index, (depth, tl) in enumerate(zip(depths, tl_stack), start=1):
        progress.step(f"Plotting {index}/{len(depths)}")
        frames.append({
            "depth": float(depth),
            "tl": plots.transmission_loss_figure(
                f"Bellhop - WG @ {depth:g}m",
                tl,
                bathy_range,
                bathy_depth,
                depth,
                dist_km,
                tight=False,
            ),
            "tl_slice": plots.tl_slice_figure(
                tl,
                params.receiver_depth,
                env_info.receiver_depth_step,
                params.range_m,
                params.source_level,
                params.ambient_level,
                params.frequency,
                ylim=slice_ylim,
                tight=False,
            ),
        })

    return {
        "plots": [],
        "sweep_frames": frames,
        "diagnostics": tl_diagnostics(tl_stack),
        "notes": env_info.notes,
        "warnings": [sweep_warning] if sweep_warning else [],
        "receiver_spacing_m": round(env_info.receiver_depth_step, 3),
    }


def _with_progress(title, number_of_runs, mode):
    """Wrap a mode so each request draws its own progress bar in the terminal."""
    def run(params, ssp_file):
        with RunProgress(title, number_of_runs * STEPS_PER_RUN) as progress:
            return mode(params, ssp_file, progress)
    return run


def _run_sweep_with_progress(params, ssp_file):
    """Depth sweep with a progress bar: one Bellhop run, then one plot step per depth."""
    total_steps = SWEEP_SETUP_STEPS + params.sweep_count
    with RunProgress(f"Depth sweep ({params.sweep_count} source depths)", total_steps) as progress:
        return run_sweep(params, ssp_file, progress)


MODES = {
    "standard": _with_progress("Standard run", 1, run_standard),
    "ranges": _with_progress("Ranges run (3 source positions)", 3, run_ranges),
    "depths": _with_progress("Depths run (3 source depths)", 3, run_depths),
    "sweep": _run_sweep_with_progress,
}
