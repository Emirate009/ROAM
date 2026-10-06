import pandas as pd

from . import config

# Salinity isn't collected from the manual/upload input, so assume standard
# open-ocean salinity (35 ppt) -- this zeroes out the formula's salinity terms.
STANDARD_SALINITY = 35.0

def create_ssp(depth_data, temperature_data):
    """Create a temporary SSP file from depth and temperature arrays.
    """
    ssp_file = config.SSP_DIR / "custom_ssp.csv"

    pressure_placeholder_values = [0] * len(depth_data)  # Placeholder for pressure values
    salinity_values = [STANDARD_SALINITY] * len(depth_data)

    df = pd.DataFrame({
        "Depth": depth_data,
        "Pressure": pressure_placeholder_values,
        "Salinity": salinity_values,
        "Temperature": temperature_data
    })

    df["Sound Speed"] = df.apply(
        lambda row: _calculate_sound_speed(row["Depth"], row["Temperature"], row["Salinity"]), axis=1
    )

    df.to_csv(ssp_file, index=False)
    return ssp_file, False

def _calculate_sound_speed(depth, temperature, salinity=STANDARD_SALINITY):
    """Calculate sound speed using the Mackenzie (1981) formula.

    depth in metres, temperature in degrees C, salinity in ppt.
    """
    return (
        1448.96
        + 4.591 * temperature
        - 5.304e-2 * temperature**2
        + 2.374e-4 * temperature**3
        + 1.340 * (salinity - 35)
        + 1.630e-2 * depth
        + 1.675e-7 * depth**2
        - 1.025e-2 * temperature * (salinity - 35)
        - 7.139e-13 * temperature * depth**3
    )