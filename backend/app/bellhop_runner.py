"""Run the Bellhop executable and turn its shade file into transmission loss."""

import subprocess
import sys
import threading
import time

import numpy as np

from . import config
from .errors import ModelError

# Bellhop reads and writes fixed filenames, so only one run at a time.
BELLHOP_LOCK = threading.Lock()

# `bellhop.readshd` lives next to the data tree
if str(config.DATA_ROOT) not in sys.path:
    sys.path.insert(0, str(config.DATA_ROOT))

from bellhop.readshd import readshd  # noqa: E402


def _readshd(*args, **kwargs):
    return readshd(*args, **kwargs)


# Spreading sets a floor on TL: spherical, 20 log10(r), out to about one water
# depth H, then cylindrical, 20 log10(H) + 10 log10(r/H), once the sound is
# trapped between surface and seabed. Focusing (e.g. a convergence zone) can
# beat that floor by several dB, but not by 20 dB across a sizeable part of the
# field. When it does, Bellhop has mis-traced beams: an 80 km run over a kinked
# seabed had 41% of its receivers past this bound, while clean runs stay well
# under 1%.
IMPLAUSIBLE_MARGIN_DB = 20.0
IMPLAUSIBLE_MIN_RANGE_M = 1000.0   # the near field is not spreading limited
IMPLAUSIBLE_MAX_FRACTION = 0.01


def implausible_tl_fraction(tl, dist_km, bathy_range, bathy_depth):
    """Fraction of receivers beyond 1 km whose TL is implausibly low.

    tl is (depth, range) or (source depth, depth, range); for a stack the
    result has one value per source depth. The water depth used for the
    cylindrical part is the shallowest seen so far along the slice, which
    gives the most lenient (lowest) floor.
    """
    tl = np.asarray(tl)
    ranges = np.linspace(0.0, dist_km * 1000.0, tl.shape[-1])
    far = ranges >= IMPLAUSIBLE_MIN_RANGE_M
    r = ranges[far]
    water_depth = np.minimum.accumulate(np.interp(ranges, bathy_range, bathy_depth))[far]
    h = np.maximum(water_depth, 1.0)
    floor = 20.0 * np.log10(np.minimum(r, h)) + 10.0 * np.log10(np.maximum(r, h) / h)

    field = tl[..., far]
    finite = np.isfinite(field)
    implausible = (field < floor - IMPLAUSIBLE_MARGIN_DB) & finite
    with np.errstate(invalid="ignore", divide="ignore"):
        fraction = implausible.sum(axis=(-2, -1)) / finite.sum(axis=(-2, -1))
    return np.nan_to_num(fraction)


def implausible_tl_warning(fraction, where):
    """A warning for the results page, or None if the field looks physical."""
    if fraction <= IMPLAUSIBLE_MAX_FRACTION:
        return None
    return (
        f"{where}: {fraction:.0%} of the field beyond 1 km has transmission loss more than "
        f"{IMPLAUSIBLE_MARGIN_DB:g} dB below what spreading alone allows, which is not "
        "physically possible. Bellhop has probably mis-traced some beams (a sharp seabed feature is the "
        "usual cause), so treat this plot as unreliable."
    )


def tl_diagnostics(tl):
    """Summary stats that used to be printed to the terminal."""
    finite = np.asarray(tl)[np.isfinite(tl)]
    if finite.size == 0:
        raise ModelError("Transmission loss contains no finite values. Check input parameters are valid for given environment")

    levels = [0, 1, 5, 25, 50, 75, 95, 99, 100]
    values = np.percentile(finite, levels)

    return {
        "shape": list(np.shape(tl)),
        "finite_values": int(finite.size),
        "nan_count": int(np.isnan(tl).sum()),
        "inf_count": int(np.isinf(tl).sum()),
        "percentiles": {f"p{lvl}": round(float(v), 2) for lvl, v in zip(levels, values)},
        "fraction_at_or_above_80db": round(float(np.mean(finite >= 80.0)), 4),
    }


def _run_with_progress(command, progress):
    """subprocess.run equivalent that redraws the progress bar about once a second."""
    process = subprocess.Popen(
        command,
        cwd=str(config.BELLHOP_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + config.BELLHOP_TIMEOUT_SECONDS
    while True:
        try:
            stdout, stderr = process.communicate(timeout=1)
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            if time.monotonic() > deadline:
                process.kill()
                process.communicate()
                raise
            if progress is not None:
                progress.refresh()


def run_bellhop(progress=None, label=""):
    """Execute Bellhop on the current WG_.env / WG_.bty and return the TL array.

    The array is (depth, range) for a single source depth, or
    (source depth, depth, range) when the .env lists several.

    This never calls os.chdir on the process; the working
    directory is passed to the subprocess instead, which is safe under a server
    handling concurrent requests.
    """
    with BELLHOP_LOCK:
        if config.SHD_FILE.exists():
            config.SHD_FILE.unlink()

        command = [str(config.BELLHOP_EXE), config.ENV_STEM]

        # For running on MAC
        if config.USE_WINE:
            command.insert(0, "wine")

        try:
            result = _run_with_progress(command, progress)
        except FileNotFoundError as exc:
            raise ModelError(f"Could not launch Bellhop ({command[0]}): {exc}")
        except subprocess.TimeoutExpired:
            raise ModelError(
                f"Bellhop timed out after {config.BELLHOP_TIMEOUT_SECONDS} s."
            )

        if result.returncode != 0:
            raise ModelError(
                "Bellhop failed.\n\n"
                f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
            )

        if not config.SHD_FILE.exists():
            raise ModelError(
                "Bellhop finished without creating WG_.shd. Check that the run "
                "type is a transmission-loss mode such as 'CB'."
            )

        if progress is not None:
            progress.step(f"{label}Reading TL")
        pressure, _geometry = _readshd(str(config.SHD_FILE), np.nan, np.nan, np.nan)

    p = pressure[0]  # single bearing
    if p.shape[0] == 1:
        p = p[0]
    p = np.where(p == 0, np.nan, p)
    with np.errstate(divide="ignore", invalid="ignore"):
        tl = -20 * np.log10(np.abs(p))

    return tl, {"stdout": result.stdout, "stderr": result.stderr}
