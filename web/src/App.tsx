import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { api, UNAUTHORIZED_EVENT } from './api';
import {
  EventsPage, ForwardSettingsPage, OverviewPage, QQBotPage, RecordsPage, SettingsPage, SpugPage, SystemPage,
} from './pages';
import { ThemeProvider, ThemeToggle } from './theme';
import { RefreshProvider, useRefresh } from './refresh';
import { I18nProvider, LanguageToggle, localeTag, t, useI18n, useLang } from './i18n';
import type { PageKey } from './types';
import emblem from './assets/emblem.webp';

type NavItem = { key: PageKey; label: string; icon: string };

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: '监控', items: [
      { key: 'overview', label: '总览', icon: 'M3 3h7v7H3V3zm11 0h7v7h-7V3zM3 14h7v7H3v-7zm11 0h7v7h-7v-7z' },
      { key: 'records', label: '投递记录', icon: 'M4 5h16M4 10h16M4 15h16M4 20h10' },
      { key: 'events', label: '事件明细', icon: 'M3 12h4l3 7 4-14 3 7h4' },
    ],
  },
  {
    title: '配置', items: [
      { key: 'qqbot', label: 'QQ 机器人', icon: 'M4 5h16v11H8l-4 4V5z' },
      { key: 'spug', label: 'Spug 通道', icon: 'M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6zm4 9a2 2 0 0 0 4 0' },
      { key: 'forward', label: '转发设置', icon: 'M4 7h10M18 7h2M4 17h2M10 17h10M14 4l3 3-3 3M10 14l-3 3 3 3' },
    ],
  },
  {
    title: '系统', items: [
      { key: 'system', label: '系统信息', icon: 'M3 4h18v6H3V4zm0 10h18v6H3v-6zm3-3h.01M7 17h.01' },
      { key: 'settings', label: '设置', icon: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1l2-1.6-2-3.4-2.4 1a7 7 0 0 0-1.7-1L14.5 3h-4l-.3 2.6a7 7 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a7 7 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 1.7 1l.3 2.6h4l.3-2.6a7 7 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6a7 7 0 0 0 .1-1z' },
    ],
  },
];

const ALL_NAV: NavItem[] = NAV_GROUPS.flatMap((group) => group.items);

/** Brand glyph + themed wordmark. The wordmark is text so it stays legible in
 *  both themes (the supplied lockup PNG has a dark navy wordmark). */
function BrandMark({ size = 30 }: { size?: number }) {
  return <img className="brand-emblem" src={emblem} width={size} height={size}
    alt="" aria-hidden="true" />;
}

function Sidebar({ active, onNavigate, onLogout, username }: {
  active: PageKey; onNavigate: (page: PageKey) => void;
  onLogout: () => void; username: string;
}) {
  return <aside className="sidebar">
    <div className="sidebar-brand">
      <BrandMark />
      <div className="sidebar-brand-text">
        <strong>{t('信栖')}</strong>
        <span>{t('运行监测控制台')}</span>
      </div>
    </div>
    <nav className="sidebar-nav">
      {NAV_GROUPS.map((group) => <div className="nav-group" key={group.title}>
        <div className="nav-group-title">{t(group.title)}</div>
        {group.items.map((item) => (
          <button key={item.key}
            className={'nav-item ' + (active === item.key ? 'active' : '')}
            onClick={() => onNavigate(item.key)}>
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none"
              stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"
              strokeLinejoin="round" aria-hidden="true">
              <path d={item.icon} />
            </svg>
            <span>{t(item.label)}</span>
          </button>
        ))}
      </div>)}
    </nav>
    <div className="sidebar-foot">
      <div className="sidebar-user">
        <span className="user-avatar">{(username || 'A').slice(0, 1).toUpperCase()}</span>
        <span className="user-name">{username || t('已登录')}</span>
        <button className="ghost-button compact" onClick={onLogout}>{t('退出')}</button>
      </div>
    </div>
  </aside>;
}

