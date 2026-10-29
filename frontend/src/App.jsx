import { useEffect, useState } from 'react'
import { getHealth, getMap, getWaterDepth, postRun } from './api'
import DepthSweep from './DepthSweep'
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
  sweep_min_depth: 100,
  sweep_max_depth: 450,
  sweep_count: 10,
}

const MODES = [
  { value: 'standard', label: 'Standard' },
  { value: 'ranges', label: 'Tactical (range)' },
  { value: 'depths', label: 'Tactical (depth)' },
  { value: 'sweep', label: 'Depth sweep' },
]

const NUMERIC_FIELDS = [
  ['frequency', 'Frequency (Hz)'],
  ['source_depth', 'Source depth (m)'],
  ['receiver_depth', 'Receiver depth (m)'],
  ['source_level', 'Source level (dB)'],
  ['ambient_level', 'Ambient level (dB)'],
  ['range_m', 'Range (m)'],
]

const SWEEP_FIELDS = [
  ['sweep_min_depth', 'Shallowest source depth (m)'],
  ['sweep_max_depth', 'Deepest source depth (m)'],
  ['sweep_count', 'Number of depths (2-50)'],
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
  // Water depth at the source: { status: 'idle' | 'loading' | 'ready' | 'outside' | 'error', value }
  const [waterDepth, setWaterDepth] = useState({ status: 'idle', value: null })

  const sourcePoint = useDebounced(JSON.stringify({ lat: form.lat, lon: form.lon }))

  const preview = useDebounced(
    JSON.stringify({
      lat: form.lat,
      lon: form.lon,
      bearing: form.bearing,
      range_m: form.range_m,
    }),
  )

  // Reachability + configuration check. Failures here are shown in the UI, but do not throw an exception that would break the whole app.
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

  // Look up the water depth at the source whenever its position settles.
  useEffect(() => {
    const { lat, lon } = JSON.parse(sourcePoint)
    if (backendError || lat === '' || lon === '') {
      setWaterDepth({ status: 'idle', value: null })
      return undefined
    }

    let cancelled = false
    setWaterDepth({ status: 'loading', value: null })
    getWaterDepth(new URLSearchParams({ lat, lon }))
      .then(({ water_depth_m: value }) => {
        if (cancelled) return
        setWaterDepth(value == null ? { status: 'outside', value: null } : { status: 'ready', value })
      })
      .catch(() => !cancelled && setWaterDepth({ status: 'error', value: null }))

    return () => {
      cancelled = true
    }
  }, [sourcePoint, backendError])

  useEffect(() => {
    if (waterDepth.status === 'ready' && Number(form.sweep_max_depth) >= waterDepth.value) {
      setForm((prev) => ({ ...prev, sweep_max_depth: waterDepth.value - 1 }))
    }
  }, [waterDepth])

  function update(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  /** Turn a click on the map <img> into a lat/lon, using the pixel and data bounds returned by the backend. */
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
    const numericKeys = [...NUMERIC_FIELDS, ...SWEEP_FIELDS].map((f) => f[0])
    for (const key of ['lat', 'lon', 'bearing', ...numericKeys]) {
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

        {form.mode === 'sweep' && (
          <>
            <p className="hint">
              {{
                idle: 'Place the source to see the water depth there.',
                loading: 'Looking up water depth at the source…',
                ready: `Water depth at the source: ${waterDepth.value} m`,
                outside: 'The source is outside the bathymetry grid.',
                error: 'Could not look up the water depth at the source.',
              }[waterDepth.status]}
            </p>
            {waterDepth.status === 'ready' && Number(form.sweep_max_depth) >= waterDepth.value && (
              <p className="warning">
                The deepest source depth must be shallower than {waterDepth.value} m.
              </p>
            )}
            {SWEEP_FIELDS.map(([key, label]) => (
              <label key={key}>
                {label}
                <input value={form[key]} onChange={(e) => update(key, e.target.value)} />
              </label>
            ))}
            <p className="hint">
              Bellhop solves every depth in one run, so run time grows with the number of depths.
              The source depth field above is not used.
            </p>
          </>
        )}

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

        {result?.warnings?.map((warning, i) => (
          <p key={i} className="warning">
            {warning}
          </p>
        ))}

        {result?.notes?.length > 0 && (
          <div className="notes">
            {result.notes.map((note, i) => (
              <p key={i}>{note}</p>
            ))}
          </div>
        )}

        {result?.sweep_frames?.length > 0 && <DepthSweep frames={result.sweep_frames} />}

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
