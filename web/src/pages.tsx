import { QRCodeSVG } from 'qrcode.react';
import type { EChartsCoreOption } from 'echarts/core';
import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { api } from './api';
import { useTheme } from './theme';
import { EChart, ChartEmpty, cssVar } from './EChart';
import { useAutoRefresh, useRefresh } from './refresh';
import {
  bytes, ErrorBanner, formatTime, KeyValue, Metric, OUTCOME_META,
  Pagination, Panel, Pill, RESULT_LABELS, SectionTitle, SOURCE_LABELS,
  STATUS_META, StatusDot,
} from './common';
import type {
  DayBucket, DeliveryRecord, EventItem, Filters, ForwardRoute, Meta, Outcome, Overview,
  Paged, PasswordLoginResult, QQAccounts, QQConfig, QQGroups, QQStatus, QrcodeData,
  QuickLogin, SettingsInfo, SpugStatus, Stats, SystemInfo, TokenStatus,
} from './types';
import { t, useI18n, useLang } from './i18n';
import logoZh from './assets/logo-zh.webp';
import logoEn from './assets/logo-en.webp';
import emblem from './assets/emblem.webp';

const EMPTY_FILTERS: Filters = {
  since: '', until: '', source: '', channel: '', outcome: '', result: '', q: '',
};

/* --------------------------------------------------------------- overview */

type NumericKey = 'delivered' | 'fallback' | 'failed' | 'ignored' | 'unknown' | 'pending';
const SEGMENTS: { key: NumericKey; color: string }[] = [
  { key: 'delivered', color: 'var(--ok)' },
  { key: 'fallback', color: 'var(--info)' },
  { key: 'failed', color: 'var(--danger)' },
  { key: 'unknown', color: 'var(--warn)' },
  { key: 'ignored', color: 'var(--text-subtle)' },
  { key: 'pending', color: 'var(--purple)' },
];
const COLOR_VAR: Record<NumericKey, string> = {
  delivered: '--ok', fallback: '--info', failed: '--danger',
  ignored: '--text-subtle', unknown: '--warn', pending: '--purple',
};

function TrendChart({ days, meta }: { days: DayBucket[]; meta: Meta | null }) {
  const { theme } = useTheme();
  const lang = useLang();
  const option = useMemo<EChartsCoreOption>(() => {
    const textColor = cssVar('--text-muted');
    const axisColor = cssVar('--text-subtle');
    const gridColor = cssVar('--chart-grid');
    const series = SEGMENTS.map((segment) => ({
      name: t(meta?.outcomeLabels?.[segment.key] ?? segment.key),
      type: 'bar' as const,
      stack: 'total',
      barMaxWidth: 36,
      emphasis: { focus: 'series' as const },
      itemStyle: { color: cssVar(COLOR_VAR[segment.key]) },
      data: days.map((day) => day[segment.key]),
    }));
    return {
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'inherit', color: textColor },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        textStyle: { color: textColor }, borderColor: gridColor,
      },
      legend: {
        type: 'scroll', top: 0, icon: 'roundRect',
        textStyle: { color: textColor, fontSize: 11 },
        itemWidth: 10, itemHeight: 10, itemGap: 12,
      },
      grid: { left: 6, right: 10, bottom: 2, top: 36, containLabel: true },
      xAxis: {
        type: 'category',
        data: days.map((day) => day.date.slice(5)),
        axisLine: { lineStyle: { color: gridColor } },
        axisTick: { show: false },
        axisLabel: { color: axisColor, fontSize: 11 },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: gridColor } },
        axisLabel: { color: axisColor, fontSize: 11 },
      },
      series,
    };
  }, [days, theme, meta, lang]);

  if (!days.length) return <ChartEmpty>{t('暂无数据')}</ChartEmpty>;
  return <EChart option={option} height={220} />;
}

export function OverviewPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState('');
  const [updatedAt, setUpdatedAt] = useState('');

  const load = useCallback(async (force = false) => {
    try {
      const [o, s] = await Promise.all([api.overview(force), api.stats(7)]);
      setOverview(o); setStats(s); setUpdatedAt(new Date().toISOString()); setError('');
    } catch (err) { setError(err instanceof Error ? err.message : t('刷新失败')); }
  }, []);

  useEffect(() => {
    void api.meta().then(setMeta).catch(() => undefined);
  }, []);
  useAutoRefresh(() => { void load(); }, []);

  const summary = overview?.summary ?? { online: 0, offline: 0, degraded: 0, unknown: 0, disabled: 0 };
  const today = stats && stats.days.length ? stats.days[stats.days.length - 1] : undefined;

  return <>
    <ErrorBanner message={error} onClose={() => setError('')} />
    <div className="page-head">
      <h1>{t('总览')}</h1>
      <div className="head-actions">
        <span className="muted">{t('更新于 ')}{formatTime(updatedAt)}</span>
        <button className="ghost-button" onClick={() => void load(true)}>{t('立即检测')}</button>
      </div>
    </div>

    <section className="metrics">
      <Metric label={t('在线服务')} value={summary.online} hint={t('共 {n} 项', { n: overview?.services.length ?? 0 })} color="var(--ok)" />
      <Metric label={t('异常 / 降级')} value={summary.offline + summary.degraded}
        hint={t('离线 {o} · 降级 {d}', { o: summary.offline, d: summary.degraded })}
        color={summary.offline + summary.degraded > 0 ? 'var(--danger)' : undefined} />
      <Metric label={t('今日投递记录')} value={today?.total ?? 0} hint={t('按接收时间 UTC 归集')} />
      <Metric label={t('转发成功')} value={today?.delivered ?? 0} color="var(--ok)" />
      <Metric label={t('兜底送达')} value={today?.fallback ?? 0} color="var(--info)" />
      <Metric label={t('失败 / 未知')} value={(today?.failed ?? 0) + (today?.unknown ?? 0)} color="var(--danger)" />
    </section>

    <Panel title={t('服务状态')}
      extra={<div className="status-legend">
        {Object.entries(STATUS_META).map(([key, value]) => (
          <span key={key}><i style={{ background: value.color }} />{t(value.label)}</span>
        ))}
      </div>}>
      <div className="service-grid">
        {(overview?.services ?? []).map((item) => (
          <div className={'service-card status-' + item.status} key={item.id}>
            <div className="service-head">
              <StatusDot status={item.status} />
              <span className="service-name">{t(item.name)}</span>
              <span className="service-group">{t(item.group)}</span>
              <span className="service-state" style={{ color: STATUS_META[item.status]?.color }}>
                {t(STATUS_META[item.status]?.label ?? item.status)}
              </span>
            </div>
            <div className="service-detail">{t(item.detail || '—')}</div>
            <div className="service-foot"><span>{t('耗时 {n} ms', { n: item.latencyMs })}</span><span>{formatTime(item.checkedAt)}</span></div>
          </div>
        ))}
        {!overview && <div className="muted">{t('正在检测服务状态…')}</div>}
      </div>
    </Panel>

    <Panel title={t('近 7 天投递结果')}>
      <TrendChart days={stats?.days ?? []} meta={meta} />
    </Panel>
  </>;
}

