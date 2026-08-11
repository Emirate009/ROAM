"""FastAPI entry point.

    cd backend
    uvicorn app.main:app --reload --port 8000

Run it from the `backend/` folder, with WG_DATA_ROOT pointing at the tree that
contains `bellhop/` and `ssp/`.
"""

import logging
import traceback
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app import create_ssp

from . import config, plots, scenarios, sites
from .errors import InputError, ModelError
from .schemas import ArrayPreset, RunResponse, ScenarioParams
from .ssp import delete_ssp, resolve_ssp
from .create_ssp import create_ssp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wg")

app = FastAPI(title="WG Acoustic Ranging", version="1.0.0")

# Vite dev server. The dev proxy makes requests same-origin, so this only
# matters if you point the frontend at the backend directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Starlette's default 500 is a plain-text body, which the frontend cannot
    parse as JSON ("unexpected end of data"). Always answer with JSON so the
    real error reaches the browser."""
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc().splitlines()[-8:],
        },
    )


@app.on_event("startup")
def log_paths():
    """Print the resolved paths at boot, so a misconfigured WG_DATA_ROOT is
    obvious in the terminal rather than showing up as an empty dropdown."""
    logger.info("data root      : %s", config.DATA_ROOT)
    logger.info("grid file      : %s (exists=%s)", config.GRID_FILE, config.GRID_FILE.exists())
    logger.info("bellhop exe    : %s (exists=%s)", config.BELLHOP_EXE, config.BELLHOP_EXE.exists())
    logger.info("ssp directory  : %s (exists=%s)", config.SSP_DIR, config.SSP_DIR.is_dir())
    logger.info("use wine       : %s", config.USE_WINE)
    if not config.GRID_FILE.exists():
        logger.warning("Grid file not found - the map and every run will fail. "
                       "Set WG_DATA_ROOT to the folder containing bellhop/ and ssp/.")


@app.get("/api/health")
def health():
    """Cheap reachability + configuration check. The frontend calls this on load."""
    return {
        "status": "ok",
        "data_root": str(config.DATA_ROOT),
        "grid_file": str(config.GRID_FILE),
        "grid_file_exists": config.GRID_FILE.exists(),
        "bellhop_exe": str(config.BELLHOP_EXE),
        "bellhop_exe_exists": config.BELLHOP_EXE.exists(),
        "ssp_dir": str(config.SSP_DIR),
        "ssp_dir_exists": config.SSP_DIR.is_dir(),
        "use_wine": config.USE_WINE,
    }


@app.get("/api/arrays", response_model=List[ArrayPreset])
def list_arrays():
    """Preset source positions for the dropdown. Pure static data - if this
    fails, the backend is not reachable at all."""
    return sites.ARRAYS


@app.get("/api/map")
async def overview_map(
    x: Optional[float] = Query(None),
    y: Optional[float] = Query(None),
    bearing: Optional[float] = Query(None),
    range_m: Optional[int] = Query(None),
):
    """Survey-area bathymetry map, optionally with the source and bearing line.

    The bearing is converted from compass to model convention here so the
    preview matches what the scenario will actually run.
    """
    if not config.GRID_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Bathymetry grid not found at {config.GRID_FILE}. "
                "Set WG_DATA_ROOT to the folder containing bellhop/ and ssp/."
            ),
        )

    math_bearing = None if bearing is None else 90.0 - bearing
    try:
        return await run_in_threadpool(
            plots.overview_map_figure, x, y, math_bearing, range_m
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"Grid file missing: {exc}")
    except Exception as exc:
        logger.exception("Map rendering failed")
        raise HTTPException(
            status_code=500, detail=f"Map rendering failed - {type(exc).__name__}: {exc}"
        )


@app.post("/api/run", response_model=RunResponse)
async def run_scenario(params: ScenarioParams):
    """Run one of the three scenario modes and return the rendered figures."""
    if not config.GRID_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Bathymetry grid not found at {config.GRID_FILE}.",
        )
    if not config.BELLHOP_EXE.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Bellhop executable not found at {config.BELLHOP_EXE}.",
        )

    lon = lat = None
    if params.use_current_ssp:
        lon, lat = sites.local_metres_to_lonlat(params.x, params.y)
    if params.depth_data and params.temperature_data:
        if len(params.depth_data) != len(params.temperature_data):
            raise HTTPException(
                status_code=400,
                detail="Depth and temperature arrays must be the same length.",
            )
        if len(params.depth_data) < 2:
            raise HTTPException(
                status_code=400,
                detail="At least two depth/temperature points are required.",
            )
        try:
            ssp_file, is_temporary = await run_in_threadpool(
                create_ssp, params.use_current_ssp, params.ssp_date, lat, lon
            )
        except InputError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    else: 
        try:
            ssp_file, is_temporary = await run_in_threadpool(
                resolve_ssp, params.use_current_ssp, params.ssp_date, lat, lon
            )
        except InputError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    try:
        result = await run_in_threadpool(scenarios.MODES[params.mode], params, ssp_file)
    except InputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ModelError as exc:
        logger.exception("Bellhop run failed")
        raise HTTPException(status_code=500, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Missing data file: {exc}")
    finally:
        # The tk app deleted a downloaded profile on window close; do it per run.
        if is_temporary:
            delete_ssp(ssp_file)

    return RunResponse(
        mode=params.mode,
        ssp_file=str(ssp_file),
        plots=result["plots"],
        diagnostics=result.get("diagnostics"),
        notes=result.get("notes", []),
        receiver_spacing_m=result.get("receiver_spacing_m"),
    )
