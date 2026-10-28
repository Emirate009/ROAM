"""Bellhop .env file generation."""

from dataclasses import dataclass

import numpy as np

from . import config
from .ssp import read_ssp

# Beam / run-type settings
RUN_TYPE = "CB"          # incoherent TL, Gaussian beams
NUMBER_OF_BEAMS = 0   # Number of beams to use (0 = Bellhop's automatic choice, capped at MAX_BEAMS)
MAX_BEAMS = 1000         # Bellhop's automatic choice grows with range x frequency
MIN_ANGLE = -89.0        # Minimum launch angle in degrees
MAX_ANGLE = 89.0         # Maximum launch angle in degrees
RAY_STEP = 0             # 0 = let Bellhop choose

# Receiver grid. Bellhop's run time scales with (receiver ranges x depths x beams),
# so the grid is capped rather than fixed at 1 m spacing: 1 m spacing at 10 km
# gave 25M receivers and an ~8 min run; at 50 km it would take hours.
MAX_NUMBER_OF_RANGES = 2001     # 1 m spacing up to 2 km, coarser beyond
RECEIVER_DEPTH_STEP_M = 10.0    # target receiver depth spacing


@dataclass
class EnvInfo:

    max_model_depth: float
    number_receiver_depths: int
    receiver_depth_step: float
    number_of_ranges: int
    number_of_beams: int
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


def _number_of_beams(dist_km, freq):
    """NUMBER_OF_BEAMS, or Bellhop's own automatic choice capped at MAX_BEAMS."""
    if NUMBER_OF_BEAMS > 0:
        return NUMBER_OF_BEAMS
    # Bellhop's rule for NBeams = 0, with a nominal 1500 m/s sound speed.
    automatic = max(int(0.3 * dist_km * 1000.0 * freq / 1500.0), 300)
    return min(automatic, MAX_BEAMS)


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

    # One receiver range per metre, up to MAX_NUMBER_OF_RANGES.
    number_of_ranges = min(int(round(dist_km * 1000)) + 1, MAX_NUMBER_OF_RANGES)
    # Receivers evenly spaced from 0 m to the model depth, about RECEIVER_DEPTH_STEP_M apart.
    number_receiver_depths = int(np.ceil(max_model_depth / RECEIVER_DEPTH_STEP_M)) + 1
    receiver_depth_step = max_model_depth / (number_receiver_depths - 1)
    number_of_beams = _number_of_beams(dist_km, freq)
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
        envfile.write(f"{number_of_beams}     ! NBeams\n")
        envfile.write(f"{MIN_ANGLE} {MAX_ANGLE} / ! ALPHA1, ALPHA2 degrees\n")
        envfile.write(
            f"{RAY_STEP} {max_model_depth + 50} {rbox} "
            "! STEP (m), ZBOX (m), RBOX (km)\n"
        )

    return EnvInfo(
        max_model_depth=max_model_depth,
        number_receiver_depths=number_receiver_depths,
        receiver_depth_step=receiver_depth_step,
        number_of_ranges=number_of_ranges,
        number_of_beams=number_of_beams,
        ssp_depth=[float(v) for v in ssp_depth],
        ssp_speed=[float(v) for v in ssp_speed],
        notes=notes,
    )
