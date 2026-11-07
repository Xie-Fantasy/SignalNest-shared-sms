import {
  createContext, useCallback, useContext, useEffect, useRef, useState,
  type ReactNode,
} from 'react';

const STORAGE_KEY = 'smsmon-refresh';
const ALLOWED = [5000, 10000, 15000, 30000, 60000, 120000];

interface RefreshValue {
  enabled: boolean;
  intervalMs: number;
  tick: number;
  lastRunAt: number;
  setEnabled: (value: boolean) => void;
  setIntervalMs: (ms: number) => void;
  requestRefreshNow: () => void;
  registerRun: () => void;
}

const DEFAULT: RefreshValue = {
  enabled: true, intervalMs: 15000, tick: 0, lastRunAt: 0,
  setEnabled: () => undefined, setIntervalMs: () => undefined,
  requestRefreshNow: () => undefined, registerRun: () => undefined,
};

const Ctx = createContext<RefreshValue>(DEFAULT);

function load(): { enabled: boolean; intervalMs: number } {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      const enabled = parsed.enabled !== false;
      const intervalMs = ALLOWED.includes(parsed.intervalMs) ? parsed.intervalMs : 15000;
      return { enabled, intervalMs };
    }
  } catch {
    /* storage unavailable */
  }
  return { enabled: true, intervalMs: 15000 };
}

export function RefreshProvider({ children }: { children: ReactNode }) {
  const initial = load();
  const [enabled, setEnabledState] = useState(initial.enabled);
  const [intervalMs, setIntervalMsState] = useState(initial.intervalMs);
  const [tick, setTick] = useState(0);
  const [lastRunAt, setLastRunAt] = useState(0);

  const persist = useCallback((nextEnabled: boolean, nextMs: number) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
        enabled: nextEnabled, intervalMs: nextMs,
      }));
    } catch {
      /* ignore */
    }
  }, []);

  const setEnabled = useCallback((value: boolean) => {
    setEnabledState(value);
    persist(value, intervalMs);
  }, [intervalMs, persist]);

  const setIntervalMs = useCallback((ms: number) => {
    setIntervalMsState(ms);
    persist(enabled, ms);
  }, [enabled, persist]);

  const requestRefreshNow = useCallback(() => setTick((t) => t + 1), []);
  const registerRun = useCallback(() => setLastRunAt(Date.now()), []);

  return (
    <Ctx.Provider value={{
      enabled, intervalMs, tick, lastRunAt,
      setEnabled, setIntervalMs, requestRefreshNow, registerRun,
    }}>
      {children}
    </Ctx.Provider>
  );
}

export function useRefresh(): RefreshValue {
  return useContext(Ctx);
}

/** Poll `fn` on the global auto-refresh cadence. Also re-runs on manual
 *  refresh (tick) and when the tab regains visibility. Respects `enabled`. */
export function useAutoRefresh(fn: () => void | Promise<void>, deps: unknown[] = []) {
  const { enabled, intervalMs, tick, registerRun } = useRefresh();
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const busy = useRef(false);

  const run = useCallback(() => {
    if (busy.current) return;
    if (document.visibilityState !== 'visible') return;
    busy.current = true;
    const finish = () => { busy.current = false; registerRun(); };
    try {
      Promise.resolve(fnRef.current()).then(finish, finish);
    } catch {
      finish();
    }
  }, [registerRun]);

  useEffect(() => { run(); /* initial + on dep/tick change */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, tick, ...deps]);

  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(run, intervalMs);
    return () => window.clearInterval(id);
  }, [enabled, intervalMs, run, ...deps]);

  useEffect(() => {
    const onVisible = () => { if (document.visibilityState === 'visible') run(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [run]);
}
