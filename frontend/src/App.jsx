import { useEffect, useState } from 'react'
import { getHealth, getMap, postRun } from './api'
import TableAccordion from './TableAccordion'

const DEFAULTS = {
  lat: '',
  lon: '',
  bearing: '',
  frequency: 500,
  source_depth: 200,
  receiver_depth: 200,
  source_level: 125,
  ambient_level: 70,
  range_m: 5000,
  mode: 'standard',
  use_current_ssp: false,
  ssp_date: '20250211',
  depth_data: [],
  temperature_data: [],
}

const MODES = [
  { value: 'standard', label: 'Standard' },
  { value: 'ranges', label: 'Tactical (range)' },
  { value: 'depths', label: 'Tactical (depth)' },
]

const NUMERIC_FIELDS = [
  ['frequency', 'Frequency (Hz)'],
  ['source_depth', 'Source depth (m)'],
  ['receiver_depth', 'Receiver depth (m)'],
  ['source_level', 'Source level (dB)'],
  ['ambient_level', 'Ambient level (dB)'],
  ['range_m', 'Range (m)'],
]

/** Debounce a value so the map preview doesn't refetch on every keystroke. */
function useDebounced(value, delay = 600) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

/** Which configured paths the backend could not find. */
function missingPaths(health) {
  if (!health) return []
  const checks = [
    ['grid_file_exists', 'grid_file', 'Bathymetry grid'],
    ['bellhop_exe_exists', 'bellhop_exe', 'Bellhop executable'],
    ['ssp_dir_exists', 'ssp_dir', 'SSP directory'],
  ]
  return checks
    .filter(([flag]) => health[flag] === false)
    .map(([, pathKey, label]) => `${label}: ${health[pathKey]}`)
}

