/**
 * Export a depth sweep as a video, entirely in the browser: each frame's PNGs
 * are drawn onto a canvas, then turned into video.
 *
 * MP4 (H.264) is made with WebCodecs via Mediabunny: every depth is encoded
 * with an exact timestamp and duration, so the video doesn't depend on timers,
 * runs faster than real time and keeps working if the tab is hidden. Browsers
 * without an H.264 encoder fall back to MediaRecorder, which records the
 * canvas in real time and may only manage WebM, and WebM doesn't open in
 * QuickTime or PowerPoint.
 */
import { BufferTarget, CanvasSource, Mp4OutputFormat, Output, QUALITY_HIGH, canEncodeVideo } from 'mediabunny'

// MediaRecorder fallback, preferred first.
const RECORDER_TYPES = ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm']
const CAPTION_HEIGHT = 56
const CANVAS_FPS = 30

export const VIDEO_CONTENTS = [
  { value: 'both', label: 'Colourmap + slice' },
  { value: 'tl', label: 'Colourmap only' },
  { value: 'slice', label: 'Slice only' },
]

function recorderType() {
  if (typeof MediaRecorder === 'undefined') return null
  return RECORDER_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? null
}

/** Whether this browser can make a video at all (the H.264 check needs the frame size, so happens later). */
export function canExportVideo() {
  return typeof VideoEncoder !== 'undefined' || recorderType() !== null
}

async function loadImage(src) {
  const img = new Image()
  img.src = src
  await img.decode()
  return img
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const even = (n) => Math.ceil(n / 2) * 2 // H.264 needs even dimensions

/** One sample per depth, each lasting exactly frameMs. */
async function encodeMp4(canvas, images, draw, frameMs, onProgress) {
  const output = new Output({
    format: new Mp4OutputFormat({ fastStart: 'in-memory' }), // moov first, so players open it straight away
    target: new BufferTarget(),
  })
  const seconds = frameMs / 1000
  // A key frame per depth, so scrubbing lands on any depth instantly.
  const source = new CanvasSource(canvas, { codec: 'avc', quality: QUALITY_HIGH, keyFrameInterval: 0 })
  output.addVideoTrack(source, { frameRate: 1 / seconds })
  await output.start()
  for (let i = 0; i < images.length; i++) {
    draw(images[i])
    await source.add(i * seconds, seconds)
    onProgress?.(i + 1, images.length)
  }
  await output.finalize()
  return { blob: new Blob([output.target.buffer], { type: 'video/mp4' }), extension: 'mp4' }
}

async function recordInRealTime(canvas, images, draw, frameMs, onProgress, mimeType) {
  draw(images[0]) // so the first captured frame isn't blank
  const stream = canvas.captureStream(CANVAS_FPS)
  const recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 8_000_000 })
  const chunks = []
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)
  const stopped = new Promise((resolve) => (recorder.onstop = resolve))

  // The stream only emits a video frame when the canvas is redrawn, and each
  // frame lasts until the next one, so redraw at the capture rate to hold
  // every depth, the last included, for its full frameMs.
  async function hold(image, ms) {
    const end = performance.now() + ms
    for (let left = ms; left > 0; left = end - performance.now()) {
      draw(image)
      await sleep(Math.min(1000 / CANVAS_FPS, left))
    }
  }

  recorder.start()
  for (let i = 0; i < images.length; i++) {
    onProgress?.(i + 1, images.length)
    await hold(images[i], frameMs)
  }
  draw(images[images.length - 1]) // closes the last hold so its duration is recorded
  recorder.stop()
  await stopped
  stream.getTracks().forEach((t) => t.stop())

  return {
    blob: new Blob(chunks, { type: mimeType.split(';')[0] }),
    extension: mimeType.startsWith('video/mp4') ? 'mp4' : 'webm',
  }
}

/**
 * frames: the sweep frames, in play order. frameMs: how long each one shows.
 * contents: one of VIDEO_CONTENTS. Resolves to { blob, extension }.
 */
export async function recordSweepVideo(frames, { frameMs, contents, onProgress }) {
  const images = await Promise.all(
    frames.map(async (f) => ({
      depth: f.depth,
      panels: [
        contents !== 'slice' && (await loadImage(f.tl.image)),
        contents !== 'tl' && (await loadImage(f.tl_slice.image)),
      ].filter(Boolean),
    })),
  )

  // Panels are stacked and centred; every frame has the same panel sizes.
  const panelSizes = images[0].panels.map((p) => [p.naturalWidth, p.naturalHeight])
  const canvas = document.createElement('canvas')
  canvas.width = even(Math.max(...panelSizes.map(([w]) => w)))
  canvas.height = even(CAPTION_HEIGHT + panelSizes.reduce((sum, [, h]) => sum + h, 0))
  const ctx = canvas.getContext('2d')

  function draw({ depth, panels }) {
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = '#000'
    ctx.font = '600 28px system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(`Source depth ${depth} m`, canvas.width / 2, CAPTION_HEIGHT / 2)
    let y = CAPTION_HEIGHT
    for (const panel of panels) {
      ctx.drawImage(panel, Math.round((canvas.width - panel.naturalWidth) / 2), y)
      y += panel.naturalHeight
    }
  }

  if (await canEncodeVideo('avc', { width: canvas.width, height: canvas.height, quality: QUALITY_HIGH })) {
    return encodeMp4(canvas, images, draw, frameMs, onProgress)
  }
  const mimeType = recorderType()
  if (!mimeType) throw new Error('This browser cannot make video (no H.264 encoder or MediaRecorder).')
  return recordInRealTime(canvas, images, draw, frameMs, onProgress, mimeType)
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
