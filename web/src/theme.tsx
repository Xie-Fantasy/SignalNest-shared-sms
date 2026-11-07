import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { t } from './i18n';

export type Theme = 'light' | 'dark';
const STORAGE_KEY = 'smsmon-theme';

interface ThemeValue {
  theme: Theme;
  toggle: () => void;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeValue>({
  theme: 'dark', toggle: () => undefined, setTheme: () => undefined,
});

function initialTheme(): Theme {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // storage may be blocked
  }
  try {
    if (window.matchMedia('(prefers-color-scheme: light)').matches) return 'light';
  } catch {
    // matchMedia unavailable
  }
  return 'dark';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.style.colorScheme = theme;
    try { window.localStorage.setItem(STORAGE_KEY, theme); } catch { /* ignore */ }
  }, [theme]);

  const setTheme = (value: Theme) => setThemeState(value);
  const toggle = () => setThemeState((previous) => previous === 'dark' ? 'light' : 'dark');

  return <ThemeContext.Provider value={{ theme, toggle, setTheme }}>
    {children}
  </ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  return useContext(ThemeContext);
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === 'dark' ? t('浅色') : t('深色');
  return (
    <button className="theme-toggle" onClick={toggle}
      aria-label={t('切换到{what}主题', { what: next })} title={t('切换到{what}主题', { what: next })}>
      {theme === 'dark'
        ? <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </svg>
        : <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
          </svg>}
      <span>{next}</span>
    </button>
  );
}
