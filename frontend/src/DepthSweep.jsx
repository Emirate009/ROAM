import { useEffect, useState } from 'react'
import { VIDEO_CONTENTS, downloadBlob, recordSweepVideo, supportedVideoType } from './sweepVideo'

const PLAY_INTERVAL_MS = 600
// The speed button cycles through these multipliers of the base rate.
const PLAY_SPEEDS = [1, 2, 4, 8]

/** Arrow keys typed into a form field belong to that field, not the sweep. */
function isTyping(target) {
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target?.tagName)
}

/**
 * Step through a depth sweep's precomputed frames. Every frame is already in
 * the response, so switching depth never calls the backend.
 */
export default function DepthSweep({ frames }) {
  const [index, setIndex] = useState(0)
  const [ready, setReady] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(PLAY_SPEEDS[0])
  const [videoContents, setVideoContents] = useState(VIDEO_CONTENTS[0].value)
  const [recording, setRecording] = useState(false)
  const [videoStatus, setVideoStatus] = useState('')
  const canRecord = supportedVideoType() !== null
  const last = frames.length - 1

  // Decode every image up front so the first visit to a depth doesn't flash.
  useEffect(() => {
    let cancelled = false
    setIndex(0)
    setReady(false)
    setPlaying(false)

    const decode = (src) => {
      const img = new Image()
      img.src = src
      return img.decode().catch(() => {}) // a bad frame still shows its alt text
    }
    Promise.all(frames.flatMap((f) => [decode(f.tl.image), decode(f.tl_slice.image)])).then(
      () => !cancelled && setReady(true),
    )

    return () => {
      cancelled = true
    }
  }, [frames])

  // Down arrow = deeper source, up arrow = shallower.
  useEffect(() => {
    function onKeyDown(event) {
      if (isTyping(event.target)) return
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setIndex((i) => Math.min(i + 1, last))
      } else if (event.key === 'ArrowUp') {
        event.preventDefault()
        setIndex((i) => Math.max(i - 1, 0))
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [last])

  // Play steps down to the deepest frame, then stops.
  useEffect(() => {
    if (!playing) return undefined
    const timer = setInterval(() => {
      setIndex((i) => {
        if (i >= last) {
          setPlaying(false)
          return i
        }
        return i + 1
      })
    }, PLAY_INTERVAL_MS / speed)
    return () => clearInterval(timer)
  }, [playing, last, speed])

  function togglePlay() {
    if (!playing && index >= last) setIndex(0)
    setPlaying((p) => !p)
  }

  function cycleSpeed() {
    setSpeed((s) => PLAY_SPEEDS[(PLAY_SPEEDS.indexOf(s) + 1) % PLAY_SPEEDS.length])
  }

  // Records at the current playback speed, so the video matches what Play shows.
  async function exportVideo() {
    setPlaying(false)
    setRecording(true)
    try {
      setVideoStatus('Preparing video…')
      const { blob, extension } = await recordSweepVideo(frames, {
        frameMs: PLAY_INTERVAL_MS / speed,
        contents: videoContents,
        onProgress: (i, n) => setVideoStatus(`Recording frame ${i} / ${n}…`),
      })
      const first = frames[0].depth
      const lastDepth = frames[last].depth
      downloadBlob(blob, `depth-sweep_${first}-${lastDepth}m_${videoContents}_${speed}x.${extension}`)
      setVideoStatus('')
    } catch (err) {
      setVideoStatus(`Video export failed: ${err.message}`)
    } finally {
      setRecording(false)
    }
  }

  const frame = frames[index]

  return (
    <section className="sweep">
      <div className="sweep-controls">
        <button type="button" onClick={() => setIndex((i) => Math.max(i - 1, 0))} disabled={!ready || index === 0} aria-label="Shallower source">
          ▲
        </button>
        <button type="button" onClick={() => setIndex((i) => Math.min(i + 1, last))} disabled={!ready || index === last} aria-label="Deeper source">
          ▼
        </button>
        <button type="button" onClick={togglePlay} disabled={!ready}>
          {playing ? 'Pause' : 'Play'}
        </button>
        <button type="button" onClick={cycleSpeed} disabled={!ready} aria-label="Playback speed" title="Playback speed">
          {speed}×
        </button>
        <input
          type="range"
          min={0}
          max={last}
          value={index}
          disabled={!ready}
          onChange={(e) => setIndex(Number(e.target.value))}
          aria-label="Source depth"
        />
        <span className="sweep-label">
          {ready ? `Source depth ${frame.depth} m (${index + 1} / ${frames.length})` : 'Loading frames…'}
        </span>
      </div>
      <p className="hint">Use the ↑ / ↓ arrow keys to move the source.</p>

      <div className="sweep-controls">
        <select value={videoContents} onChange={(e) => setVideoContents(e.target.value)} disabled={recording} aria-label="Video contents">
          {VIDEO_CONTENTS.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
        <button type="button" onClick={exportVideo} disabled={!ready || !canRecord || recording}>
          Export video ({speed}×)
        </button>
        {videoStatus && <span className="hint">{videoStatus}</span>}
        {!canRecord && <span className="hint">This browser can't record video.</span>}
      </div>

      <figure>
        <img src={frame.tl.image} alt={frame.tl.title} />
      </figure>
      <figure>
        <img src={frame.tl_slice.image} alt={frame.tl_slice.title} />
      </figure>
    </section>
  )
}
