import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Run an async function and track its state.
 *
 * Requests are aborted when the inputs change or the component unmounts, so a
 * slow response for a city the user has already navigated away from can never
 * overwrite the current view.
 *
 * @param fn      receives an AbortSignal; should be stable (wrap in useCallback)
 * @param deps    re-runs when these change
 * @param options `{ enabled }` — skip the call while false
 */
export function useAsync(fn, deps = [], { enabled = true } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: enabled });
  const [nonce, setNonce] = useState(0);
  const mounted = useRef(true);

  // The flag must be re-armed in the effect body, not only cleared in cleanup:
  // StrictMode mounts, unmounts and remounts, so a cleanup-only version would
  // leave `mounted` false for the real mount and silently drop every setState.
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, error: null, loading: false });
      return undefined;
    }

    const controller = new AbortController();
    let active = true;
    setState((prev) => ({ ...prev, loading: true, error: null }));

    fn(controller.signal)
      .then((data) => {
        if (active && mounted.current) setState({ data, error: null, loading: false });
      })
      .catch((error) => {
        if (error.name === 'AbortError' || !active || !mounted.current) return;
        setState({ data: null, error, loading: false });
      });

    return () => {
      active = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, nonce]);

  return { ...state, refresh };
}

/**
 * An async action triggered by the user rather than by render.
 *
 * Returns `{ run, reset, data, error, loading }`. Only the most recent run can
 * settle the state, so rapid resubmissions cannot interleave.
 */
export function useAction(fn) {
  const [state, setState] = useState({ data: null, error: null, loading: false });
  const runId = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(
    async (...args) => {
      const id = ++runId.current;
      setState({ data: null, error: null, loading: true });
      try {
        const data = await fn(...args);
        if (id === runId.current && mounted.current) {
          setState({ data, error: null, loading: false });
        }
        return data;
      } catch (error) {
        if (error.name !== 'AbortError' && id === runId.current && mounted.current) {
          setState({ data: null, error, loading: false });
        }
        return undefined;
      }
    },
    [fn],
  );

  const reset = useCallback(() => {
    runId.current += 1;
    setState({ data: null, error: null, loading: false });
  }, []);

  return { ...state, run, reset };
}