/* ------------------------------------------------------- records & events */

function FiltersBar({ filters, onChange, mode, meta }: {
  filters: Filters; onChange: (key: keyof Filters, value: string) => void;
  mode: 'records' | 'events'; meta: Meta | null;
}) {
  const channels = useMemo(() => Object.entries(meta?.channelLabels ?? {}), [meta]);
  const outcomes = useMemo(() => Object.entries(meta?.outcomeLabels ?? {}), [meta]);
  return <div className="filters">
    <label>{t('起始')} <input type="date" value={filters.since}
      onChange={(e) => onChange('since', e.target.value)} /></label>
    <label>{t('截止')} <input type="date" value={filters.until}
      onChange={(e) => onChange('until', e.target.value)} /></label>
    <label>{t('来源')} <select value={filters.source} onChange={(e) => onChange('source', e.target.value)}>
      <option value="">{t('全部')}</option><option value="iphone">iPhone</option>
      <option value="android">Android</option><option value="system">{t('系统')}</option>
    </select></label>
    <label>{t('通道')} <select value={filters.channel} onChange={(e) => onChange('channel', e.target.value)}>
      <option value="">{t('全部')}</option>
      {channels.map(([key, label]) => <option key={key} value={key}>{t(label)}</option>)}
    </select></label>
    <label>{t('结果')} <select value={mode === 'records' ? filters.outcome : filters.result}
      onChange={(e) => onChange(mode === 'records' ? 'outcome' : 'result', e.target.value)}>
      <option value="">{t('全部')}</option>
      {mode === 'records'
        ? outcomes.map(([key, label]) => <option key={key} value={key}>{t(label)}</option>)
        : Object.entries(RESULT_LABELS).map(([key, label]) => <option key={key} value={key}>{t(label)}</option>)}
    </select></label>
    <label className="search-field">{t('关键词')} <input placeholder={t('发件人 / 号码 / 对象 / trace')}
      value={filters.q} onChange={(e) => onChange('q', e.target.value)} /></label>
  </div>;
}

function TableShell({ head, children }: { head: ReactNode; children: ReactNode }) {
  return <div className="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{children}</tbody></table></div>;
}

export function RecordsPage({ onTrace }: { onTrace: (trace: string) => void }) {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paged<DeliveryRecord> | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setData(await api.records(filters, page, 20)); setError(''); }
    catch (err) { setError(err instanceof Error ? err.message : t('加载失败')); }
  }, [filters, page]);

  useEffect(() => { void api.meta().then(setMeta).catch(() => undefined); }, [load]);
  useAutoRefresh(() => { void load(); }, [load]);

  const update = (key: keyof Filters, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value })); setPage(1);
  };

  return <>
    <ErrorBanner message={error} onClose={() => setError('')} />
    <div className="page-head">
      <h1>{t('投递记录')}</h1>
      <button className="ghost-button" onClick={() => { setFilters(EMPTY_FILTERS); setPage(1); }}>{t('重置筛选')}</button>
    </div>
    <Panel title={t('筛选')}>
      <FiltersBar filters={filters} onChange={update} mode="records" meta={meta} />
      {data && <TableShell head={<>
        <th>{t('时间')}</th><th>{t('来源')}</th><th>{t('发件人')}</th><th>{t('接收号')}</th>
        <th>{t('发送对象')}</th><th>{t('结果')}</th><th>{t('链路')}</th>
      </>}>
        {data.items.length === 0 && <tr><td colSpan={7} className="empty-row">{t('没有符合条件的记录')}</td></tr>}
        {data.items.map((row) => {
          const style = OUTCOME_META[row.outcome] ?? OUTCOME_META.unknown;
          const open = expanded === row.trace;
          return <Rows key={row.trace} open={open} row={row} style={style}
            onToggle={() => setExpanded(open ? null : row.trace)} onTrace={onTrace} />;
        })}
      </TableShell>}
      {data && <Pagination page={data.page} pages={data.pages} total={data.total}
        size={data.size} onPage={setPage} />}
    </Panel>
  </>;
}

function Rows({ row, open, style, onToggle, onTrace }: {
  row: DeliveryRecord; open: boolean; style: { color: string; background: string };
  onToggle: () => void; onTrace: (trace: string) => void;
}) {
  return <>
    <tr className={'data-row ' + (open ? 'opened' : '')} onClick={onToggle}>
      <td className="nowrap">{formatTime(row.ts)}</td>
      <td><span className="source-tag">{t(SOURCE_LABELS[row.source] ?? row.source)}</span></td>
      <td className="mono">{row.sender || '—'}</td>
      <td className="mono">{row.recipient || '—'}</td>
      <td>{row.target || '—'}</td>
      <td><Pill color={style.color} background={style.background}>{t(row.outcomeLabel)}</Pill></td>
      <td className="muted nowrap">{t('{n} 个事件', { n: row.count })} <span className="chev">{open ? '▾' : '▸'}</span></td>
    </tr>
    {open && <tr className="detail-row"><td colSpan={7}>
      <div className="trace-line">
        <span className="trace-id">trace {row.trace}</span>
        {row.stageLabels.map((label, index) => <span className="trace-step" key={index}><i />{t(label)}</span>)}
        {row.note && !row.note.includes('legacy_masked') && <span className="muted">{t('说明 ')}{t(row.note)}</span>}
        {row.note.includes('legacy_masked') &&
          <span className="chip small legacy" title={t('当时的日志未采集完整号码，无法还原')}>{t('历史号码未采集')}</span>}
        <button className="link-button" onClick={(e) => { e.stopPropagation(); onTrace(row.trace); }}>{t('按此记录筛选')}</button>
      </div>
    </td></tr>}
  </>;
}

