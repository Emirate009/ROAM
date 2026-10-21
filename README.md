# WG Acoustic Ranging

A web application for modelling underwater acoustic propagation with the
Bellhop ray-tracing model. Choose a source position on a bathymetry map, set the
acoustic parameters and a sound speed profile, and the app runs Bellhop and
shows the transmission loss (TL) results as plots.

- **Backend:** Python / FastAPI. Builds the bathymetry and environment files,
  runs Bellhop and draws the figures with matplotlib.
- **Frontend:** React / Vite. A form for the run inputs, a clickable survey map,
  and a results panel.

## Project structure

```
ROAM/
├── .vscode/
│   └── launch.json              VS Code run configurations
├── backend/
│   ├── requirements.txt         Python dependencies
│   └── app/
│       ├── main.py              FastAPI app and endpoints
│       ├── config.py            paths and runtime settings
│       ├── schemas.py           request/response models and validation
│       ├── scenarios.py         standard / range / depth scenario modes
│       ├── bathymetry.py        grid loading, bathymetry slices, .bty writing
│       ├── environment.py       Bellhop .env writing
│       ├── bellhop_runner.py    runs Bellhop, reads TL from the shade file
│       ├── ssp.py               SSP selection, download and reading
│       ├── ocean_navigator_api_script_csv.py  downloads a current SSP from Ocean Navigator
│       ├── create_ssp.py        builds an SSP from a manual temperature profile
│       ├── geometry.py          bearing and end-point calculations
│       ├── sites.py             array presets, survey boundary, coordinate transforms
│       ├── plots.py             matplotlib figures returned as PNGs
│       └── errors.py            error types mapped to HTTP responses
├── frontend/
│   ├── package.json
│   ├── vite.config.js           dev server; proxies /api to the backend
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx              main form, map and results
│       ├── TableAccordion.jsx   manual temperature profile table
│       ├── api.js               fetch helpers
│       └── styles.css
├── bellhop/
│   ├── bellhop.exe              Bellhop executable
│   ├── CHS_Bathy_Data/          raw CHS NONNA-100 bathymetry tiles
│   ├── format_bathy_data_part2.py  builds the bathymetry grid from the CHS tiles
│   ├── grid_150m.txt            Processed bathymetry file for the WCFR
│   ├── readshd.py, plotray.py, plotray_2.py   Bellhop output helpers
│   └── WG_.*                    Bellhop input/output files (rewritten on each run)
├── ssp/ctd/                     archived CTD casts (yyyymmddhhmm.csv) and custom_ssp.csv
└── README.md
```

## Requirements

- Python 3.10 or newer
- Node.js 18 or newer, with npm
- [Wine](https://www.winehq.org/), on macOS or Linux only. `bellhop.exe` is a
  Windows executable, and the backend uses Wine for it automatically when it
  isn't running on Windows.

## Setup

From the repository root:

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Frontend
cd frontend
npm install
```

The backend reads its bathymetry grid from `bellhop/grid_150m_WCFR.txt`. If that
file isn't there, build it from the CHS tiles by running this from the
repository root:

```bash
python bellhop/format_bathy_data_part2.py
```

## Running in VS Code

1. Open the `ROAM` folder in VS Code.
2. Install the **Python** extension (which includes the Python Debugger).
3. Choose the virtual environment: open the Command Palette with
   `Cmd/Ctrl+Shift+P`, run **Python: Select Interpreter**, and pick `.venv`.
4. Open the **Run and Debug** view (`Cmd/Ctrl+Shift+D`).
5. Choose **ROAM (backend + frontend)** from the dropdown and press **F5**.
   This starts:
   - the FastAPI backend on `http://localhost:8000`
   - the Vite frontend on `http://localhost:5173`
6. Open `http://localhost:5173` in your browser.

You can also start each part by itself with **ROAM backend (FastAPI)** or
**ROAM frontend (Vite)**. Stopping the compound configuration stops both.

To check the backend, open `http://localhost:8000/api/health`. It shows whether
the grid file, Bellhop executable and SSP directory were found, and whether Wine
will be used.

### Running from a terminal instead

```bash
# Terminal 1, from backend/
WG_DATA_ROOT=.. uvicorn app.main:app --reload --port 8000

# Terminal 2, from frontend/
npm run dev
```

## Using the application

1. **Place the source.** Click the survey map to set the source latitude and
   longitude, or type them into the form. Enter a **bearing** in compass
   degrees (0 = north, 90 = east). The map then draws the source and the
   bearing line out to the chosen range.
2. **Set the input parameters:**
   - Frequency (Hz)
   - Source depth and receiver depth (m)
   - Source level and ambient noise level (dB)
   - Range (m): how far the model runs along the bearing
3. **Choose a sound speed profile (SSP)** in one of three ways:
   - **SSP date** (`yyyymmdd`): uses the archived CTD cast in `ssp/ctd/` closest
     to that date. If none is within 14 days, it uses a cast from the same month.
   - **Use current SSP**: downloads a current profile for the source position
     from Ocean Navigator. This needs an internet connection.
   - **Manual temperature profile** (optional): open *Enter Temperature
     Profile* and enter depth/temperature pairs, or upload a CSV whose first two
     columns are depth and temperature. You need at least 8 points, with depths
     strictly increasing. When a manual profile is given, it is used instead of
     the date or current SSP.
4. **Pick a scenario:**
   - **Standard**: a TL heatmap, a TL-versus-range slice at the receiver
     depth, and the SSP plot.
   - **Tactical (range)**: three TL heatmaps, starting at the source position
     and then 1 km and 2 km further along the bearing.
   - **Tactical (depth)**: three TL heatmaps, at the source depth and then
     50 m and 100 m deeper.
5. Click **Run scenario**. Bellhop can take a while to run. When it finishes,
   the plots appear under the map, along with any notes. Expand
   **TL diagnostics** to see the summary statistics.

Problems are shown in the app itself: a backend that can't be reached, missing
data files, and invalid inputs (for example, a receiver deeper than the water
column).

## Configuration

Paths and settings can be overridden with environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `WG_DATA_ROOT` | repository root | folder containing `bellhop/` and `ssp/` |
| `WG_BELLHOP_DIR` | `$WG_DATA_ROOT/bellhop` | where Bellhop input/output files are written |
| `WG_BELLHOP_EXE` | `$WG_BELLHOP_DIR/bellhop.exe` | Bellhop executable |
| `WG_GRID_FILE` | `$WG_BELLHOP_DIR/grid_150m_WCFR.txt` | bathymetry grid |
| `WG_SSP_DIR` | `$WG_DATA_ROOT/ssp/ctd` | archived CTD casts |
| `WG_USE_WINE` | auto | `1` or `0` to force Wine on or off |
| `WG_BELLHOP_TIMEOUT` | `900` | seconds before a Bellhop run is stopped |

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | checks paths and dependencies |
| `GET /api/arrays` | array preset positions |
| `GET /api/map?lat=&lon=&bearing=&range_m=` | survey map image, with optional source marker and bearing line |
| `POST /api/run` | runs a scenario and returns plots, diagnostics and notes |

Example `POST /api/run` body:

```json
{
  "lat": 49.16317, "lon": -127.42809, "bearing": 90,
  "frequency": 500, "source_depth": 200, "receiver_depth": 200,
  "source_level": 125, "ambient_level": 70, "range_m": 5000,
  "mode": "standard",
  "use_current_ssp": false, "ssp_date": "20250211"
}
```

Interactive API docs are at `http://localhost:8000/docs` while the backend is
running.