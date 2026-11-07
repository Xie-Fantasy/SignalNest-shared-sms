import type { ReactNode } from 'react';
import type { Outcome, ServiceStatus } from './types';
import { t, localeTag } from './i18n';

// Semantic tokens come from CSS variables so both themes stay consistent and
// contrast-compliant. No hardcoded neon colours (design-system: restrained
// Data-Dense Dashboard palette, one accent + semantic status colours).
export const STATUS_META: Record<ServiceStatus, { label: string; color: string }> = {
  online: { label: '在线', color: 'var(--ok)' },
  offline: { label: '离线', color: 'var(--danger)' },
  degraded: { label: '降级', color: 'var(--warn)' },
  unknown: { label: '未知', color: 'var(--text-subtle)' },
  disabled: { label: '停用', color: 'var(--text-subtle)' },
};

export const OUTCOME_META: Record<Outcome, { color: string; background: string }> = {
  delivered: { color: 'var(--ok)', background: 'var(--ok-weak)' },
  fallback: { color: 'var(--info)', background: 'var(--info-weak)' },
  failed: { color: 'var(--danger)', background: 'var(--danger-weak)' },
  ignored: { color: 'var(--text-muted)', background: 'var(--surface-2)' },
  unknown: { color: 'var(--warn)', background: 'var(--warn-weak)' },
  pending: { color: 'var(--purple)', background: 'var(--purple-weak)' },
};

export const RESULT_LABELS: Record<string, string> = {
  ok: '成功', failed: '失败', ignored: '忽略', unknown: '未知', pending: '待处理',
};
export const SOURCE_LABELS: Record<string, string> = {
  iphone: 'iPhone', android: 'Android', system: '系统',
};

export function formatTime(value: string, seconds = true): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(localeTag(), {
    timeZone: 'Asia/Shanghai', hour12: false,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    ...(seconds ? { second: '2-digit' } : {}),
  });
}

export function bytes(value: number): string {
  if (!value) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let index = 0;
  let size = value;
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
  return size.toFixed(2) + ' ' + units[index];
}

export function StatusDot({ status }: { status: ServiceStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.unknown;
  return <span className="status-dot" style={{ background: meta.color }} />;
}

export function Pill({ children, color, background }: {
  children: ReactNode; color: string; background: string;
}) {
  return <span className="pill" style={{ color, background }}>{children}</span>;
}

export function Metric({ label, value, hint, color }: {
  label: string; value: number | string; hint?: string; color?: string;
}) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={color ? { color } : undefined}>{value}</div>
      {hint && <div className="metric-hint">{hint}</div>}
    </div>
  );
}

export function Panel({ title, subtitle, extra, children }: {
  title: string; subtitle?: string; extra?: ReactNode; children: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div><h2>{title}</h2>{subtitle && <p className="muted">{subtitle}</p>}</div>
        {extra}
      </div>
      {children}
    </section>
  );
}

export function Pagination({ page, pages, total, size, onPage }: {
  page: number; pages: number; total: number; size: number; onPage: (page: number) => void;
}) {
  return (
    <div className="pagination">
      <span className="muted">{t('共 {total} 条 · 第 {page}/{pages} 页 · 每页 {size} 条', {
        total, page, pages: Math.max(1, pages), size,
      })}</span>
      <div className="page-buttons">
        <button onClick={() => onPage(Math.max(1, page - 1))} disabled={page <= 1}>{t('上一页')}</button>
        <button onClick={() => onPage(Math.min(Math.max(1, pages), page + 1))}
          disabled={page >= Math.max(1, pages)}>{t('下一页')}</button>
      </div>
    </div>
  );
}

export function ErrorBanner({ message, onClose }: { message: string; onClose?: () => void }) {
  if (!message) return null;
  return <div className="alert">{t(message)}
    {onClose && <button className="link-button" onClick={onClose}>{t('关闭')}</button>}
  </div>;
}

export function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return (
    <div className="kv-grid">
      {items.map(([key, value]) => (
        <div className="kv-row" key={key}>
          <span className="kv-key">{key}</span>
          <span className="kv-value">{value ?? '—'}</span>
        </div>
      ))}
    </div>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="section-title">{children}</h3>;
}