export function EventsPage({ initialQuery }: { initialQuery?: string }) {
  const [filters, setFilters] = useState<Filters>({ ...EMPTY_FILTERS, q: initialQuery ?? '' });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paged<EventItem> | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (initialQuery !== undefined) { setFilters((prev) => ({ ...prev, q: initialQuery })); setPage(1); }
  }, [initialQuery]);

  const load = useCallback(async () => {
    try { setData(await api.events(filters, page, 30)); setError(''); }
    catch (err) { setError(err instanceof Error ? err.message : t('加载失败')); }
  }, [filters, page]);
  useEffect(() => { void api.meta().then(setMeta).catch(() => undefined); }, [load]);
  useAutoRefresh(() => { void load(); }, [load]);

  const update = (key: keyof Filters, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value })); setPage(1);
  };

  return <>
    <ErrorBanner message={error} onClose={() => setError('')} />
    <div className="page-head">
      <h1>{t('事件明细')}</h1>
      <button className="ghost-button" onClick={() => { setFilters(EMPTY_FILTERS); setPage(1); }}>{t('重置筛选')}</button>
    </div>
    <Panel title={t('筛选')}>
      <FiltersBar filters={filters} onChange={update} mode="events" meta={meta} />
      {data && <TableShell head={<>
        <th>{t('时间')}</th><th>{t('阶段')}</th><th>{t('通道')}</th><th>{t('结果')}</th>
        <th>{t('发件人')}</th><th>{t('接收号')}</th><th>{t('发送对象')}</th><th>{t('说明')}</th>
      </>}>
        {data.items.length === 0 && <tr><td colSpan={8} className="empty-row">{t('没有符合条件的事件')}</td></tr>}
        {data.items.map((row, index) => {
          const outcome: Outcome = row.result === 'ok' ? 'delivered'
            : row.result === 'failed' ? 'failed'
            : row.result === 'ignored' ? 'ignored'
            : row.result === 'unknown' ? 'unknown' : 'pending';
          const style = OUTCOME_META[outcome] ?? OUTCOME_META.unknown;
          return <tr className="data-row static-row" key={row.trace + row.ts + index}>
            <td className="nowrap">{formatTime(row.ts)}</td>
            <td>{t(row.stageLabel)}</td>
            <td className="muted">{t(row.channelLabel)}</td>
            <td><Pill color={style.color} background={style.background}>
              {t(RESULT_LABELS[row.result] ?? row.result)}</Pill></td>
            <td className="mono">{row.sender || '—'}</td>
            <td className="mono">{row.recipient || '—'}</td>
            <td>{row.target || '—'}</td>
            <td className="muted">
              {row.note.includes('legacy_masked') ? t('历史回填')
                : (row.note || (row.origin === 'backfill' ? t('历史回填') : '—'))}
              {row.note.includes('legacy_masked') &&
                <span className="chip small legacy" title={t('当时的日志未采集完整号码，无法还原')}>{t('号码未采集')}</span>}
            </td>
          </tr>;
        })}
      </TableShell>}
      {data && <Pagination page={data.page} pages={data.pages} total={data.total}
        size={data.size} onPage={setPage} />}
    </Panel>
  </>;
}

/* ------------------------------------------------------------- QQ bot page */

