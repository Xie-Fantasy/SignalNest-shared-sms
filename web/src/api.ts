import type {
  DeliveryRecord, EventItem, Filters, ForwardRoute, Meta, Overview, Paged, PasswordLoginResult,
  QQAccounts, QQConfig, QQGroups, QQStatus, QrcodeData, QuickLogin, RestartResult,
  SettingsInfo, SpugStatus, Stats, SwitchResult, SystemInfo, TokenStatus,
} from './types';
import { t } from './i18n';

const BASE = '/monitor/api';
export const UNAUTHORIZED_EVENT = 'smsmon:unauthorized';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      ...init,
    });
  } catch {
    throw new Error(t('无法连接监控服务，请检查网络或服务状态'));
  }
  if (response.status === 401) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    throw new Error(t('登录已过期，请重新登录'));
  }
  if (!response.ok) {
    let detail = t('请求失败 (') + response.status + ')';
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      // keep the generic message
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== null) search.set(key, String(value));
  });
  const text = search.toString();
  return text ? '?' + text : '';
}

export const api = {
  me: () => request<{ username: string | null }>('/me'),
  login: (username: string, password: string) =>
    request<{ ok: boolean; username: string }>('/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ ok: boolean }>('/logout', { method: 'POST' }),
  meta: () => request<Meta>('/meta'),
  overview: (force = false) => request<Overview>('/overview' + query({ force: force ? 1 : 0 })),
  stats: (days = 7) => request<Stats>('/stats' + query({ days })),
  records: (filters: Filters, page: number, size = 20) =>
    request<Paged<DeliveryRecord>>('/records' + query({ ...filters, page, size })),
  events: (filters: Filters, page: number, size = 30) =>
    request<Paged<EventItem>>('/events' + query({
      since: filters.since, until: filters.until, source: filters.source,
      channel: filters.channel, result: filters.result, q: filters.q,
      page, size,
    })),

  // QQ bot settings
  qqStatus: (force = false) => request<QQStatus>('/qq/status' + query({ force: force ? 1 : 0 })),
  qqRestart: () => request<RestartResult>('/qq/restart', { method: 'POST' }),
  qqAccounts: () => request<QQAccounts>('/qq/accounts'),
  qqAccountSave: (label: string, uin: string, password: string, id = '') =>
    request<{ ok: boolean; count: number }>('/qq/accounts', {
      method: 'POST',
      body: JSON.stringify({ label, uin, password, id }),
    }),
  qqAccountDelete: (accountId: string) =>
    request<{ ok: boolean; count: number }>('/qq/accounts/' + accountId, { method: 'DELETE' }),
  qqSwitch: (accountId: string) =>
    request<SwitchResult>('/qq/switch', {
      method: 'POST', body: JSON.stringify({ accountId }),
    }),
  qqQrcode: () => request<QrcodeData>('/qq/qrcode'),
  qqQrcodeRefresh: () => request<QrcodeData>('/qq/qrcode/refresh', { method: 'POST' }),
  qqQuickLogin: () => request<QuickLogin>('/qq/quick-login'),
  qqGroups: () => request<QQGroups>('/qq/groups'),
  qqConfig: () => request<QQConfig>('/qq/config'),
  qqConfigSave: (targetGroupId: string) =>
    request<{ ok: boolean; effective: string; restartRequired: boolean; envModified: boolean }>(
      '/qq/config', { method: 'POST', body: JSON.stringify({ targetGroupId }) }),
  qqPasswordLogin: (uin: string, password: string) =>
    request<PasswordLoginResult>('/qq/password-login', {
      method: 'POST', body: JSON.stringify({ uin, password }),
    }),

  // Settings
  settingsInfo: () => request<SettingsInfo>('/settings/info'),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ ok: boolean; sessionInvalidated: boolean; message: string }>(
      '/settings/password', {
        method: 'POST',
        body: JSON.stringify({ currentPassword, newPassword }),
      }),

  // Spug
  spugStatus: (force = false) => request<SpugStatus>('/spug/status' + query({ force: force ? 1 : 0 })),
  spugToken: () => request<TokenStatus>('/spug/token'),
  spugTokenSave: (token: string) =>
    request<{ ok: boolean }>('/spug/token', { method: 'POST', body: JSON.stringify({ token }) }),
  spugTokenDelete: () => request<{ ok: boolean }>('/spug/token', { method: 'DELETE' }),

  // Forwarding route (priority ladder)
  forwardRoute: () => request<ForwardRoute>('/forward/route'),
  forwardRouteSave: (channels: { key: string; enabled: boolean }[]) =>
    request<{ ok: boolean; channels: ForwardRoute['channels']; effective: string; restartRequired: boolean; note: string }>(
      '/forward/route', { method: 'PUT', body: JSON.stringify({ channels }) }),

  // System
  systemInfo: () => request<SystemInfo>('/system/info'),
};
