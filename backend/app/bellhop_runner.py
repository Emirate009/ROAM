"""Run the Bellhop executable and turn its shade file into transmission loss."""

import subprocess
import sys
import threading

import numpy as np

from . import config
from .errors import ModelError

# Bellhop reads and writes fixed filenames, so only one run at a time.
BELLHOP_LOCK = threading.Lock()

# `bellhop.readshd` lives next to the data tree in the original layout.
if str(config.DATA_ROOT) not in sys.path:
    sys.path.insert(0, str(config.DATA_ROOT))

from bellhop.readshd import readshd  # noqa: E402


def _readshd(*args, **kwargs):
    return readshd(*args, **kwargs)


def tl_diagnostics(tl):
    """Summary stats that used to be printed to the terminal."""
    finite = np.asarray(tl)[np.isfinite(tl)]
    if finite.size == 0:
        raise ModelError("Transmission loss contains no finite values.")

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


def run_bellhop():
    """Execute Bellhop on the current WG_.env / WG_.bty and return the TL array.

    Unlike the original, this never calls os.chdir on the process; the working
    directory is passed to the subprocess instead, which is safe under a server
    handling concurrent requests.
    """
    with BELLHOP_LOCK:
        if config.SHD_FILE.exists():
            config.SHD_FILE.unlink()

        command = [str(config.BELLHOP_EXE), config.ENV_STEM]
        if config.USE_WINE:
            command.insert(0, "wine")

        try:
            result = subprocess.run(
                command,
                cwd=str(config.BELLHOP_DIR),
                text=True,
                capture_output=True,
                timeout=config.BELLHOP_TIMEOUT_SECONDS,
            )
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

        pressure, _geometry = _readshd(str(config.SHD_FILE), np.nan, np.nan, np.nan)

    p = np.squeeze(pressure, axis=(0, 1))
    p = np.where(p == 0, np.nan, p)
    with np.errstate(divide="ignore", invalid="ignore"):
        tl = -20 * np.log10(np.abs(p))

    return tl, {"stdout": result.stdout, "stderr": result.stderr}