export function QQBotPage() {
  const [status, setStatus] = useState<QQStatus | null>(null);
  const [qrcode, setQrcode] = useState<QrcodeData | null>(null);
  const [groups, setGroups] = useState<QQGroups | null>(null);
  const [quick, setQuick] = useState<QuickLogin | null>(null);
  const [config, setConfig] = useState<QQConfig | null>(null);
  const [groupInput, setGroupInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loginUin, setLoginUin] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginResult, setLoginResult] = useState<PasswordLoginResult | null>(null);
  const [loginBusy, setLoginBusy] = useState(false);

  // Restart / force-refresh / account switching
  const [accounts, setAccounts] = useState<QQAccounts | null>(null);
  const [restarting, setRestarting] = useState(false);
  const [restartMsg, setRestartMsg] = useState('');
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [switching, setSwitching] = useState('');
  const [switchMsg, setSwitchMsg] = useState('');
  const [acctLabel, setAcctLabel] = useState('');
  const [acctUin, setAcctUin] = useState('');
  const [acctPassword, setAcctPassword] = useState('');
  const [acctBusy, setAcctBusy] = useState(false);
  const [acctMsg, setAcctMsg] = useState('');

  const loadStatus = useCallback(async (force = false) => {
    try { setStatus(await api.qqStatus(force)); } catch { /* keep last state */ }
  }, []);
  const loadAccounts = useCallback(async () => {
    try { setAccounts(await api.qqAccounts()); } catch { /* keep last state */ }
  }, []);
  const loadQr = useCallback(async () => {
    try { setQrcode(await api.qqQrcode()); } catch { setQrcode(null); }
  }, []);
  const loadGroups = useCallback(async () => {
    try { setGroups(await api.qqGroups()); } catch { /* keep last state */ }
  }, []);
  const loadConfig = useCallback(async () => {
    try {
      const value = await api.qqConfig();
      setConfig(value);
      setGroupInput(value.targetGroup);
      setLoginUin((previous) => previous || value.botQq);
    } catch { /* keep last state */ }
  }, []);

  useAutoRefresh(() => {
    void loadStatus();
    void loadGroups();
    void loadConfig();
    void loadAccounts();
    void api.qqQuickLogin().then(setQuick).catch(() => undefined);
  }, []);

  // QR auto-poll is declared below, after `isLoggedIn` is computed.

  async function refreshQr() {
    try { setQrcode(await api.qqQrcodeRefresh()); setError(''); }
    catch (err) { setError(err instanceof Error ? err.message : t('刷新失败')); }
  }

  async function submitPasswordLogin(event: FormEvent) {
    event.preventDefault();
    setLoginBusy(true); setError(''); setLoginResult(null);
    try {
      const result = await api.qqPasswordLogin(loginUin.trim(), loginPassword);
      setLoginResult(result);
      setLoginPassword('');
      if (result.ok) void loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('登录请求失败'));
      setLoginPassword('');
    } finally { setLoginBusy(false); }
  }

  async function saveGroup() {
    if (!/^\d{5,12}$/.test(groupInput.trim())) { setError(t('群号必须为 5-12 位数字')); return; }
    setSaving(true); setError('');
    try {
      await api.qqConfigSave(groupInput.trim());
      setMessage(t('已保存，短信服务下次转发前自动生效，无需重启'));
      await Promise.all([loadConfig(), loadGroups()]);
    } catch (err) { setError(err instanceof Error ? err.message : t('保存失败')); }
    finally { setSaving(false); }
  }

  async function restartOnebot() {
    if (restarting) return;
    setConfirmRestart(false);
    setRestarting(true); setRestartMsg(''); setError('');
    try {
      const result = await api.qqRestart();
      // NapCat does NOT keep the login session across a restart: the bot comes
      // back logged out (verified in production). Say so instead of implying a
      // silent recovery.
      setRestartMsg((result.message || t('已请求重启')) +
        t('；重启期间会断开当前登录，恢复后需要用扫码或账号密码重新登录。'));
      setStatus((prev) => prev ? { ...prev } : prev);
      // Re-probe immediately (force) so the UI reflects the new state quickly.
      await new Promise((r) => setTimeout(r, 2500));
      await loadStatus(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('重启请求失败'));
    } finally { setRestarting(false); }
  }

  async function forceRefreshStatus() {
    try { await loadStatus(true); setSwitchMsg(''); } catch (err) {
      setError(err instanceof Error ? err.message : t('刷新失败'));
    }
  }

  async function switchAccount(accountId: string) {
    if (switching) return;
    setSwitching(accountId); setSwitchMsg('');
    try {
      const result = await api.qqSwitch(accountId);
      setSwitchMsg(result.message + (result.uin ? '（' + result.uin + '）' : ''));
      await new Promise((r) => setTimeout(r, 1500));
      await Promise.all([loadStatus(true), loadAccounts()]);
    } catch (err) {
      setSwitchMsg(t('切换失败：') + (err instanceof Error ? err.message : t('未知错误')));
    } finally { setSwitching(''); }
  }

  async function saveAccount(event: FormEvent) {
    event.preventDefault();
    if (!/^\d{5,12}$/.test(acctUin.trim())) { setAcctMsg(t('QQ 号必须为 5-12 位数字')); return; }
    setAcctBusy(true); setAcctMsg('');
    try {
      await api.qqAccountSave(acctLabel.trim() || acctUin.trim(), acctUin.trim(), acctPassword);
      setAcctMsg(t('已保存账号，可在「当前账号」面板一键切换'));
      setAcctLabel(''); setAcctUin(''); setAcctPassword('');
      await loadAccounts();
    } catch (err) { setAcctMsg(err instanceof Error ? err.message : t('保存失败')); }
    finally { setAcctBusy(false); }
  }

  async function deleteAccount(accountId: string) {
    try { await api.qqAccountDelete(accountId); await loadAccounts(); }
    catch (err) { setError(err instanceof Error ? err.message : t('删除失败')); }
  }

  const login = status?.login;
  const isLoggedIn = Boolean(login?.isLogin);
  // QR code only needs to refresh quickly while waiting for a scan; once logged
  // in it is irrelevant, so stop polling to avoid needless requests.
  useEffect(() => {
    void loadQr();
    if (isLoggedIn) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void loadQr();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [isLoggedIn, loadQr]);
  const botState = (status?.state === 'online' || status?.state === 'degraded') ? status.state : 'offline';
  const stateMeta = STATUS_META[botState as keyof typeof STATUS_META] ?? STATUS_META.offline;
  const phaseLabel: Record<string, string> = {
    waiting_qrcode: t('等待扫码'), qrcode_scanned: t('已扫码 等待确认'),
    qrcode_generating: t('正在生成二维码'), generating_qrcode: t('正在生成二维码'),
    login_success: t('登录成功'), initializing: t('初始化中'), reconnecting: t('重连中'),
  };

  // Shared by both branches: when the bot is logged out (e.g. right after a
  // restart) this is the fastest way back in - pick a saved account and its
  // stored password logs in without retyping.
  const accountPanel = (
    <Panel title={t('多账号切换')}>
      <p className="muted small">{t('当当前 QQ 机器人不可用时，可一键切换到已保存的备用账号（保存密码的账号可免输密码切换）。')}</p>
      <div className="account-list">
        {(accounts?.accounts ?? []).length === 0 && (
          <p className="muted small">{t('尚未添加备用账号，可在下方添加。')}</p>
        )}
        {(accounts?.accounts ?? []).map((acc) => (
          <div className={'account-row ' + (acc.isActive ? 'active' : '')} key={acc.id}>
            <div className="account-main">
              <strong>{acc.label}</strong>
              <span className="mono">{acc.uin}</span>
              {acc.hasPassword && <span className="chip small">{t('已存密码')}</span>}
            </div>
            <div className="account-actions">
              {acc.isActive
                ? <span className="chip small">{t('当前')}</span>
                : <button className="primary-button compact" disabled={switching === acc.id}
                    onClick={() => void switchAccount(acc.id)}>
                    {switching === acc.id ? t('切换中…') : t('切换')}</button>}
              <button className="ghost-button compact" onClick={() => void deleteAccount(acc.id)}>{t('删除')}</button>
            </div>
          </div>
        ))}
      </div>
      <form className="account-add" onSubmit={saveAccount}>
        <input value={acctLabel} onChange={(e) => setAcctLabel(e.target.value)}
          placeholder={t('备注名（如 备用小号）')} maxLength={40} />
        <input value={acctUin} onChange={(e) => setAcctUin(e.target.value)}
          placeholder={t('QQ 号')} inputMode="numeric" maxLength={12} />
        <input type="password" value={acctPassword} onChange={(e) => setAcctPassword(e.target.value)}
          placeholder={t('密码（可选·存后一键切换）')} autoComplete="off" maxLength={128} />
        <button className="primary-button compact" type="submit" disabled={acctBusy}>
          {acctBusy ? t('保存中…') : t('添加账号')}</button>
      </form>
      {acctMsg && <div className="result-line ok">{acctMsg}</div>}
    </Panel>
  );

  return <>
    <ErrorBanner message={error} onClose={() => setError('')} />
    {message && <div className="success-banner">{message}
      <button className="link-button" onClick={() => setMessage('')}>{t('关闭')}</button></div>}
    <div className="page-head">
      <div className="page-head-title">
        <h1>{t('QQ 机器人')}</h1>
        <span className={'state-badge ' + botState}><i />{t(stateMeta.label)}</span>
      </div>
      <div className="head-actions">
        <button className="ghost-button" onClick={() => void forceRefreshStatus()}>{t('刷新状态')}</button>
        <button className={'primary-button compact ' + ((botState === 'degraded' || botState === 'offline') ? 'warn' : '')}
          onClick={() => setConfirmRestart(true)} disabled={restarting}>
          {restarting ? t('重启中…') : t('重启 OneBot')}
        </button>
      </div>
    </div>
    {confirmRestart && (
      <div className="confirm-strip">
        <div className="confirm-text">
          <strong>{t('确认重启 OneBot？')}</strong>
          <span>{t('重启会断开当前 QQ 登录，恢复后需要用扫码或账号密码重新登录；期间短信转发暂停约 30 秒。')}</span>
        </div>
        <div className="confirm-actions">
          <button className="ghost-button compact" onClick={() => setConfirmRestart(false)}>{t('取消')}</button>
          <button className="primary-button compact warn" onClick={() => void restartOnebot()}>{t('确认重启')}</button>
        </div>
      </div>
    )}
    {restartMsg && <div className="success-banner">{restartMsg}
      <button className="link-button" onClick={() => setRestartMsg('')}>{t('关闭')}</button></div>}
    {switchMsg && <div className="success-banner">{switchMsg}
      <button className="link-button" onClick={() => setSwitchMsg('')}>{t('关闭')}</button></div>}

    {!isLoggedIn ? (
      <>
      <div className="two-col">
        <Panel title={t('扫码登录')}
          extra={<button className="ghost-button" onClick={() => void refreshQr()}>{t('刷新二维码')}</button>}>
          <div className="qrcode-box">
            {qrcode?.url
              ? <><QRCodeSVG value={qrcode.url} size={208} level="M" includeMargin
                  bgColor="#ffffff" fgColor="#0b1220" />
                <p className="muted">{t('阶段：')}{t(phaseLabel[qrcode.loginPhase] ?? qrcode.loginPhase)}</p>
                <p className="muted small">{qrcode.qrLoginAccepted ? t('已扫码，请在手机上确认登录') : t('等待扫码')}</p></>
              : <div className="qrcode-empty">{t('当前没有可显示的二维码')}<br /><span className="muted">{t('可点击「刷新二维码」重新生成')}</span></div>}
          </div>
        </Panel>

        <Panel title={t('账号密码登录')}>
          <form className="login-form-grid" onSubmit={submitPasswordLogin}>
            <label>{t('QQ 号')}
              <input value={loginUin} onChange={(e) => setLoginUin(e.target.value)}
                inputMode="numeric" maxLength={12} required /></label>
            <label>{t('密码')}
              <input type="password" value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                autoComplete="off" maxLength={128} required /></label>
            <button className="primary-button compact" type="submit" disabled={loginBusy}>
              {loginBusy ? t('提交中…') : t('提交登录')}
            </button>
          </form>
          {loginResult && <div className={'result-line ' + (loginResult.ok ? 'ok' : 'warn')}>
            {loginResult.message}
          </div>}
        </Panel>
      </div>
      {accountPanel}
      </>
    ) : (
      <>
        <div className="two-col">
          <Panel title={t('登录账号')}>
            <KeyValue items={[
              [t('机器人 QQ'), status?.bot?.uin || status?.config?.botQq || '—'],
              [t('昵称'), status?.bot?.nickname || status?.loginInfo?.nick || '—'],
              [t('核心状态'), login?.coreReady ? t('已就绪') : t('登录中')],
              [t('登录阶段'), (login && (phaseLabel[login.loginPhase] ?? login.loginPhase)) || '—'],
              [t('检查时间'), formatTime(status?.checkedAt ?? '')],
            ]} />
            {quick && quick.count > 0 && <div className="sub-block">
              <SectionTitle>{t('快速登录列表')}</SectionTitle>
              <div className="chip-list">{quick.items.map((item, index) => (
                <span className="chip" key={index}>{item.nick || item.nickname || item.uin} · {item.uin}</span>
              ))}</div>
            </div>}
          </Panel>

          <Panel title={t('转发群设置')}>
            <KeyValue items={[
              [t('当前目标群'), config?.targetGroup ?? '—'],
              [t('配置来源'), config?.targetGroupSource === 'runtime' ? t('独立配置文件') : t('环境变量 .env')],
              [t('最近更新'), config?.targetGroupUpdatedAt ? formatTime(config.targetGroupUpdatedAt) : '—'],
              [t('转发开关'), config?.forwardEnabled || '—'],
            ]} />
            <div className="inline-form">
              <input value={groupInput} onChange={(e) => setGroupInput(e.target.value)}
                placeholder={t('输入群号')} maxLength={12} />
              <button className="primary-button compact" disabled={saving} onClick={() => void saveGroup()}>
                {saving ? t('保存中…') : t('保存群号')}
              </button>
            </div>
            {groups?.available
              ? <div className="group-list" style={{ marginTop: 12 }}>
                  {(groups.groups ?? []).map((group) => (
                    <button key={group.groupId}
                      className={'group-item ' + (group.current ? 'selected' : '')}
                      onClick={() => setGroupInput(group.groupId)}>
                      <span className="mono">{group.groupId}</span>
                      <span>{group.groupName}</span>
                      {group.memberCount != null && <span className="muted">{t('{n} 人', { n: group.memberCount })}</span>}
                      {group.current && <span className="chip small">{t('当前')}</span>}
                    </button>
                  ))}
                </div>
              : <p className="muted" style={{ marginTop: 12 }}>{t(groups?.hint ?? t('机器人离线，暂不能拉取群列表'))}</p>}
          </Panel>
        </div>

        {accountPanel}

        <Panel title={t('连接信息')}>
          <KeyValue items={[
            [t('机器人 QQ'), config?.botQq || '—'],
            [t('目标类型'), config?.targetType || '—'],
            [t('OneBot 地址'), config?.onebotUrl || '—'],
            [t('WebUI 地址'), config?.webuiUrl || '—'],
            [t('配置文件'), config?.runtimeConfigPath || '—'],
          ]} />
        </Panel>
      </>
    )}
  </>;
}

