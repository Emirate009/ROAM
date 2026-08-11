"""Paths and runtime settings.

Everything the old script hard-coded relative to os.getcwd() lives here, so the
API can be started from any directory.  Override with environment variables.
"""

import os
import platform
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

BELLHOP_TIMEOUT_SECONDS = int(os.environ.get("WG_BELLHOP_TIMEOUT", "900"))

# UTM projection used to place the survey polygon in local metres.
SOURCE_CRS = "EPSG:4326"
TARGET_CRS = "EPSG:32609"
ORIGIN_LON = -128.0
ORIGIN_LAT = 48.0
