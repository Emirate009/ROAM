import pandas as pd

from . import config

def create_ssp(depth_data, temperature_data):
    """Create a temporary SSP file from depth and temperature arrays.
    """
    ssp_file = config.SSP_DIR / "custom_ssp.csv"

    pressure_placeholder_values = [0] * len(depth_data)  # Placeholder for pressure values
    salinity_placeholder_values = [0] * len(depth_data)  # Placeholder for salinity values

    df = pd.DataFrame({
        "Depth": depth_data,
        "Pressure": pressure_placeholder_values,
        "Salinity": salinity_placeholder_values,
        "Temperature": temperature_data
    })

    df["Sound Speed"] = df.apply(lambda row: _calculate_sound_speed(row["Depth"], row["Temperature"]), axis=1)

    df.to_csv(ssp_file, index=False)
    return ssp_file, False

def _calculate_sound_speed(depth, temperature):
    """Calculate sound speed using the Mackenzie formula."""
    # Mackenzie formula for sound speed in seawater
    return (
        1448.96
        + 4.591 * temperature
        - 5.304e-2 * temperature**2
        + 2.374e-4 * temperature**3
        + 1.340 * (depth / 1000)
        + 1.630e-2 * (depth / 1000) * temperature
        + 1.675e-7 * (depth / 1000) * temperature**3
        - 1.025e-2 * (depth / 1000)**2
        - 7.139e-13 * (depth / 1000)**3
    )