/* ----------------------------------------------------- Forward route (ladder) */

export function ForwardSettingsPage() {
  const [route, setRoute] = useState<ForwardRoute | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  useEffect(() => {
    void api.forwardRoute()
      .then(setRoute)
      .catch((err) => setError(err instanceof Error ? err.message : t('加载失败')));
  }, []);

  function move(index: number, dir: -1 | 1) {
    if (!route) return;
    const next = route.channels.slice();
    const target = index + dir;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    setRoute({ ...route, channels: next });
  }

  function toggle(key: string) {
    if (!route) return;
    setRoute({
      ...route,
      channels: route.channels.map((c) =>
        c.key === key ? { ...c, enabled: !c.enabled } : c),
    });
  }

  function onDrop(targetIndex: number) {
    if (!route || dragIndex === null || dragIndex === targetIndex) {
      setDragIndex(null);
      return;
    }
    const next = route.channels.slice();
    const [moved] = next.splice(dragIndex, 1);
    next.splice(targetIndex, 0, moved);
    setRoute({ ...route, channels: next });
    setDragIndex(null);
  }

  async function save() {
    if (!route) return;
    setSaving(true); setError(''); setMessage('');
    try {
      const result = await api.forwardRouteSave(
        route.channels.map((c) => ({ key: c.key, enabled: c.enabled })));
      setRoute({ ...route, channels: result.channels });
      setMessage(t('已保存，网关下次转发前自动生效，无需重启'));
    } catch (err) { setError(err instanceof Error ? err.message : t('保存失败')); }
    finally { setSaving(false); }
  }

  return <>
    <ErrorBanner message={error} onClose={() => setError('')} />
    {message && <div className="success-banner">{message}
      <button className="link-button" onClick={() => setMessage('')}>{t('关闭')}</button></div>}
    <div className="page-head">
      <div className="page-head-title"><h1>{t('转发设置')}</h1></div>
    </div>
    <Panel title={t('短信转发方式（优先级阶梯）')}>
      <p className="muted small">{t('短信到达后按从上到下的顺序尝试每个')}<b>{t('已启用')}</b>{t('的渠道；某个渠道失败会自动尝试下一个。拖动行或点箭头调整顺序，关闭开关可跳过该渠道。')}</p>
      {!route
        ? <p className="muted">{t('加载中…')}</p>
        : <div className="ladder">
            {route.channels.map((ch, index) => (
              <div key={ch.key}
                className={'ladder-row ' + (ch.enabled ? '' : 'off')}
                draggable
                onDragStart={() => setDragIndex(index)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDrop(index)}>
                <span className="ladder-order">{index + 1}</span>
                <span className="ladder-grip" aria-hidden="true">⠿</span>
                <div className="ladder-info">
                  <strong>{ch.label}</strong>
                  <span className="muted small">{ch.desc}</span>
                </div>
                <label className="switch">
                  <input type="checkbox" checked={ch.enabled} onChange={() => toggle(ch.key)} />
                  <span className="slider" />
                </label>
                <div className="ladder-move">
                  <button className="icon-button" disabled={index === 0}
                    onClick={() => move(index, -1)} aria-label={t('上移')}>↑</button>
                  <button className="icon-button" disabled={index === route.channels.length - 1}
                    onClick={() => move(index, 1)} aria-label={t('下移')}>↓</button>
                </div>
              </div>
            ))}
          </div>}
      <div className="form-actions">
        <button className="primary-button" disabled={saving || !route} onClick={() => void save()}>
          {saving ? t('保存中…') : t('保存转发规则')}
        </button>
      </div>
    </Panel>
  </>;
}

