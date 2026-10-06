import re

import numpy as np
import pandas as pd
from pyproj import Transformer


INPUT_FILES = {
    "main": "bellhop/CHS_bathy_data/NONNA100_4900N12700W.txt",
    "left": "bellhop/CHS_bathy_data/NONNA100_4900N12800W.txt",
    "upper": "bellhop/CHS_bathy_data/NONNA100_4800N12800W.txt",
    "upper_left": "bellhop/CHS_bathy_data/NONNA100_4800N12700W.txt",
}

OUTPUT_FILE = "bellhop/grid_150m_WCFR.txt"


def dms_to_decimal(dms):
    """
    Convert a DMS coordinate such as:

        49-00-03.600N
        127-45-46.800W

    to decimal degrees.
    """
    if pd.isna(dms):
        return np.nan

    value = str(dms).strip().upper()

    match = re.fullmatch(
        r"(\d{1,3})-(\d{1,2})-(\d+(?:\.\d+)?)([NSEW])",
        value,
    )

    if not match:
        return np.nan

    degrees = float(match.group(1))
    minutes = float(match.group(2))
    seconds = float(match.group(3))
    direction = match.group(4)

    if minutes >= 60 or seconds >= 60:
        return np.nan

    if direction in {"N", "S"} and degrees > 90:
        return np.nan

    if direction in {"E", "W"} and degrees > 180:
        return np.nan

    decimal = degrees + minutes / 60 + seconds / 3600

    if direction in {"S", "W"}:
        decimal *= -1

    return decimal


def load_bathymetry_file(file_path):
    """Load a CHS bathymetry file and convert its coordinates."""
    df = pd.read_csv(
        file_path,
        delimiter="\t",
        header=0,
    )

    # Remove accidental empty columns created by trailing delimiters.
    df = df.loc[
        :,
        ~df.columns.astype(str).str.startswith("Unnamed"),
    ].copy()

    required_columns = {
        "Lat (DMS)",
        "Long (DMS)",
        "Depth (m)",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"{file_path} is missing columns: "
            f"{sorted(missing_columns)}"
        )

    df = df.rename(
        columns={
            "Lat (DMS)": "Lat_DMS",
            "Long (DMS)": "Long_DMS",
            "Depth (m)": "Depth",
        }
    )

    df["Lat"] = df["Lat_DMS"].map(dms_to_decimal)
    df["Long"] = df["Long_DMS"].map(dms_to_decimal)
    df["Depth"] = pd.to_numeric(
        df["Depth"],
        errors="coerce",
    )

    df = df.replace([np.inf, -np.inf], np.nan)

    df = df.dropna(
        subset=["Lat", "Long", "Depth"]
    )

    return df


def keep_left_half(df):
    """
    Keep the western half of a dataset.

    Western longitudes are numerically smaller/more negative.
    """
    longitude_midpoint = (
        df["Long"].min() + df["Long"].max()
    ) / 2

    return df.loc[
        df["Long"] <= longitude_midpoint
    ].copy()


def keep_upper_half(df):
    """Keep the northern half of a dataset."""
    latitude_midpoint = (
        df["Lat"].min() + df["Lat"].max()
    ) / 2

    return df.loc[
        df["Lat"] <= latitude_midpoint
    ].copy()


def keep_upper_left_quarter(df):
    """Keep the northwest quarter of a dataset."""
    longitude_midpoint = (
        df["Long"].min() + df["Long"].max()
    ) / 2

    latitude_midpoint = (
        df["Lat"].min() + df["Lat"].max()
    ) / 2

    return df.loc[
        (df["Long"] <= longitude_midpoint)
        & (df["Lat"] >= latitude_midpoint)
    ].copy()


