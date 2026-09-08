// Thin fetch wrappers around the FastAPI backend (src/rogaine/web/app.py). No DOM/state here --
// callers (app.js) own all UI state; this module only knows request/response shapes.

/** Thrown for any non-2xx response; `message` is the server's own explanation when it has one. */
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// FastAPI's HTTPException responses are `{"detail": "<string>"}`; a raw pydantic validation
// failure (malformed request body) instead sends `{"detail": [{"msg": "...", ...}, ...]}`. Both
// are handled so an unexpected shape mismatch still surfaces *something* readable.
async function _errorDetail(resp) {
  let body;
  try {
    body = await resp.json();
  } catch {
    return resp.statusText || `HTTP ${resp.status}`;
  }
  const detail = body && body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => (e && e.msg) || JSON.stringify(e)).join("; ");
  }
  return resp.statusText || `HTTP ${resp.status}`;
}

async function _requestJson(method, url, body) {
  const resp = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) throw new ApiError(await _errorDetail(resp), resp.status);
  if (resp.status === 204) return null;
  return resp.json();
}

/** `POST /api/runs` -- multipart upload. Returns `{run_id}`. */
export async function uploadMap(file) {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch("/api/runs", { method: "POST", body: form });
  if (!resp.ok) throw new ApiError(await _errorDetail(resp), resp.status);
  return resp.json();
}

/** URL for the raw uploaded map bytes (an `<img>`/`fetch` target, not JSON). */
export function mapUrl(runId) {
  return `/api/runs/${encodeURIComponent(runId)}/map`;
}

/** `POST /api/runs/{runId}/segment`. `body` is `{dpi?, scale?, calibrate?, page?}`. Returns `{job_id}`. */
export function startSegment(runId, body) {
  return _requestJson("POST", `/api/runs/${encodeURIComponent(runId)}/segment`, body);
}

/** `POST /api/runs/{runId}/detect`, no body. Returns `{job_id}`. */
export function startDetect(runId) {
  return _requestJson("POST", `/api/runs/${encodeURIComponent(runId)}/detect`, {});
}

/** `POST /api/runs/{runId}/auto-scale`, no body. Returns `{job_id}`. */
export function startAutoScale(runId) {
  return _requestJson("POST", `/api/runs/${encodeURIComponent(runId)}/auto-scale`, {});
}

/** `GET /api/runs/{runId}/controls` -> `Control[]`. */
export function getControls(runId) {
  return _requestJson("GET", `/api/runs/${encodeURIComponent(runId)}/controls`);
}

/** `PUT /api/runs/{runId}/controls` with the full `Control[]` -> the validated `Control[]` back. */
export function putControls(runId, controls) {
  return _requestJson("PUT", `/api/runs/${encodeURIComponent(runId)}/controls`, controls);
}

/** `POST /api/runs/{runId}/plan` with a `RunConfig` body. Returns `{job_id}`. */
export function startPlan(runId, runConfig) {
  return _requestJson("POST", `/api/runs/${encodeURIComponent(runId)}/plan`, runConfig);
}

/** `GET /api/jobs/{jobId}` -> `JobStatusOut`. */
export function getJob(jobId) {
  return _requestJson("GET", `/api/jobs/${encodeURIComponent(jobId)}`);
}

/** Poll `GET /api/jobs/{jobId}` until `status` is `"done"`/`"error"`. `onTick` sees every poll. */
export async function waitForJob(jobId, { intervalMs = 400, onTick } = {}) {
  for (;;) {
    const job = await getJob(jobId);
    if (onTick) onTick(job);
    if (job.status === "done" || job.status === "error") return job;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

/** URL for `GET /api/runs/{runId}/export/{artifact}` -- a plain download link target. */
export function exportUrl(runId, artifact) {
  return `/api/runs/${encodeURIComponent(runId)}/export/${encodeURIComponent(artifact)}`;
}