/* --------------------------------------------------------------- Spug page */

const BALANCE_FIELDS: [string, string, string][] = [
  ['money_balance', t('资金余额'), t('元')],
  ['sms_resource_balance', t('短信资源包'), t('条')],
  ['voice_resource_balance', t('语音资源包'), t('分钟')],
  ['mail_resource_balance', t('邮件资源包'), t('封')],
  ['wx_mp_resource_balance', t('公众号资源包'), t('条')],
];

export function SpugPage() {
  const [status, setStatus] = useState<SpugStatus | null>(null);
  const [token, setToken] = useState<TokenStatus | null>(null);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async (force = false) => {
    try {
      const [s, t] = await Promise.all([api.spugStatus(force), api.spugToken()]);
      setStatus(s); setToken(t); setError('');
    } catch (err) { setError(err instanceof Error ? err.message : t('加载失败')); }
  }, []);

  useAutoRefresh(() => { void load(); }, []);

  async function saveToken() {
    if (input.trim().length < 8) { setError(t('Token 长度不足')); return; }
    setBusy(true); setError('');
    try {
      await api.spugTokenSave(input.trim());
      setInput(''); setMessage(t('开发者 Token 已保存到服务器（600 权限），页面不会回显'));
      await load(true);
    } catch (err) { setError(err instanceof Error ? err.message : t('保存失败')); }
    finally { setBusy(false); }
  }
  async function clearToken() {
    setBusy(true);
    try { await api.spugTokenDelete(); setMessage(t('Token 已清除')); await load(true); }
    catch (err) { setError(err instanceof Error ? err.message : t('清除失败')); }
    finally { setBusy(false); }
  }

  const balance = status?.balance;

  return <>
    <ErrorBanner message={error} onClose={() => setError('')} />
    {message && <div className="success-banner">{message}
      <button className="link-button" onClick={() => setMessage('')}>{t('关闭')}</button></div>}
    <div className="page-head">
      <h1>{t('Spug 通道')}</h1>
      <div className="head-actions">
        <span className="muted">{t('检查于 ')}{formatTime(status?.checkedAt ?? '')}</span>
        <button className="ghost-button" onClick={() => void load(true)}>{t('强制刷新额度')}</button>
      </div>
    </div>

    <Panel title={t('账户额度')}
      extra={<Pill color={status?.reachable ? 'var(--ok)' : 'var(--danger)'}
        background={status?.reachable ? 'var(--ok-weak)' : 'var(--danger-weak)'}>
        {status?.reachable ? t('通道可达') : t('通道不可达')}</Pill>}>
      {!status?.configured && <div className="empty-state">

        {t('尚未配置开发者 Token。')}
        <a href="https://push.spug.cc/" target="_blank" rel="noreferrer"
          className="link-button">{t('打开 Spug 控制台')}</a>

        {t('在「凭证管理」复制开发者 Token，粘贴到下方即可显示真实额度。')}
      </div>}
      {status?.configured && !balance && <div className="empty-state">
        {t('额度暂不可用')}{status.balanceError ? '：' + t(status.balanceError) : ''}{t('（接口限流或 Token 无效时会自动重试）。')}
      </div>}
      {balance && <div className="balance-grid">
        {BALANCE_FIELDS.map(([key, label, unit]) => (
          <div className="balance-card" key={key}>
            <div className="metric-label">{label}</div>
            <div className="balance-value">{balance[key] ?? '—'}</div>
            <div className="metric-hint">{unit}</div>
          </div>
        ))}
      </div>}
    </Panel>

    <div className="two-col">
      <Panel title={t('开发者 Token')}>
        <KeyValue items={[
          [t('配置状态'), token?.configured ? t('已配置') : t('未配置')],
          [t('更新时间'), token?.updatedAt ? formatTime(token.updatedAt) : '—'],
          [t('存储路径'), status?.tokenPath || '—'],
        ]} />
        <div className="inline-form">
          <input type="password" value={input} onChange={(e) => setInput(e.target.value)}
            placeholder={t('粘贴开发者 Token（不会回显）')} maxLength={256} />
          <button className="primary-button compact" disabled={busy} onClick={() => void saveToken()}>{t('保存')}</button>
          <button className="ghost-button" disabled={busy || !token?.configured}
            onClick={() => void clearToken()}>{t('清除')}</button>
          <a href="https://push.spug.cc/" target="_blank" rel="noreferrer"
            className="ghost-button">{t('控制台')}</a>
        </div>
      </Panel>

      <Panel title={t('投递统计')}>
        <div className="metrics compact-metrics">
          <Metric label={t('近 24h 成功')} value={status?.delivery.last24h.sent ?? 0} color="var(--ok)" />
          <Metric label={t('近 24h 失败')} value={status?.delivery.last24h.failed ?? 0} color="var(--danger)" />
          <Metric label={t('近 7d 成功')} value={status?.delivery.last7d.sent ?? 0} color="var(--ok)" />
          <Metric label={t('近 7d 失败')} value={status?.delivery.last7d.failed ?? 0} color="var(--danger)" />
        </div>
        <SectionTitle>{t('模板与地址')}</SectionTitle>
        <KeyValue items={Object.entries(status?.templates ?? {}).map(
          ([key, value]): [string, ReactNode] => [
            key === 'code' ? t('验证码转发模板') : key === 'notify' ? t('掉线提醒模板') : t('定时告警模板'),
            <span className="mono wrap" key={key}>{value.url || '—'}</span>,
          ])} />
      </Panel>
    </div>
  </>;
}

