/**
 * One fetch helper for every call, so a dead backend produces a sentence you
 * can act on instead of "JSON.parse: unexpected end of data".
 *
 * The Vite dev proxy answers with a 500 and an EMPTY body when it cannot reach
 * the target, which is what that cryptic parse error actually meant.
 */

const BACKEND_HINT =
  'Is the backend running? Start it with:\n' +
  '  cd backend && uvicorn app.main:app --reload --port 8000'

export class ApiError extends Error {
  constructor(message, { status = null, traceback = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.traceback = traceback
  }
}

export async function request(path, options = {}) {
  let response
  try {
    response = await fetch(path, options)
  } catch (err) {
    // Network-level failure: wrong port, server down, CORS block.
    throw new ApiError(`Could not reach ${path}.\n${BACKEND_HINT}`)
  }

  const text = await response.text()

  if (text.trim() === '') {
    throw new ApiError(
      `${path} returned HTTP ${response.status} with an empty body.\n${BACKEND_HINT}`,
      { status: response.status },
    )
  }

  let body
  try {
    body = JSON.parse(text)
  } catch {
    // Non-JSON body: usually an HTML error page from a proxy, or Starlette's
    // plain-text "Internal Server Error".
    throw new ApiError(
      `${path} returned HTTP ${response.status} with a non-JSON body:\n` +
        text.slice(0, 300),
      { status: response.status },
    )
  }

  if (!response.ok) {
    // FastAPI validation errors (422) are a list of { loc, msg }; show them as
    // "field: message" lines rather than raw JSON.
    const detail =
      typeof body.detail === 'string'
        ? body.detail
        : Array.isArray(body.detail) && body.detail.every((e) => e?.msg)
          ? body.detail.map((e) => `${(e.loc ?? []).filter((p) => p !== 'body').join('.')}: ${e.msg}`).join('\n')
          : JSON.stringify(body.detail ?? body, null, 2)
    throw new ApiError(detail, { status: response.status, traceback: body.traceback })
  }

  return body
}

export const getHealth = () => request('/api/health')
export const getArrays = () => request('/api/arrays')
export const getMap = (params) => request(`/api/map?${params.toString()}`)
export const getWaterDepth = (params) => request(`/api/water-depth?${params.toString()}`)

export const postRun = (payload) =>
  request('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
