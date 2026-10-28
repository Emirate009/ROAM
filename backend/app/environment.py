"""Bellhop .env file generation."""

from dataclasses import dataclass

import numpy as np

from . import config
from .ssp import read_ssp

# Beam / run-type settings
RUN_TYPE = "CB"          # incoherent TL, Gaussian beams
NUMBER_OF_BEAMS = 100   # Number of beams to use
MIN_ANGLE = -89.0        # Minimum launch angle in degrees
MAX_ANGLE = 89.0         # Maximum launch angle in degrees
RAY_STEP = 0             # 0 = let Bellhop choose


@dataclass
class EnvInfo:

    max_model_depth: float
    number_receiver_depths: int
    number_of_ranges: int
    ssp_depth: list
    ssp_speed: list
    notes: list


def _fit_ssp_to_model_depth(ssp_depth, ssp_speed, max_model_depth):
    """Make the profile start at 0 m and end exactly at max_model_depth."""
    notes = []

    #Check if the first depth is greater than 0, if so, insert a new depth of 0 and the corresponding speed (avoids double zeros - Bellhop will complain if the first two depths are the same)
    if ssp_depth[0] > 0.0:
        ssp_depth = np.insert(ssp_depth, 0, 0.0)
        ssp_speed = np.insert(ssp_speed, 0, ssp_speed[0])

    max_ssp_depth = float(np.max(ssp_depth))

    if max_ssp_depth < max_model_depth:
        # Constant extrapolation from the deepest known sound speed.
        # Modelling assumption as a deeper SSP is preferable.
        notes.append(
            f"Extended SSP from {max_ssp_depth:.2f} m to {max_model_depth:.2f} m "
            f"at a constant {ssp_speed[-1]:.2f} m/s."
        )
        ssp_depth = np.append(ssp_depth, max_model_depth)
        ssp_speed = np.append(ssp_speed, ssp_speed[-1])
    elif max_ssp_depth > max_model_depth:
        #Otherwise truncate the SSP to the model depth, and interpolate the sound speed at the model depth
        keep = ssp_depth < max_model_depth
        speed_at_bottom = float(np.interp(max_model_depth, ssp_depth, ssp_speed))
        ssp_depth = np.append(ssp_depth[keep], max_model_depth)
        ssp_speed = np.append(ssp_speed[keep], speed_at_bottom)
        notes.append(f"Truncated SSP to the model depth of {max_model_depth:.2f} m.")
    else:
        #Perfect match, no changes needed
        ssp_depth[-1] = max_model_depth

    return ssp_depth, ssp_speed, notes


def write_env(ssp_file, freq, source_depth, dist_km, deepest_bathy, path=None):
    """
    Write the Bellhop environment file.

    dist_km       -- maximum receiver range in kilometres
    deepest_bathy -- deepest water depth along the slice, metres
    """
    path = path or config.ENV_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    ssp_depth, ssp_speed = read_ssp(ssp_file)

    # Small margin avoids failures from floating-point rounding.
    max_model_depth = float(np.ceil(deepest_bathy + 1.0))
    ssp_depth, ssp_speed, notes = _fit_ssp_to_model_depth(
        ssp_depth, ssp_speed, max_model_depth
    )

    number_of_ranges = int(5001)
    number_receiver_depths = int(np.ceil(max_model_depth)) + 1
    rbox = dist_km + 1.0  # computational box slightly beyond the last receiver

    with open(path, "w") as envfile:
        envfile.write("'WG profile'    ! TITLE\n")
        envfile.write(f"{freq}          ! FREQ (Hz)\n")
        envfile.write("1            ! NMEDIA\n")
        envfile.write("'CVW  '          ! SSPOPT (C-linear interpolation, flat surface)\n")
        envfile.write(f"22  0.0  {max_model_depth} ! DEPTH of bottom (m)\n")
        for depth, speed in zip(ssp_depth, ssp_speed):
            envfile.write(f" {depth} {speed} /\n")
        envfile.write("'A*' 0.0\n")
        envfile.write(f" {max_model_depth} 1600.00 1.5 0.5 /\n")
        envfile.write("1                ! NSD\n")
        envfile.write(f"{source_depth} /             ! SD(1:NSD) (m)\n")
        envfile.write(f"{number_receiver_depths}              ! NRD\n")
        envfile.write(f"0.0 {max_model_depth} /          ! RD(1:NRD) (m)\n")
        envfile.write(f"{number_of_ranges}             ! NR\n")
        envfile.write(f"0.0  {dist_km} /      ! R(1:NR) (km)\n")
        envfile.write(f"'{RUN_TYPE}'          ! Incoherent TL, Gaussian beams\n")
        envfile.write(f"{NUMBER_OF_BEAMS}     ! NBeams\n")
        envfile.write(f"{MIN_ANGLE} {MAX_ANGLE} / ! ALPHA1, ALPHA2 degrees\n")
        envfile.write(
            f"{RAY_STEP} {max_model_depth + 50} {rbox} "
            "! STEP (m), ZBOX (m), RBOX (km)\n"
        )

    return EnvInfo(
        max_model_depth=max_model_depth,
        number_receiver_depths=number_receiver_depths,
        number_of_ranges=number_of_ranges,
        ssp_depth=[float(v) for v in ssp_depth],
        ssp_speed=[float(v) for v in ssp_speed],
        notes=notes,
    )
