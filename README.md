# WG Acoustic Ranging — FastAPI + React

The tkinter app, split into a FastAPI backend that does all the Bellhop work and
a thin React frontend that submits a form and displays the resulting figures.
Plotting is still matplotlib: figures are rendered headlessly with the `Agg`
backend and returned as base64 PNGs, so the plots look exactly as they did.

## Layout

```
backend/
  requirements.txt
  app/
    config.py          paths + runtime settings (env-var overridable)
    errors.py          InputError -> HTTP 400, ModelError -> HTTP 500
    geometry.py        calculate_terminus_points, bearing conversion
    bathymetry.py      grid loading (cached), slice interpolation, .bty writing
    environment.py     .env writing + SSP fitting to model depth
    ssp.py             SSP selection / download / reading
    bellhop_runner.py  subprocess call + shade file -> TL + diagnostics
    plots.py           every matplotlib figure -> base64 PNG
    scenarios.py       standard / ranges / depths, as pure functions
    schemas.py         pydantic request + response models
    main.py            FastAPI app
frontend/
  package.json, vite.config.js, index.html
  src/main.jsx, src/App.jsx, src/styles.css
```

## Running it

The backend needs to find your existing data tree — the folder containing
`bellhop/` (with `bellhop.exe`, `grid_150m_WCFR.txt`, `readshd.py`) and
`ssp/ctd/`. Point `WG_DATA_ROOT` at it.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export WG_DATA_ROOT=/path/to/your/existing/project
uvicorn app.main:app --reload --port 8000
```

Check `http://localhost:8000/api/health` — it reports whether the executable,
grid file and SSP directory were found, and whether wine will be used.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, /api proxied to port 8000
```

Requires Python 3.10+ (the API uses `X | None` type syntax).

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `WG_DATA_ROOT` | repo root | folder containing `bellhop/` and `ssp/` |
| `WG_BELLHOP_DIR` | `$WG_DATA_ROOT/bellhop` | where `.env`/`.bty`/`.shd` are written |
| `WG_BELLHOP_EXE` | `$WG_BELLHOP_DIR/bellhop.exe` | the executable |
| `WG_GRID_FILE` | `$WG_BELLHOP_DIR/grid_150m_WCFR.txt` | bathymetric grid |
| `WG_SSP_DIR` | `$WG_DATA_ROOT/ssp/ctd` | archived CTD casts |
| `WG_USE_WINE` | auto | `1`/`0` to force wine on or off |
| `WG_BELLHOP_TIMEOUT` | `900` | seconds before a run is killed |

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | path and dependency check |
| `GET /api/arrays` | array presets for the dropdown |
| `GET /api/map?x=&y=&bearing=&range_m=` | survey-area map PNG, with optional source marker and bearing line |
| `POST /api/run` | run a scenario, returns `{plots: [{title, image}], diagnostics, notes}` |

`POST /api/run` body:

```json
{
  "x": 40000, "y": 130000, "bearing": 90,
  "frequency": 7500, "source_depth": 200, "receiver_depth": 200,
  "source_level": 135, "ambient_level": 70, "range_m": 5000,
  "mode": "standard",
  "use_current_ssp": false, "ssp_date": "20230619"
}
```

`mode` is `standard` (TL heatmap + TL slice + SSP), `ranges` (three heatmaps at
0 / +1 km / +2 km along track), or `depths` (three heatmaps at the source depth,
+50 m and +100 m).

## What changed in the Python, and why

Structural:

- **No `os.chdir`.** `run_bellhop` passes `cwd=` to `subprocess.run` instead.
  Changing the process working directory is not safe in a server handling more
  than one request.
- **A lock around Bellhop.** It reads and writes fixed filenames (`WG_.env`,
  `WG_.bty`, `WG_.shd`), so runs are serialised with a `threading.Lock` and the
  work is pushed to a threadpool so the event loop stays responsive.
- **Widget reads replaced by function arguments.** `run_standard` and friends
  take a validated `ScenarioParams` object; nothing reaches for globals.
- **`messagebox.showerror` replaced by `InputError`**, which the API turns into
  a 400 with the same message. Notably, the old error paths did `return` after
  showing the dialog, so `write_bty` returned `None` and the caller crashed with
  a confusing unpacking error. Now the run stops cleanly.
- **The grid file is cached** (`lru_cache`) instead of being re-read from disk on
  every slice, and the slow concave-hull land boundary is cached too.
- **`ssp_file` is no longer a global.** It's resolved per request and, when
  downloaded fresh, deleted in a `finally` block rather than on window close.
- **Diagnostics are returned, not printed** — the percentile table now comes back
  in the JSON response under `diagnostics`.

Bugs fixed along the way (worth a look, since they change results):

1. **`run_depths` and `run_ranges` called `write_env` with too few arguments** —
   they omitted `deepest_bathy`, so those two modes raised `TypeError` and could
   never have run. Both now rewrite the `.env` per iteration with that slice's
   own bathymetry.
2. **`run_ranges` never rewrote the `.env` between runs**, so the +1 km and +2 km
   panels used the first slice's model depth. Each run now gets a matching env.
3. **`determine_ssp` had `if abs(difference < 14)`** — that compares a bool, so
   `abs(...)` was always 0 or 1 and always truthy. The 14-day window never
   applied. It is now `abs(difference) < 14`.
4. **Degrees vs radians in `calculate_terminus_points`.** The PCS branch fed the
   bearing straight into `np.cos`/`np.sin` with the conversion line commented
   out, while `run_ranges` used `np.radians(bearing)` for its offsets. The two
   disagreed. The function now always converts degrees to radians. **Sanity-check
   this against a run you trust** — if the old un-converted behaviour was
   actually what you wanted, it's a one-line change in `geometry.py`.
5. **`np.arange` in the bathymetry slice** produced 29, 30 or 31 samples
   depending on rounding, and had special cases for a vertical or horizontal
   line. `np.linspace` gives exactly `RESOLUTION` samples with no special cases.
6. **`run_standard` indexed `tl[receiver_depth]` unguarded** — a receiver deeper
   than the model raised `IndexError`. It now returns a clear 400.
7. **`float` vs `int` coordinates.** `run_standard` read x/y as `float` while
   `run_ranges`/`run_depths` read them as `int`, so the same input gave slightly
   different geometry. Everything is `float` now.
8. **The array preset lists were mismatched** — 29 names, 42 x-values and 30
   y-values. `sites.ARRAYS` zips them, which pairs the 29 names with the first 29
   coordinates, exactly as the old `arrays.index(selected)` lookup did. The
   surplus coordinates are unused; worth confirming the pairing is right.

## Not carried over

- The cartopy imports and the commented-out gridline/NaturalEarth blocks were
  dead code and are gone. `cartopy` is no longer a dependency.
- The unused `re`, `ConvexHull` and `multiprocessing.util.debug` imports.
- `update_plot`'s first `try` block, which set `y` to a hard-coded `120000`
  before the second block immediately overwrote it.