export default function App() {
  const [form, setForm] = useState(DEFAULTS)
  const [health, setHealth] = useState(null)
  const [backendError, setBackendError] = useState(null)
  const [mapFigure, setMapFigure] = useState(null)
  const [mapError, setMapError] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [running, setRunning] = useState(false)

  const preview = useDebounced(
    JSON.stringify({
      lat: form.lat,
      lon: form.lon,
      bearing: form.bearing,
      range_m: form.range_m,
    }),
  )

  // Reachability + configuration check. Failures here are shown rather than
  // swallowed
  useEffect(() => {
    let cancelled = false

    getHealth()
      .then((body) => !cancelled && setHealth(body))
      .catch((err) => !cancelled && setBackendError(err.message))

    return () => {
      cancelled = true
    }
  }, [])

  // Redraw the survey map whenever the source position or bearing settles.
  useEffect(() => {
    if (backendError) return undefined

    const { lat, lon, bearing, range_m } = JSON.parse(preview)
    const params = new URLSearchParams()
    if (lat !== '' && lon !== '') {
      params.set('lat', lat)
      params.set('lon', lon)
      if (bearing !== '') params.set('bearing', bearing)
      if (range_m !== '') params.set('range_m', range_m)
    }

    let cancelled = false
    getMap(params)
      .then((figure) => {
        if (cancelled) return
        setMapFigure(figure)
        setMapError(null)
      })
      .catch((err) => {
        if (cancelled) return
        setMapFigure(null)
        setMapError(err.message)
      })

    return () => {
      cancelled = true
    }
  }, [preview, backendError])

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  /** Turn a click on the map <img> into a lat/lon, using the pixel
   * <-> data-coordinate mapping the backend computed for this render. */
  function placeSourceFromClick(event) {
    const { pixel_bounds: px, data_bounds: db } = mapFigure ?? {}
    if (!px || !db) return

    const img = event.currentTarget
    const rect = img.getBoundingClientRect()
    const scaleX = img.naturalWidth / rect.width
    const scaleY = img.naturalHeight / rect.height
    const clickX = (event.clientX - rect.left) * scaleX
    const clickY = (event.clientY - rect.top) * scaleY

    if (clickX < px.left || clickX > px.right || clickY < px.top || clickY > px.bottom) {
      return // clicked outside the plotted axes (e.g. on the colorbar or title)
    }

    const fracX = (clickX - px.left) / (px.right - px.left)
    const fracY = (clickY - px.top) / (px.bottom - px.top)
    const lon = db.lon_min + fracX * (db.lon_max - db.lon_min)
    const lat = db.lat_max - fracY * (db.lat_max - db.lat_min)

    setForm((prev) => ({ ...prev, lat: lat.toFixed(5), lon: lon.toFixed(5) }))
  }

  async function runScenario(event) {
    event.preventDefault()
    setRunning(true)
    setError(null)
    setResult(null)

    const payload = { ...form }
    for (const key of ['lat', 'lon', 'bearing', ...NUMERIC_FIELDS.map((f) => f[0])]) {
      payload[key] = Number(payload[key])
    }

    try {
      setResult(await postRun(payload))
    } catch (err) {
      setError(err.traceback ? `${err.message}\n\n${err.traceback.join('\n')}` : err.message)
    } finally {
      setRunning(false)
    }
  }

  const configProblems = missingPaths(health)

  /** The accordion always has a few trailing blank rows -- drop those rather
   * than sending Number('') === 0 as a bogus (depth 0, temp 0) point, which
   * breaks Bellhop's "depths must be monotone increasing" requirement. */
  function setSsp(rows) {
    const filled = rows
      .filter((row) => row.a.trim() !== '' && row.b.trim() !== '')
      .map((row) => ({ depth: Number(row.a), temp: Number(row.b) }))
      .filter((row) => Number.isFinite(row.depth) && Number.isFinite(row.temp))

    setForm((prev) => ({
      ...prev,
      depth_data: filled.map((row) => row.depth),
      temperature_data: filled.map((row) => row.temp),
    }))
  }

  return (
    <div className="layout">
      <form className="panel" onSubmit={runScenario}>
        <h1>WG Acoustic Ranging</h1>

        {backendError && (
          <p className="error">
            <strong>Backend unreachable</strong>
            {'\n'}
            {backendError}
          </p>
        )}

        {configProblems.length > 0 && (
          <p className="warning">
            <strong>Backend is running but cannot find its data:</strong>
            {'\n'}
            {configProblems.join('\n')}
            {'\n\n'}
            Set WG_DATA_ROOT to the folder containing bellhop/ and ssp/.
          </p>
        )}

        <h2>Source location</h2>

        <p className="hint">Click the map to place the source, or enter coordinates directly.</p>

        <label>
          Latitude (°)
          <input value={form.lat} onChange={(e) => update('lat', e.target.value)} required />
        </label>
        <label>
          Longitude (°)
          <input value={form.lon} onChange={(e) => update('lon', e.target.value)} required />
        </label>
        <label>
          Bearing (deg)
          <input
            value={form.bearing}
            onChange={(e) => update('bearing', e.target.value)}
            required
          />
        </label>

        <h2>Input parameters</h2>

        {NUMERIC_FIELDS.map(([key, label]) => (
          <label key={key}>
            {label}
            <input value={form[key]} onChange={(e) => update(key, e.target.value)} />
          </label>
        ))}

        <h2>Sound Speed Profile</h2>

        <label>
          SSP date (yyyymmdd)
          <input
            value={form.use_current_ssp ? 'current' : form.ssp_date}
            disabled={form.use_current_ssp}
            onChange={(e) => update('ssp_date', e.target.value)}
          />
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.use_current_ssp}
            onChange={(e) => update('use_current_ssp', e.target.checked)}
          />
          Use current SSP
        </label>

        <h2>Manual Temperature Profile</h2>

        <p className="hint">Optional — override the temperature values from the SSP</p>

        <TableAccordion
          title="Enter Temperature Profile"
          columns={['Depth (m)', 'Temperature (°C)']}
          onChange={(rows) => setSsp(rows)}
        />

        <fieldset>
          <legend>Scenario</legend>
          {MODES.map((mode) => (
            <label key={mode.value} className="checkbox">
              <input
                type="radio"
                name="mode"
                value={mode.value}
                checked={form.mode === mode.value}
                onChange={(e) => update('mode', e.target.value)}
              />
              {mode.label}
            </label>
          ))}
        </fieldset>

        <button type="submit" disabled={running || !!backendError}>
          {running ? 'Running Bellhop…' : 'Run scenario'}
        </button>

        {error && <p className="error">{error}</p>}
      </form>

      <main className="results">
        {mapError && !backendError && (
          <p className="error">
            <strong>Map could not be drawn</strong>
            {'\n'}
            {mapError}
          </p>
        )}

        {mapFigure && (
          <figure>
            <img
              className="map-image"
              src={mapFigure.image}
              alt="Survey area — click to place the source"
              onClick={placeSourceFromClick}
            />
          </figure>
        )}

        {result?.notes?.length > 0 && (
          <div className="notes">
            {result.notes.map((note, i) => (
              <p key={i}>{note}</p>
            ))}
          </div>
        )}

        {result?.plots?.map((figure) => (
          <figure key={figure.title}>
            <figcaption>{figure.title}</figcaption>
            <img src={figure.image} alt={figure.title} />
          </figure>
        ))}

        {result?.diagnostics && (
          <details>
            <summary>TL diagnostics</summary>
            <pre>{JSON.stringify(result.diagnostics, null, 2)}</pre>
          </details>
        )}
      </main>
    </div>
  )
}
