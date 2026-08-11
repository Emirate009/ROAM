import os
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .errors import InputError

def create_ssp(use_current, date_string, lat=None, lon=None):
    """Return a path to an SSP file, either from the archive or fetched from
    Ocean Navigator. If fetched, the file is written to a temporary location
    and should be deleted after use.
    """
    if use_current:
        if lat is None or lon is None:
            raise InputError("Current SSP requires a source position.")
        return fetch_current_ssp(lat, lon), True
    return determine_ssp(date_string), False