import { useState, useCallback } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function useFetch() {
  const [data, setData] = useState<unknown | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async <T = unknown>(url: string, options?: RequestInit): Promise<T> => {
    setLoading(true);
    setError(null);
    try {
      const fullUrl = `${API_BASE}${url}`;
      const res = await fetch(fullUrl, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
      });
      if (!res.ok) {
        let message = `HTTP ${res.status} ${res.statusText || ''}`.trim();
        try {
          const body = await res.json();
          if (body) {
            if (typeof body.detail === 'string') {
              message = body.detail;
            } else if (Array.isArray(body.detail)) {
              message = body.detail
                .map((d: any) => (typeof d === 'string' ? d : (d?.msg || d?.message || '')))
                .filter(Boolean)
                .join('; ') || message;
            } else if (body.error) {
              message = typeof body.error === 'string' ? body.error : JSON.stringify(body.error);
            }
          }
        } catch {
          try {
            const text = await res.text();
            if (text) message = text.slice(0, 300);
          } catch {}
        }
        throw new Error(message);
      }
      const result = await res.json();
      setData(result);
      return result;
    } catch (e: any) {
      const msg = e.message || 'Unknown error';
      setError(msg);
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, fetchData, setData };
}
