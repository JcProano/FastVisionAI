import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";

export function useApi<T>(path: string, refreshMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const value = await api<T>(path);
      if (mounted.current) {
        setData(value);
        setError(null);
      }
    } catch (reason) {
      if (mounted.current)
        setError(reason instanceof Error ? reason.message : "Sin conexión");
    }
  }, [path]);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const timer =
      refreshMs > 0 ? window.setInterval(refresh, refreshMs) : undefined;
    return () => {
      mounted.current = false;
      if (timer) window.clearInterval(timer);
    };
  }, [refresh, refreshMs]);

  return { data, error, refresh };
}
