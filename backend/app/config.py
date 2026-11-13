"""Paths and runtime settings.

Everything the old script hard-coded relative to os.getcwd() lives here, so the
API can be started from any directory.  Override with environment variables.
"""

import os
import platform
from dataclasses import dataclass
from pathlib import Path

# Root of your existing data tree: the folder that contains `bellhop/` and `ssp/`.
# Defaults to the repo root (two levels up from this file).
DATA_ROOT = Path(os.environ.get("WG_DATA_ROOT", Path(__file__).resolve().parents[2]))

BELLHOP_DIR = Path(os.environ.get("WG_BELLHOP_DIR", DATA_ROOT / "bellhop"))
SSP_DIR = Path(os.environ.get("WG_SSP_DIR", DATA_ROOT / "ssp" / "ctd"))

GRID_FILE = Path(os.environ.get("WG_GRID_FILE", BELLHOP_DIR / "grid_150m_WCFR.txt"))
BELLHOP_EXE = Path(os.environ.get("WG_BELLHOP_EXE", BELLHOP_DIR / "bellhop.exe"))

# Bellhop reads/writes these fixed filenames inside BELLHOP_DIR.
ENV_STEM = "WG_"
ENV_FILE = BELLHOP_DIR / f"{ENV_STEM}.env"
BTY_FILE = BELLHOP_DIR / f"{ENV_STEM}.bty"
SHD_FILE = BELLHOP_DIR / f"{ENV_STEM}.shd"

# A Windows .exe on a non-Windows host needs wine. Set WG_USE_WINE=0/1 to force.
_use_wine_env = os.environ.get("WG_USE_WINE")
if _use_wine_env is None:
    USE_WINE = BELLHOP_EXE.suffix.lower() == ".exe" and platform.system() != "Windows"
else:
    USE_WINE = _use_wine_env not in ("0", "false", "False", "")

# Porter's original Fortran BELLHOP (Acoustics Toolbox), the default engine.
# Defaults to the build in the `at` folder next to this repo, which is
# a native macOS binary despite its .exe name, so it runs without wine.
PORTER_BELLHOP_EXE = Path(
    os.environ.get("WG_PORTER_BELLHOP_EXE", DATA_ROOT.parent / "at" / "bin" / "bellhop.exe")
)


def is_windows_exe(path):
    """True for a Windows (PE) program, which needs wine off Windows; False for a native one."""
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"MZ"
    except OSError:
        return False


@dataclass(frozen=True)
class Engine:
    label: str
    exe: Path
    use_wine: bool
    bathy_smooth_sigma_m: float   # Gaussian smoothing of the seabed slice, metres (0 = none)


# The bathymetry slice is sampled off a triangulated grid, so it has kinks
# wherever it crosses a triangle edge (up to ~11 deg on a 50 km slice).
# bellhopcxx mis-traces beams off those kinks and needs ~600 m of smoothing to
# stay clean: on a 50-depth, 50 km sweep it flagged 19 depths at 300 m and none
# at 600 m. Porter's BELLHOP flagged nothing on three 40-50 km slices even
# unsmoothed, so it keeps the seabed exactly as the grid gives it. bellhopcxx
# is the optional fast mode (about 3.5x quicker on a 50-depth sweep).
ENGINES = {
    "bellhop": Engine(
        "Bellhop",
        PORTER_BELLHOP_EXE,
        is_windows_exe(PORTER_BELLHOP_EXE) and platform.system() != "Windows",
        0.0,
    ),
    "fast": Engine("Fast mode (bellhopcxx)", BELLHOP_EXE, USE_WINE, 600.0),
}
DEFAULT_ENGINE = "bellhop"

BELLHOP_TIMEOUT_SECONDS = int(os.environ.get("WG_BELLHOP_TIMEOUT", "900"))

# UTM projection used to place the survey polygon in local metres.
SOURCE_CRS = "EPSG:4326"
TARGET_CRS = "EPSG:32609"
ORIGIN_LON = -128.0
ORIGIN_LAT = 48.0
