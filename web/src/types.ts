export type ServiceStatus = 'online' | 'offline' | 'degraded' | 'unknown' | 'disabled';
export type Outcome = 'delivered' | 'fallback' | 'failed' | 'ignored' | 'unknown' | 'pending';

export interface ServiceItem {
  id: string;
  name: string;
  group: string;
  status: ServiceStatus;
  detail: string;
  latencyMs: number;
  checkedAt: string;
}

export interface Overview {
  services: ServiceItem[];
  summary: Record<ServiceStatus, number>;
  checkedAt: string;
  note: string;
}

export interface DeliveryRecord {
  trace: string;
  ts: string;
  lastTs: string;
  source: string;
  sender: string;
  recipient: string;
  target: string;
  outcome: Outcome;
  outcomeLabel: string;
  stages: string[];
  stageLabels: string[];
  channels: string[];
  note: string;
  count: number;
}

export interface EventItem {
  ts: string;
  trace: string;
  source: string;
  stage: string;
  stageLabel: string;
  channel: string;
  channelLabel: string;
  result: string;
  target: string;
  sender: string;
  recipient: string;
  length: number | null;
  note: string;
  origin: string;
}

export interface Paged<T> {
  total: number;
  page: number;
  size: number;
  pages: number;
  items: T[];
}

export interface DayBucket {
  date: string;
  total: number;
  delivered: number;
  fallback: number;
  failed: number;
  ignored: number;
  unknown: number;
  pending: number;
}

export interface Stats {
  days: DayBucket[];
  totals: Omit<DayBucket, 'date'>;
  channels: { key: string; label: string; count: number }[];
  sources: Record<string, number>;
  generatedAt: string;
}

export interface Meta {
  stageLabels: Record<string, string>;
  channelLabels: Record<string, string>;
  outcomeLabels: Record<string, string>;
  sources: string[];
  serverTime: string;
}

export interface Filters {
  since: string;
  until: string;
  source: string;
  channel: string;
  outcome: string;
  result: string;
  q: string;
}

/* --------------------------------------------------- QQ bot settings page */

export interface QQConfig {
  botQq: string;
  targetGroup: string;
  targetGroupSource: string;
  targetGroupUpdatedAt: string;
  targetGroupUpdatedBy: string;
  targetType: string;
  forwardEnabled: string;
  onebotUrl: string;
  webuiUrl: string;
  runtimeConfigPath: string;
  envPath: string;
}

export interface QQStatus {
  state?: string;
  webuiConfigured: boolean;
  webuiStatus?: string;
  onebotOnline: boolean;
  onebotStatus?: string;
  bot: { uin?: string; nickname?: string };
  login: {
    isLogin: boolean;
    isOffline: boolean;
    loginPhase: string;
    loginError: string;
    qrLoginAccepted: boolean;
    coreReady: boolean;
    hasQrcode: boolean;
  };
  loginInfo: Record<string, string>;
  config: QQConfig;
  checkedAt: string;
}

export interface QQGroup {
  groupId: string;
  groupName: string;
  memberCount: number | null;
  current: boolean;
}

export interface QQGroups {
  available: boolean;
  current: string;
  count: number;
  groups: QQGroup[];
  reason?: string;
  hint?: string;
  checkedAt: string;
}

export interface QrcodeData {
  url: string;
  loginPhase: string;
  isLogin: boolean;
  qrLoginAccepted: boolean;
  checkedAt: string;
}

export interface QuickLogin {
  available: boolean;
  count: number;
  items: Record<string, string>[];
  note?: string;
  reason?: string;
}

/* ------------------------------------------------------------ Spug page */

export interface SpugBalance {
  money_balance?: number;
  sms_resource_balance?: number;
  voice_resource_balance?: number;
  mail_resource_balance?: number;
  wx_mp_resource_balance?: number;
  [key: string]: number | undefined;
}

export interface SpugStatus {
  configured: boolean;
  tokenPath: string;
  balance: SpugBalance | null;
  balanceError: string;
  balanceCheckedAt: string;
  balanceNote: string;
  reachable: boolean;
  delivery: {
    last24h: { sent: number; failed: number; total: number };
    last7d: { sent: number; failed: number; total: number };
  };
  templates: Record<string, { configured?: boolean; url: string }>;
  checkedAt: string;
}

export interface TokenStatus {
  configured: boolean;
  updatedAt: string;
  note: string;
}

/* ----------------------------------------------------- System info page */

export interface SystemInfo {
  host: string;
  hostname: string;
  os: string;
  kernel: string;
  architecture: string;
  python: string;
  uptime: string;
  loadAverage: number[];
  memory: Record<string, string>;
  disk: { total: number; used: number; free: number; percent: number; path: string };
  listeningPorts: string[];
  containers: string[];
  services: { unit: string; active: string; enabled: string }[];
  certificate: Record<string, string | boolean>;
  paths: Record<string, string>;
  endpoints: Record<string, string>;
  identity: Record<string, string>;
  generatedAt: string;
  note: string;
}

export interface PasswordLoginResult {
  ok: boolean;
  state: string;
  message: string;
  uin?: string;
  code?: number;
}

export interface SettingsInfo {
  username: string;
  updatedAt: string;
  authFile: string;
  sessionTtlHours: number;
  passwordPolicy: string;
  note: string;
}

export type PageKey = 'overview' | 'records' | 'events' | 'qqbot' | 'spug' | 'system' | 'settings' | 'forward';

/* ----------------------------------------------------- QQ accounts / restart */

export interface QQAccount {
  id: string;
  label: string;
  uin: string;
  hasPassword: boolean;
  isActive: boolean;
}

export interface QQAccounts {
  accounts: QQAccount[];
  activeUin: string;
  note: string;
}

export interface RestartResult {
  ok: boolean;
  requestedAt?: string;
  message?: string;
  cooldownRemaining?: number;
}

export interface SwitchResult {
  ok: boolean;
  state: string;
  uin?: string;
  message: string;
  code?: number;
}

/* ----------------------------------------------------- Forwarding route */

export interface ForwardChannel {
  key: string;
  enabled: boolean;
  label: string;
  desc: string;
}

export interface ForwardRoute {
  channels: ForwardChannel[];
  knownChannels: string[];
  path: string;
}
