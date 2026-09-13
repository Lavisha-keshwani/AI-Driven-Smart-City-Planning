import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, analyzeMicroplastic, getCityLayer, planBuilding, runCoordinator } from './client';

/**
 * The API client's contract: it must surface the backend's own error envelope
 * rather than swallowing a failure or substituting placeholder data.
 */

function mockFetch(response) {
  const spy = vi.fn().mockResolvedValue(response);
  globalThis.fetch = spy;
  return spy;
}

const ok = (body) => ({ ok: true, status: 200, json: async () => body });
const fail = (status, body) => ({ ok: false, status, json: async () => body });

describe('request handling', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('returns the parsed payload on success', async () => {
    mockFetch(ok({ type: 'FeatureCollection', features: [] }));
    await expect(getCityLayer('urban', 'Chennai')).resolves.toEqual({
      type: 'FeatureCollection',
      features: [],
    });
  });

  it('builds the right URL for a city layer', async () => {
    const spy = mockFetch(ok({}));
    await getCityLayer('flood', 'New Delhi', { limit: 50 });

    const url = new URL(spy.mock.calls[0][0]);
    expect(url.pathname).toBe('/api/flood-risk/city/New%20Delhi/geojson');
    expect(url.searchParams.get('limit')).toBe('50');
  });

  it('rejects an unknown layer before making a request', () => {
    const spy = mockFetch(ok({}));
    expect(() => getCityLayer('weather', 'Chennai')).toThrow(/Unknown layer/);
    expect(spy).not.toHaveBeenCalled();
  });

  it('surfaces the backend error code and message', async () => {
    mockFetch(
      fail(503, {
        error: 'model_unavailable',
        message: 'Model 3 (Flood Risk) is not available.',
        detail: { config_key: 'FLOOD_MODEL_PATH' },
      }),
    );

    const error = await runCoordinator({ grid_id: 'X_1' }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe('model_unavailable');
    expect(error.status).toBe(503);
    expect(error.message).toMatch(/not available/);
    expect(error.detail.config_key).toBe('FLOOD_MODEL_PATH');
    expect(error.isUnavailable).toBe(true);
  });

  it('distinguishes an unavailable model from bad input', async () => {
    mockFetch(fail(404, { error: 'grid_not_found', message: 'No such cell.', detail: {} }));
    const error = await runCoordinator({ grid_id: 'nope' }).catch((e) => e);
    expect(error.code).toBe('grid_not_found');
    expect(error.isUnavailable).toBe(false);
  });

  it('reports an unreachable backend clearly', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    const error = await runCoordinator({ grid_id: 'X_1' }).catch((e) => e);
    expect(error.code).toBe('network_error');
    expect(error.message).toMatch(/Cannot reach the backend/);
  });

  it('propagates an abort rather than reporting it as a failure', async () => {
    const abortError = Object.assign(new Error('aborted'), { name: 'AbortError' });
    globalThis.fetch = vi.fn().mockRejectedValue(abortError);
    await expect(runCoordinator({ grid_id: 'X_1' })).rejects.toHaveProperty(
      'name',
      'AbortError',
    );
  });

  it('handles an error response with no JSON body', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error('not json');
      },
    });
    const error = await runCoordinator({ grid_id: 'X_1' }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(500);
  });
});

describe('request bodies', () => {
  it('posts the coordinator payload as JSON', async () => {
    const spy = mockFetch(ok({}));
    await runCoordinator({ grid_id: 'Chennai_1', include_attribution: false });

    const [, init] = spy.mock.calls[0];
    expect(init.method).toBe('POST');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body)).toEqual({
      grid_id: 'Chennai_1',
      include_attribution: false,
    });
  });

  it('sends the three polarimetric channels under their expected field names', async () => {
    const spy = mockFetch(ok({}));
    const file = (name) => new File(['x'], name, { type: 'image/bmp' });
    await analyzeMicroplastic({ r: file('r.bmp'), a: file('a.bmp'), p: file('p.bmp') });

    const form = spy.mock.calls[0][1].body;
    expect(form).toBeInstanceOf(FormData);
    expect(form.get('r_image').name).toBe('r.bmp');
    expect(form.get('a_image').name).toBe('a.bmp');
    expect(form.get('p_image').name).toBe('p.bmp');
  });

  it('passes the interpret flag as a query parameter', async () => {
    const spy = mockFetch(ok({}));
    await planBuilding({ lat: 13, lon: 80 }, { interpret: false });
    expect(new URL(spy.mock.calls[0][0]).searchParams.get('interpret')).toBe('false');
  });
});
