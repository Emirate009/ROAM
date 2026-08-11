"""Request/response models. Validation that used to be scattered through the
tkinter callbacks now happens here, before any file is written."""

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ScenarioParams(BaseModel):
    x: float = Field(..., description="Source easting in local metres")
    y: float = Field(..., description="Source northing in local metres")
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

    @model_validator(mode="after")
    def _check_ssp(self):
        if not self.use_current_ssp:
            if not self.ssp_date or len(self.ssp_date) != 8 or not self.ssp_date.isdigit():
                raise ValueError("ssp_date must be 8 digits in yyyymmdd form.")
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
    x: float
    y: float
