// API client for the SmartCityAI backend.
//
// Every function here hits a real endpoint. There is no mock path: if the backend
// is down or a model is unavailable, the caller gets an ApiError carrying the
// backend's own error code and message, and the UI shows that rather than
// substituting placeholder data.

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/** An error carrying the backend's error envelope. */
export class ApiError extends Error {
  constructor(message, { code, status, detail } = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code || 'request_failed';
    this.status = status ?? 0;
    this.detail = detail || {};
  }

  /** True when the cause is a missing model or dataset rather than bad input. */
  get isUnavailable() {
    return this.code === 'model_unavailable' || this.code === 'dataset_unavailable';
  }
}

async function request(path, { method = 'GET', body, signal, params } = {}) {
  const url = new URL(`${BASE_URL}${path}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }

  let response;
  try {
    response = await fetch(url, {
      method,
      signal,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (cause) {
    if (cause.name === 'AbortError') throw cause;
    throw new ApiError(
      `Cannot reach the backend at ${BASE_URL}. Is it running?`,
      { code: 'network_error' },
    );
  }

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(
      payload?.message || `Request failed with status ${response.status}`,
      { code: payload?.error, status: response.status, detail: payload?.detail },
    );
  }
  return payload;
}

async function upload(path, formData, { signal } = {}) {
  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { method: 'POST', body: formData, signal });
  } catch (cause) {
    if (cause.name === 'AbortError') throw cause;
    throw new ApiError(`Cannot reach the backend at ${BASE_URL}.`, { code: 'network_error' });
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(payload?.message || `Upload failed (${response.status})`, {
      code: payload?.error,
      status: response.status,
      detail: payload?.detail,
    });
  }
  return payload;
}

// ── System ─────────────────────────────────────────────────────────────────

export const getHealth = (opts) => request('/health', opts);
export const getModelsStatus = (opts) => request('/api/models/status', opts);
export const getAgentsInfo = (opts) => request('/api/agents', opts);

// ── Grid ───────────────────────────────────────────────────────────────────

export const getCities = (opts) => request('/api/grid/cities', opts);
export const getGridCell = (gridId, opts) => request(`/api/grid/cell/${gridId}`, opts);
export const getNearestCell = (lat, lon, opts) =>
  request('/api/grid/nearest', { ...opts, params: { lat, lon } });

// ── Model layers ───────────────────────────────────────────────────────────

/** A city's GeoJSON layer for one model. `layer` is water | urban | flood. */
export function getCityLayer(layer, city, { limit, signal } = {}) {
  const prefix = {
    water: '/api/water',
    urban: '/api/urban-expansion',
    flood: '/api/flood-risk',
  }[layer];
  if (!prefix) throw new Error(`Unknown layer "${layer}"`);
  return request(`${prefix}/city/${encodeURIComponent(city)}/geojson`, {
    signal,
    params: { limit },
  });
}

export const getWaterCell = (gridId, opts) => request(`/api/water/cell/${gridId}`, opts);
export const getUrbanCell = (gridId, opts) =>
  request(`/api/urban-expansion/cell/${gridId}`, opts);
export const getFloodCell = (gridId, opts) => request(`/api/flood-risk/cell/${gridId}`, opts);

export const getWaterMonitoring = (city, opts) =>
  request(`/api/water/monitoring/${encodeURIComponent(city)}`, opts);

// ── Metrics and thresholds (the technical-details panels) ───────────────────

export const getMetrics = (layer, opts) => {
  const prefix = {
    water: '/api/water',
    urban: '/api/urban-expansion',
    flood: '/api/flood-risk',
    microplastics: '/api/microplastics',
  }[layer];
  if (!prefix) throw new Error(`Unknown metrics target "${layer}"`);
  return request(`${prefix}/metrics`, opts);
};

export const getThresholds = (layer, opts) => {
  const prefix = { urban: '/api/urban-expansion', flood: '/api/flood-risk' }[layer];
  if (!prefix) throw new Error(`Unknown thresholds target "${layer}"`);
  return request(`${prefix}/thresholds`, opts);
};

// ── Agents ─────────────────────────────────────────────────────────────────

/** Full multi-agent pipeline, coordinator-first payload. */
export const runCoordinator = (payload, opts) =>
  request('/api/coordinator', { ...opts, method: 'POST', body: payload });

export const runPipeline = (payload, opts) =>
  request('/api/agents/analyze', { ...opts, method: 'POST', body: payload });

export const runAgent = (domain, payload, opts) =>
  request(`/api/agents/${domain}`, { ...opts, method: 'POST', body: payload });

// ── Microplastics ──────────────────────────────────────────────────────────

/** Screen a particle from its three polarimetric channels. */
export function analyzeMicroplastic({ r, a, p }, opts) {
  const form = new FormData();
  form.append('r_image', r);
  form.append('a_image', a);
  form.append('p_image', p);
  return upload('/api/microplastics/analyze', form, opts);
}

/** Screen an already-composited 3-channel image. */
export function analyzeMicroplasticComposite(image, opts) {
  const form = new FormData();
  form.append('image', image);
  return upload('/api/microplastics/analyze-composite', form, opts);
}

// ── Building planner ───────────────────────────────────────────────────────

export const planBuilding = (params, { interpret = true, signal } = {}) =>
  request('/api/building-planner', {
    method: 'POST',
    body: params,
    signal,
    params: { interpret },
  });

export const getSiteConditions = (lat, lon, opts) =>
  request('/api/building-planner/site', { ...opts, params: { lat, lon } });

export const getGuidelines = (opts) => request('/api/building-planner/guidelines', opts);

export { BASE_URL };
