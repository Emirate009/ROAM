"""Request/response models. Validation that used to be scattered through the
tkinter callbacks now happens here, before any file is written."""

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ScenarioParams(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Source latitude, degrees")
    lon: float = Field(..., ge=-180, le=180, description="Source longitude, degrees")
    bearing: float = Field(..., ge=0, le=360, description="Compass bearing, degrees")

    frequency: int = Field(7500, gt=0, description="Hz")
    source_depth: int = Field(200, ge=0, description="metres")
    receiver_depth: int = Field(200, ge=0, description="metres")
    source_level: int = Field(135, description="dB")
    ambient_level: int = Field(70, description="dB")
    range_m: int = Field(5000, gt=0, description="Ray length in metres")

    mode: Literal["standard", "ranges", "depths"] = "standard"

    use_current_ssp: bool = False
    ssp_date: Optional[str] = Field("20230619", description="yyyymmdd")

    depth_data: Optional[List[float]] = Field(
        default_factory=list, description="Manual SSP override: depths in metres"
    )
    temperature_data: Optional[List[float]] = Field(
        default_factory=list, description="Manual SSP override: temperature in °C, same length as depth_data"
    )

    @model_validator(mode="after")
    def _check_ssp(self):
        if not self.use_current_ssp and not (self.depth_data and self.temperature_data):
            if not self.ssp_date or len(self.ssp_date) != 8 or not self.ssp_date.isdigit():
                raise ValueError("ssp_date must be 8 digits in yyyymmdd form.")

        if self.depth_data and any(
            b <= a for a, b in zip(self.depth_data, self.depth_data[1:])
        ):
            # Bellhop rejects a non-increasing SSP with a raw crash dump; catch
            # it here so the error is legible instead.
            raise ValueError("depth_data must be strictly increasing.")

        return self


class Figure(BaseModel):
    title: str
    image: str


class RunResponse(BaseModel):
    mode: str
    ssp_file: str
    plots: List[Figure]
    diagnostics: Any = None
    notes: List[str] = []
    receiver_spacing_m: Optional[float] = None


class ArrayPreset(BaseModel):
    name: str
    lat: float
    lon: float
