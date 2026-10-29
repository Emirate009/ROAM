/**
 * Record a depth sweep as a video, entirely in the browser: each frame's PNGs
 * are drawn onto a canvas and MediaRecorder captures the canvas in real time,
 * so the video plays at exactly the rate the frames were drawn.
 */

// Preferred first; MP4 opens in PowerPoint / QuickTime, WebM is the fallback.
const MIME_TYPES = ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm']
const CAPTION_HEIGHT = 56
const CANVAS_FPS = 30

export const VIDEO_CONTENTS = [
  { value: 'both', label: 'Colourmap + slice' },
  { value: 'tl', label: 'Colourmap only' },
  { value: 'slice', label: 'Slice only' },
]

export function supportedVideoType() {
  if (typeof MediaRecorder === 'undefined') return null
  return MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? null
}

async function loadImage(src) {
  const img = new Image()
  img.src = src
  await img.decode()
  return img
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const even = (n) => Math.ceil(n / 2) * 2 // H.264 needs even dimensions

/**
 * frames: the sweep frames, in play order. frameMs: how long each one shows.
 * contents: one of VIDEO_CONTENTS. Resolves to { blob, extension }.
 */
export async function recordSweepVideo(frames, { frameMs, contents, onProgress }) {
  const mimeType = supportedVideoType()
  if (!mimeType) throw new Error('This browser cannot record video (no MediaRecorder support).')

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

  draw(images[0]) // so the first captured frame isn't blank
  const stream = canvas.captureStream(CANVAS_FPS)
  const recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 8_000_000 })
  const chunks = []
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data)
  const stopped = new Promise((resolve) => (recorder.onstop = resolve))

  recorder.start()
  for (let i = 0; i < images.length; i++) {
    draw(images[i])
    onProgress?.(i + 1, images.length)
    await sleep(frameMs)
  }
  recorder.stop()
  await stopped
  stream.getTracks().forEach((t) => t.stop())

  return {
    blob: new Blob(chunks, { type: mimeType.split(';')[0] }),
    extension: mimeType.startsWith('video/mp4') ? 'mp4' : 'webm',
  }
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
