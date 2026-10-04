import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./client";

export interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Fetch once per `key`, and again on `reload()`.
 *
 * Keyed on a string rather than on the loader function, because every caller builds its loader
 * inline and a function in the dependency array would refetch on every render.
 */
export function useApi<T>(load: () => Promise<T>, key: string): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // A cancelled flag rather than an AbortController: these requests finish in tens of
    // milliseconds, and the only real risk is a slow one landing after the filters moved on.
    let cancelled = false;
    setLoading(true);
    load()
      .then((value) => {
        if (cancelled) return;
        setData(value);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(
          caught instanceof ApiError
            ? caught
            : new ApiError(0, "unknown", String(caught), null),
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // `load` is deliberately absent; see the note above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  // Loading is set here as well as in the effect, which only runs after the next render. Without
  // it there is one render in which a reload is pending but `loading` still reads false, and a
  // page handing over from one busy state to this one would flash its data in between.
  const reload = useCallback(() => {
    setLoading(true);
    setAttempt((value) => value + 1);
  }, []);
  return { data, error, loading, reload };
}