def add_local_coordinates(df):
    """
    Convert WGS84 longitude/latitude coordinates to UTM Zone 9N,
    then move the origin to the lower-left corner.
    """
    transformer = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:32609",
        always_xy=True,
    )

    x_utm, y_utm = transformer.transform(
        df["Long"].to_numpy(),
        df["Lat"].to_numpy(),
    )

    df = df.copy()

    df["x_utm"] = np.asarray(x_utm)
    df["y_utm"] = np.asarray(y_utm)

    # Make the bottom-left corner the local origin.
    df["x"] = df["x_utm"] - df["x_utm"].min()
    df["y"] = df["y_utm"] - df["y_utm"].min()

    return df


def combine_bathy_files():
    """
    Load every bathymetry tile, combine them, remove duplicate geographic
    points, and then crop the complete dataset by coordinate.
    """
    file_paths = [
        "bellhop/CHS_bathy_data/NONNA100_4900N12700W.txt",
        "bellhop/CHS_bathy_data/NONNA100_4900N12800W.txt",
        "bellhop/CHS_bathy_data/NONNA100_4800N12800W.txt",
        "bellhop/CHS_bathy_data/NONNA100_4800N12700W.txt",
    ]

    dataframes = [
        load_bathymetry_file(file_path)
        for file_path in file_paths
    ]

    df = pd.concat(
        dataframes,
        ignore_index=True,
    )

    # Remove repeated points where the source tiles overlap.
    df = df.drop_duplicates(
        subset=["Lat", "Long"],
        keep="first",
    )

    # Crop after combining the files.
    #
    # Adjust these values to match the complete area that you want plotted.
    longitude_min = -128.0
    longitude_max = -126.4
    latitude_min = 48.5
    latitude_max = 50.0

    # df = df.loc[
    #     df["Long"].between(
    #         longitude_min,
    #         longitude_max,
    #         inclusive="both",
    #     )
    #     & df["Lat"].between(
    #         latitude_min,
    #         latitude_max,
    #         inclusive="both",
    #     )
    # ].copy()

    df = df.sort_values(
        ["Lat", "Long"]
    ).reset_index(drop=True)

    return df


def process_bathymetry(df, sample_step=1):
    """
    Convert the combined geographic coordinates to projected coordinates
    and save the processed dataset.

    Use sample_step=1 initially so no bathymetry points are removed.
    """
    df = add_local_coordinates(df)

    df = df.replace(
        [np.inf, -np.inf],
        np.nan,
    )

    df = df.dropna(
        subset=[
            "Lat",
            "Long",
            "Depth",
            "x",
            "y",
        ]
    )

    # Avoid dataframe-row downsampling unless it is actually required.
    if sample_step > 1:
        print(
            "Warning: positional downsampling may produce "
            "lines and triangular interpolation artifacts."
        )

        df = df.iloc[::sample_step].copy()

    df = df.sort_values(
        ["Lat", "Long"]
    ).reset_index(drop=True)

    output_columns = [
        "Lat",
        "Long",        
        "Depth",
        "x",
        "y",
    ]

    df[output_columns].to_csv(
        OUTPUT_FILE,
        sep=" ",
        index=False,
    )

    print(f"Saved {len(df):,} bathymetry points.")
    print(
        "Longitude range:",
        df["Long"].min(),
        "to",
        df["Long"].max(),
    )
    print(
        "Latitude range:",
        df["Lat"].min(),
        "to",
        df["Lat"].max(),
    )

    return df


def main():
    combined_df = combine_bathy_files()

    # Keep every point while diagnosing the missing-data issue.
    processed_df = process_bathymetry(
        combined_df,
        sample_step=20,
    )
    longitude_counts = pd.cut(
        combined_df["Long"],
        bins=np.arange(-128.0, -126.39, 0.05),
    ).value_counts().sort_index()
    
    print(
        processed_df[
            ["Long", "Lat", "Depth"]
        ].describe()
    )
    print(
        processed_df[
            ["x", "y", "Depth"]
        ].describe()
    )

    print(longitude_counts.to_string())
    print(processed_df.shape)


if __name__ == "__main__":
    main()