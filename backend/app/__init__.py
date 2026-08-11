"""WG acoustic ranging backend.

`bellhop.readshd` and `ocean_navigator_api_script_csv` live in the original data
tree rather than being installed packages, so make that tree importable here,
before any submodule tries to reach them.
"""

import sys

from .config import DATA_ROOT

if str(DATA_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_ROOT))