/* ------------------------------------------------------------- System page */

export function SystemPage() {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { setInfo(await api.systemInfo()); setError(''); }
    catch (err) { setError(err instanceof Error ? err.message : t('加载失败')); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return <>
    <ErrorBanner message={error} onClose={() => setError('')} />
    <div className="page-head">
      <h1>{t('系统信息')}</h1>
      <button className="ghost-button" onClick={() => void load()}>{t('刷新')}</button>
    </div>

    {info && <>
      <Panel title={t('主机')}>
        <KeyValue items={[
          [t('公网 IP'), info.host], [t('主机名'), info.hostname],
          [t('操作系统'), info.os], [t('内核'), info.kernel], [t('架构'), info.architecture],
          ['Python', info.python], [t('运行时长'), info.uptime],
          [t('负载'), info.loadAverage.map((v) => v.toFixed(2)).join(' / ')],
          [t('内存总量'), info.memory.MemTotal || '—'], [t('可用内存'), info.memory.MemAvailable || '—'],
          [t('磁盘'), `${bytes(info.disk.used)} / ${bytes(info.disk.total)} (${info.disk.percent}%)`],
        ]} />
      </Panel>

      <div className="two-col">
        <Panel title={t('服务状态')}>
          <div className="kv-grid">
            {info.services.map((service) => (
              <div className="kv-row" key={service.unit}>
                <span className="kv-key">{service.unit}</span>
                <span className="kv-value">
                  <Pill color={service.active === 'active' ? 'var(--ok)' : 'var(--text-subtle)'}
                    background={service.active === 'active' ? 'var(--ok-weak)' : 'var(--surface-2)'}>
                    {service.active}</Pill> <span className="muted">{service.enabled}</span>
                </span>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title={t('容器与证书')}>
          <SectionTitle>{t('Docker 容器')}</SectionTitle>
          {info.containers.length === 0
            ? <p className="muted">{t('未获取到容器信息')}</p>
            : info.containers.map((line, index) => <div className="code-line" key={index}>{line}</div>)}
          <SectionTitle>{t('TLS 证书')}</SectionTitle>
          <KeyValue items={Object.entries(info.certificate).map(
            ([key, value]): [string, ReactNode] => [key, String(value)])} />
        </Panel>
      </div>

      <Panel title={t('监听端口')}>
        <div className="code-block">
          {info.listeningPorts.map((line, index) => <div key={index}>{line}</div>)}
        </div>
      </Panel>

      <div className="two-col">
        <Panel title={t('关键路径')}>
          <KeyValue items={Object.entries(info.paths).map(
            ([key, value]): [string, ReactNode] => [
              key, <span className="mono wrap" key={value}>{value}</span>,
            ])} />
        </Panel>
        <Panel title={t('接口地址与身份')}>
          <SectionTitle>{t('接口地址')}</SectionTitle>
          <KeyValue items={Object.entries(info.endpoints).map(
            ([key, value]): [string, ReactNode] => [
              key, <span className="mono wrap" key={value}>{value}</span>,
            ])} />
          <SectionTitle>{t('身份与目标')}</SectionTitle>
          <KeyValue items={Object.entries(info.identity).map(
            ([key, value]): [string, ReactNode] => [
              key, <span className="mono" key={value}>{value}</span>,
            ])} />
        </Panel>
      </div>
    </>}
  </>;
}

/* ----------------------------------------------------------- Settings page */

export function SettingsPage({ onPasswordChanged }: { onPasswordChanged: () => void }) {
  const [info, setInfo] = useState<SettingsInfo | null>(null);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');
  const { theme, setTheme } = useTheme();
  const { enabled, intervalMs, setEnabled, setIntervalMs } = useRefresh();
  const { lang, setLang } = useI18n();

  useEffect(() => { void api.settingsInfo().then(setInfo).catch(() => undefined); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(''); setDone('');
    if (next !== confirm) { setError(t('两次输入的新密码不一致')); return; }
    if (next.length < 12 || !/[A-Za-z]/.test(next) || !/\d/.test(next)) {
      setError(t('新密码至少 12 位，且需同时包含字母和数字')); return;
    }
    setBusy(true);
    try {
      const result = await api.changePassword(current, next);
      setDone(result.message + t('，正在退出…'));
      setCurrent(''); setNext(''); setConfirm('');
      window.setTimeout(onPasswordChanged, 1400);
    } catch (err) { setError(err instanceof Error ? err.message : t('修改失败')); }
    finally { setBusy(false); }
  }

  return <>
    <ErrorBanner message={error} onClose={() => setError('')} />
    {done && <div className="success-banner">{done}</div>}
    <div className="page-head">
      <h1>{t('设置')}</h1>
    </div>

    <Panel title={t('外观')}>
      <div className="theme-options">
        <button className={'theme-option ' + (theme === 'light' ? 'selected' : '')}
          onClick={() => setTheme('light')} aria-pressed={theme === 'light'}>
          <span className="theme-swatch light" aria-hidden="true" />
          <span><strong>{t('浅色')}</strong><small>{t('明亮、中性、适合白天')}</small></span>
        </button>
        <button className={'theme-option ' + (theme === 'dark' ? 'selected' : '')}
          onClick={() => setTheme('dark')} aria-pressed={theme === 'dark'}>
          <span className="theme-swatch dark" aria-hidden="true" />
          <span><strong>{t('深色')}</strong><small>{t('低亮度、适合夜间值守')}</small></span>
        </button>
      </div>
    </Panel>

    <Panel title={t('界面语言')} subtitle={t('选择界面显示语言，设置会保存在本机浏览器。')}>
      <div className="lang-options">
        <button className={'lang-option ' + (lang === 'zh' ? 'selected' : '')}
          onClick={() => setLang('zh')} aria-pressed={lang === 'zh'}>
          <span className="lang-option-glyph">中</span>
          <span><strong>{t('简体中文')}</strong><small>Chinese (Simplified)</small></span>
        </button>
        <button className={'lang-option ' + (lang === 'en' ? 'selected' : '')}
          onClick={() => setLang('en')} aria-pressed={lang === 'en'}>
          <span className="lang-option-glyph">EN</span>
          <span><strong>English</strong><small>English (United Kingdom)</small></span>
        </button>
      </div>
    </Panel>

    <Panel title={t('数据自动刷新')}
      subtitle={t('总览、QQ 机器人、Spug 等页面的状态与数据将按设定间隔自动拉取；关闭后仅保留手动刷新')}>
      <div className="refresh-setting">
        <label className="switch-row">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          <span>{t('启用自动刷新')}</span>
        </label>
        <label className="field"><span>{t('刷新间隔')}</span>
          <select value={Math.round(intervalMs / 1000)}
            onChange={(e) => setIntervalMs(Number(e.target.value) * 1000)} disabled={!enabled}>
            <option value={5}>{t('5 秒')}</option>
            <option value={10}>{t('10 秒')}</option>
            <option value={15}>{t('15 秒')}</option>
            <option value={30}>{t('30 秒')}</option>
            <option value={60}>{t('60 秒')}</option>
          </select>
        </label>
        <span className="muted small">{t('页面可见时生效；切到后台自动暂停，回到前台立即刷新一次')}</span>
      </div>
    </Panel>

    <Panel title={t('修改登录密码')} subtitle={t('修改后所有已登录会话立即失效，需要用新密码重新登录')}>
      <form className="password-form" onSubmit={submit}>
        <label>{t('当前密码')}
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password" required /></label>
        <label>{t('新密码')}
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password" minLength={12} maxLength={128} required /></label>
        <label>{t('确认新密码')}
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password" minLength={12} maxLength={128} required /></label>
        <div className="form-actions">
          <button className="primary-button compact" type="submit" disabled={busy}>
            {busy ? t('提交中…') : t('更新密码')}
          </button>
          <span className="muted">{t('至少 12 位，包含字母与数字')}</span>
        </div>
      </form>
    </Panel>

    <Panel title={t('账户信息')}>
      <KeyValue items={[
        [t('登录账号'), info?.username ?? '—'],
        [t('会话有效期'), info ? info.sessionTtlHours + t(' 小时') : '—'],
        [t('密码策略'), info ? t(info.passwordPolicy) : '—'],
        [t('凭据文件'), <span className="mono" key="f">{info?.authFile ?? '—'}</span>],
        [t('最近更新'), info?.updatedAt ? formatTime(info.updatedAt) : '—'],
      ]} />
    </Panel>

    <Panel title={t('品牌资产')} subtitle={t('当前语言使用的完整标识')}>
      <div className="brand-assets">
        <figure className="brand-lockup-card">
          <div className="brand-lockup-canvas">
            <img src={lang === 'zh' ? logoZh : logoEn}
              alt={lang === 'zh' ? '信栖 · 中文标识' : 'SignalNest · English lockup'} />
          </div>
          <figcaption>{lang === 'zh' ? t('中文标识') : t('英文标识')}</figcaption>
        </figure>
        <div className="brand-icon-card">
          <img src={emblem} width={72} height={72} alt={t('应用图标')} />
          <div>
            <strong>{t('应用图标')}</strong>
            <span className="muted small">{t('信栖')} · SignalNest</span>
            <span className="muted small">favicon / PWA / Apple Touch</span>
          </div>
        </div>
      </div>
    </Panel>
  </>;
}