function MobileTabBar({ active, onNavigate }: { active: PageKey; onNavigate: (page: PageKey) => void }) {
  return <nav className="mobile-tabbar" aria-label={t('页面导航')}>
    {ALL_NAV.map((item) => (
      <button key={item.key}
        className={'tab-item ' + (active === item.key ? 'active' : '')}
        onClick={() => onNavigate(item.key)}>
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none"
          stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"
          strokeLinejoin="round" aria-hidden="true">
          <path d={item.icon} />
        </svg>
        <span>{t(item.label)}</span>
      </button>
    ))}
  </nav>;
}

function RefreshIndicator() {
  const { enabled, intervalMs, lastRunAt, requestRefreshNow } = useRefresh();
  const seconds = Math.round(intervalMs / 1000);
  return (
    <div className="refresh-indicator" title={t('数据自动刷新')}>
      {enabled
        ? <span className="refresh-mode"><i className="dot-live" />{t('自动 {n}s', { n: seconds })}</span>
        : <span className="refresh-mode">{t('手动刷新')}</span>}
      {lastRunAt > 0 && enabled && (
        <span className="muted small">· {t('更新于 ')}{new Date(lastRunAt).toLocaleTimeString(localeTag(), { hour12: false })}</span>
      )}
      <button className="icon-button" onClick={requestRefreshNow} aria-label={t('立即刷新')}>
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
          strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" />
        </svg>
      </button>
    </div>
  );
}

const LOGIN_FEATURES = [
  { key: '端到端投递追踪', icon: 'M4 6h16M4 12h10M4 18h7M18 12l2 2 3-4' },
  { key: '通道健康实时可见', icon: 'M3 12h4l3 7 4-14 3 7h4' },
  { key: '服务器字段完整展示', icon: 'M4 4h16v12H8l-4 4V4z' },
];

