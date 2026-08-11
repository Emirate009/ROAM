"""Static site data: array presets and the survey boundary polygon."""

import numpy as np
from pyproj import Transformer

from . import config

ARRAY_NAMES = [
    "Array 00", "Array 01", "Array 02", "Array 03", "Array 04",
    "Array 05", "Array 06", "Array 07", "Array 08", "Array 09",
    "Array 11", "Array 12", "Array 13", "Array 14", "Array 15",
    "Array 16", "Array 17", "Array 18", "Array 19", "Array 22",
    "Array 23", "Array 24", "Array 25", "Array 26", "Array 27",
    "Array 28", "Array 54", "Array 55", "Array 56", "Array 57",
]

# 6 columns x 7 rows of x, 6 columns x 5 rows of y, as in the original script.
# zip() below pairs them off in the same order the tkinter dropdown did.
_ARRAY_X = [
    20000, 30000, 40000, 50000, 60000, 70000,
    20000, 30000, 40000, 50000, 60000, 70000,
    20000, 30000, 40000, 50000, 60000, 70000,
    20000, 30000, 40000, 50000, 60000, 70000,
    20000, 30000, 40000, 50000, 60000, 70000,
    20000, 30000, 40000, 50000, 60000, 70000,
    20000, 30000, 40000, 50000, 60000, 70000,
]

_ARRAY_Y = [
    110000, 110000, 110000, 110000, 110000, 110000,
    120000, 120000, 120000, 120000, 120000, 120000,
    130000, 130000, 130000, 130000, 130000, 130000,
    140000, 140000, 140000, 140000, 140000, 140000,
    150000, 150000, 150000, 150000, 150000, 150000,
]

ARRAYS = [
    {"name": name, "x": float(x), "y": float(y)}
    for name, x, y in zip(ARRAY_NAMES, _ARRAY_X, _ARRAY_Y)
]

# Survey boundary, degrees.
BOUNDARY_LON = [
    -127.666667, -127.666667, -127.041667, -127.170000, -127.183333,
    -127.233333, -127.666667, -127.666667, -127.666667, -127.000000,
    -127.000000, -127.041667, -127.666667,
]
BOUNDARY_LAT = [
    49.500000, 49.250000, 49.250000, 49.410000, 49.461667,
    49.500000, 49.500000, 49.250000, 49.000000, 49.000000,
    49.205000, 49.250000, 49.250000,
]

_transformer = Transformer.from_crs(config.SOURCE_CRS, config.TARGET_CRS, always_xy=True)


def boundary_local_metres():
    """Boundary polygon in metres relative to the model origin."""
    x_utm, y_utm = _transformer.transform(BOUNDARY_LON, BOUNDARY_LAT)
    origin_x, origin_y = _transformer.transform(config.ORIGIN_LON, config.ORIGIN_LAT)
    x = np.asarray(x_utm) - origin_x
    y = np.asarray(y_utm) - origin_y
    return x, y


def local_metres_to_lonlat(x, y):
    """Inverse of the above, for SSP downloads which need lat/lon."""
    origin_x, origin_y = _transformer.transform(config.ORIGIN_LON, config.ORIGIN_LAT)
    inverse = Transformer.from_crs(config.TARGET_CRS, config.SOURCE_CRS, always_xy=True)
    lon, lat = inverse.transform(x + origin_x, y + origin_y)
    return float(lon), float(lat)
