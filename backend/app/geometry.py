"""Ray endpoint geometry."""

import numpy as np
from pyproj import Geod

_GEOD = Geod(ellps="WGS84")


def calculate_terminus_points(x, y, bearing, raylength, kind="PCS"):
    """
    End point of a ray of length `raylength` leaving (x, y) on `bearing`.

    kind="GCS" -> (x, y) are lon/lat degrees, raylength in metres, bearing is a
                  true geodesic azimuth in degrees.
    kind="PCS" -> (x, y) are projected metres, raylength in metres, bearing in
                  degrees measured counter-clockwise from +x.
    """
    if kind == "GCS":
        lon_end, lat_end, _ = _GEOD.fwd(x, y, bearing, raylength)
        return lon_end, lat_end, bearing

    theta = np.radians(bearing)
    x_end = x + raylength * np.cos(theta)
    y_end = y + raylength * np.sin(theta)
    return float(x_end), float(y_end), bearing


def compass_to_math_bearing(compass_bearing):
    """
    Convert a compass bearing (0 = north, clockwise) to the math convention
    used by calculate_terminus_points (0 = +x, counter-clockwise).
    """
    return 90.0 - float(compass_bearing)