function Login({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const { lang } = useI18n();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(''); setBusy(true);
    try { await api.login(username.trim(), password); onSuccess(); }
    catch (err) { setError(err instanceof Error ? err.message : t('登录失败')); setPassword(''); }
    finally { setBusy(false); }
  }

  return <div className="login-page">
    <section className="login-brand" aria-hidden="true">
      <div className="login-brand-grid" />
      <div className="login-brand-inner">
        <div className="login-brand-logo">
          <BrandMark size={44} />
          <span>{t('信栖')}</span>
        </div>
        <div className="login-brand-body">
          <div className="login-eyebrow">SIGNALNEST · SMS GATEWAY</div>
          <h2>{t('短信转发与运行监测')}</h2>
          <p className="muted">{t('统一查看投递链路、通道状态与系统运行情况。')}</p>
          <ul className="login-features">
            {LOGIN_FEATURES.map((feature) => (
              <li key={feature.key}>
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
                  stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"
                  strokeLinejoin="round" aria-hidden="true"><path d={feature.icon} /></svg>
                <span>{t(feature.key)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="login-brand-foot">SignalNest</div>
      </div>
    </section>

    <section className="login-form-side">
      <div className="login-tools">
        <LanguageToggle compact />
        <ThemeToggle />
      </div>
      <form className="login-card" onSubmit={submit}>
        <div className="login-mobile-brand">
          <BrandMark size={34} />
          <span>{t('信栖')}</span>
        </div>
        <div className="login-card-head">
          <div className="login-lock" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
              strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <rect x="4" y="10" width="16" height="11" rx="2" />
              <path d="M8 10V7a4 4 0 0 1 8 0v3" />
            </svg>
          </div>
          <h1>{t('安全登录')}</h1>
          <p className="muted">{t('登录以访问运行监测控制台')}</p>
        </div>

        <label className="field"><span>{t('账号')}</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)}
            autoComplete="username" required maxLength={64} /></label>

        <label className="field"><span>{t('密码')}</span>
          <span className="password-wrap">
            <input type={showPassword ? 'text' : 'password'} value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete="current-password"
              required maxLength={256} placeholder={t('请输入登录密码')} />
            <button type="button" className="password-peek"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? t('隐藏密码') : t('显示密码')}
              title={showPassword ? t('隐藏密码') : t('显示密码')}>
              {showPassword
                ? <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                    strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
                    <path d="M3 3l18 18M10.6 10.7a2 2 0 0 0 2.8 2.8" />
                    <path d="M9.9 5.2A9.6 9.6 0 0 1 12 5c5 0 9 4.5 9 7 0 .8-.6 2-1.6 3.1M6.2 6.7C4.1 8.1 3 10 3 12c0 2.5 4 7 9 7 1.3 0 2.5-.3 3.6-.8" />
                  </svg>
                : <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                    strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
                    <path d="M3 12s3.6-7 9-7 9 7 9 7-3.6 7-9 7-9-7-9-7z" />
                    <circle cx="12" cy="12" r="2.6" />
                  </svg>}
            </button>
          </span></label>

        {error && <div className="alert" role="alert">{t(error)}</div>}
        <button className="primary-button login-submit" type="submit" disabled={busy}>
          {busy ? t('登录中…') : t('登录')}
          {!busy && <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M5 12h14M13 6l6 6-6 6" /></svg>}
        </button>
        <p className="login-card-foot">
          {lang === 'zh' ? 'HttpOnly 签名会话 · 12 小时有效' : 'HttpOnly signed session · valid for 12 hours'}
        </p>
      </form>
    </section>
  </div>;
}

function MainView({ page, setPage, onLogout, username, openTrace, eventQuery }: {
  page: PageKey; setPage: (p: PageKey) => void;
  onLogout: () => void; username: string; openTrace: (trace: string) => void; eventQuery: string;
}) {
  return <div className="app-shell">
    <Sidebar active={page} onNavigate={setPage} onLogout={onLogout} username={username} />
    <div className="main-area">
      <header className="topbar">
        <div className="topbar-left">
          <span className="live-badge"><i />{t('实时')}</span>
          <span className="muted server-host">/monitor/</span>
        </div>
        <div className="topbar-actions">
          <RefreshIndicator />
          <LanguageToggle compact />
          <ThemeToggle />
          <button className="ghost-button" onClick={onLogout}>{t('退出')}</button>
        </div>
      </header>
      <main className="content" key={page}>
        {page === 'overview' && <OverviewPage />}
        {page === 'records' && <RecordsPage onTrace={openTrace} />}
        {page === 'events' && <EventsPage initialQuery={eventQuery} />}
        {page === 'qqbot' && <QQBotPage />}
        {page === 'spug' && <SpugPage />}
        {page === 'forward' && <ForwardSettingsPage />}
        {page === 'system' && <SystemPage />}
        {page === 'settings' && <SettingsPage onPasswordChanged={onLogout} />}
      </main>
    </div>
    <MobileTabBar active={page} onNavigate={setPage} />
  </div>;
}

export default function App() {
  // t() is not a hook, so the root must subscribe to language changes for the
  // whole tree (sidebar, pages, charts) to repaint immediately on toggle.
  useLang();
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [username, setUsername] = useState('');
  const [page, setPage] = useState<PageKey>('overview');
  const [eventQuery, setEventQuery] = useState('');

  useEffect(() => {
    void api.me()
      .then((data) => { setUsername(data.username ?? ''); setAuthed(true); })
      .catch(() => setAuthed(false));
  }, []);

  useEffect(() => {
    const handler = () => setAuthed(false);
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, []);

  async function logout() {
    try { await api.logout(); } catch { /* session gone either way */ }
    setAuthed(false);
  }

  function openTrace(trace: string) {
    setEventQuery(trace);
    setPage('events');
  }

  let content: ReactNode;
  if (authed === null) {
    content = <div className="boot-screen"><BrandMark size={40} />
      <p className="muted">{t('正在连接…')}</p></div>;
  } else if (!authed) {
    content = <Login onSuccess={() => setAuthed(true)} />;
  } else {
    content = <MainView
      page={page} setPage={setPage} onLogout={() => void logout()} username={username}
      openTrace={openTrace} eventQuery={eventQuery} />;
  }
  return (
    <I18nProvider>
      <RefreshProvider>
        <ThemeProvider>
          {content}
        </ThemeProvider>
      </RefreshProvider>
    </I18nProvider>
  );
}
