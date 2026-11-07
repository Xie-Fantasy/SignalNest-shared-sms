import { createContext, useContext, useEffect, useSyncExternalStore, type ReactNode } from 'react';

/**
 * Lightweight i18n for the monitor console.
 *
 * Chinese source strings are used as dictionary keys. That keeps the source
 * readable for the primary audience and makes the English layer a single flat
 * lookup table instead of hundreds of invented identifiers. `t()` falls back
 * to the key itself, so any server-side message or untranslated string is
 * still rendered instead of showing a blank or a raw key.
 */
export type Lang = 'zh' | 'en';
const STORAGE_KEY = 'smsmon-lang';

/** English translations keyed by the original Chinese UI string. */
const EN: Record<string, string> = {
  // ---- navigation / shell ----
  '监控': 'Monitoring',
  '配置': 'Configuration',
  '系统': 'System',
  '总览': 'Overview',
  '投递记录': 'Deliveries',
  '事件明细': 'Events',
  'QQ 机器人': 'QQ Bot',
  'Spug 通道': 'Spug Channel',
  '转发设置': 'Forwarding',
  '系统信息': 'System Info',
  '设置': 'Settings',
  '页面导航': 'Page navigation',
  '短信网关': 'SMS Gateway',
  '运行监测控制台': 'Operations Console',
  '短信网关 · 运行监测': 'SignalNest · SMS Gateway Monitor',
  '总览 / 投递记录 / QQ 机器人 / Spug / 系统信息': 'Overview / Deliveries / QQ Bot / Spug / System',
  '实时': 'Live',
  '退出': 'Sign out',
  '已登录': 'Signed in',
  '正在连接…': 'Connecting…',
  '手动刷新': 'Manual refresh',
  '立即刷新': 'Refresh now',
  '数据自动刷新': 'Auto refresh',
  '自动': 'Auto',
  '更新于': 'Updated',

  // ---- common labels / states ----
  '在线': 'Online',
  '离线': 'Offline',
  '降级': 'Degraded',
  '未知': 'Unknown',
  '停用': 'Disabled',
  '成功': 'Success',
  '失败': 'Failed',
  '忽略': 'Ignored',
  '待处理': 'Pending',
  '已启用': 'Enabled',
  '已配置': 'Configured',
  '未配置': 'Not configured',
  '关闭': 'Close',
  '取消': 'Cancel',
  '保存': 'Save',
  '保存中…': 'Saving…',
  '保存失败': 'Save failed',
  '删除': 'Delete',
  '删除失败': 'Delete failed',
  '清除': 'Clear',
  '清除失败': 'Clear failed',
  '刷新': 'Refresh',
  '刷新失败': 'Refresh failed',
  '加载中…': 'Loading…',
  '加载失败': 'Load failed',
  '重置筛选': 'Reset filters',
  '筛选': 'Filters',
  '全部': 'All',
  '暂无数据': 'No data available',
  '没有符合条件的记录': 'No matching deliveries',
  '没有符合条件的事件': 'No matching events',
  '上一页': 'Previous',
  '下一页': 'Next',
  '关键词': 'Keyword',
  '按此记录筛选': 'Filter by this record',
  '关闭开关': 'Off',
  '—': '—',

  // ---- api / error messages ----
  '无法连接监控服务，请检查网络或服务状态': 'Cannot reach the monitor service — check the network or service status',
  '登录已过期，请重新登录': 'Session expired — please sign in again',
  '请求失败 (': 'Request failed (',
  '额度暂不可用': 'Balance temporarily unavailable',
  '（接口限流或 Token 无效时会自动重试）。': ' (retried automatically on rate limiting or an invalid token).',
  '当前账号': 'Current account',
  '发件人 / 号码 / 对象 / trace': 'Sender / number / target / trace',

  // ---- interpolated fragments ----
  '共 {n} 项': '{n} total',
  '离线 {o} · 降级 {d}': '{o} offline · {d} degraded',
  '耗时 {n} ms': '{n} ms',
  '{n} 人': '{n} members',
  '阶段：': 'Phase: ',
  '说明 ': 'Note: ',
  '检查于 ': 'Checked ',
  '更新于 ': 'Updated ',
  '切换到{what}主题': 'Switch to {what} theme',
  '自动 {n}s': 'Auto {n}s',
  '· 更新于 ': '· Updated ',
  ' 小时': ' h',

  // ---- server-side labels (best effort; unknown values pass through) ----
  '短信网关 API': 'SMS Gateway API',
  'QQ 群转发': 'QQ group forwarding',
  'Spug 推送通道': 'Spug push channel',
  'NapCat 容器': 'NapCat container',
  'Nginx 接入': 'Nginx ingress',
  '掉线告警巡检': 'Offline-alert probe',
  '自动恢复任务': 'Auto-recovery task',
  '磁盘空间': 'Disk space',
  'Web 检测系统': 'Web monitor',
  'Android 待发队列': 'Android pending queue',
  '短信接入': 'SMS ingress',
  '核心': 'Core', '转发': 'Forwarding', '队列': 'Queue', '运维': 'Operations',
  '收到短信': 'SMS received',
  '号码不匹配已忽略': 'Ignored — number not allowed',
  '已接收待转发': 'Accepted, awaiting forward',
  '已转发 QQ 群': 'Forwarded to QQ group',
  'QQ 转发失败': 'QQ forward failed',
  'Spug 短信': 'Spug SMS', 'Spug 提醒': 'Spug alert',
  'Spug 验证码已发': 'Spug verification code sent',
  'Spug 验证码失败': 'Spug verification code failed',
  'Spug 掉线提醒已发': 'Spug offline alert sent',
  'Spug 掉线提醒失败': 'Spug offline alert failed',
  '转发失败': 'Forward failed',
  '转发未启用': 'Forwarding disabled',
  '已忽略': 'Ignored', '处理中': 'Processing', '待发': 'Pending',
  '结果未知': 'Result unknown', '状态未知': 'State unknown',
  '健康检查不可达': 'Health check unreachable',
  '健康检查返回异常': 'Health check returned an error',
  '容器端口不可达': 'Container port unreachable',
  '接入端口不可达': 'Ingress port unreachable',
  '推送域名 443 不可达': 'Push endpoint :443 unreachable',
  '按设计停用 避免风控': 'Disabled by design to avoid risk control',
  '只读监控服务运行中': 'Read-only monitor running',
  '账号或密码错误': 'Incorrect username or password',
  '尝试次数过多 请 5 分钟后重试': 'Too many attempts — try again in 5 minutes',

  // ---- server-side status details (exact matches; printf-style dynamic
  //      messages such as "机器人 <uin> 在线…" cannot be keyed and stay as-is) ----
  '80 与 443 监听正常': 'Ports 80 and 443 reachable',
  'OneBot 与 WebUI 端口正常': 'OneBot and WebUI ports reachable',
  '短信 API 正常响应': 'SMS API responding normally',
  '巡检定时器未运行': 'Probe timer not running',
  '巡检定时器运行中': 'Probe timer running',
  '自动恢复定时器运行中': 'Auto-recovery timer running',
  '待发队列': 'Pending queue',
  '待发队列不可读': 'Pending queue unreadable',
  '未找到待发队列目录': 'Pending queue directory not found',
  '磁盘信息不可读': 'Disk info unreadable',
  '状态探测失败': 'Status probe failed',
  '探测异常': 'Probe error',
  '探测超时': 'Probe timed out',
  '无积压 历史记录': 'No backlog · history',
  '所有探测均为只读 不会发送任何消息': 'All probes are read-only; no messages are sent',
  '通道可达 但未读取到模板配置': 'Channel reachable, template config not loaded',
  '通道可达 但近 24 小时投递失败': 'Channel reachable, delivery failed in last 24h',
  '通道可达 模板已配置 近期无投递': 'Channel reachable, template configured, no recent delivery',
  '通道可达 近 24 小时成功': 'Channel reachable, delivered in last 24h',
  '资源包余额不含会员每日赠送额度': 'Quota excludes the daily member bonus',
  '其他事件': 'Other events',
  '兜底': 'Fallback',
  '接入': 'Ingress',
  '可用': 'Available',
  '已用': 'Used',
  '百分点': 'percentage points',
  'Android 已入队': 'Android queued',
  'Android 已忽略': 'Android ignored',
  'Android 已投递': 'Android delivered',
  'Android 已过期': 'Android expired',
  'Android 结果未知': 'Android result unknown',
  'Android 重复消息': 'Android duplicate',
  // ---- server-side messages / errors ----
  '当前密码不正确': 'Current password is incorrect',
  '认证服务未就绪': 'Auth service not ready',
  '认证文件不可用': 'Auth file unavailable',
  '账号不存在': 'Account not found',
  '登录被拒绝': 'Login rejected',
  '登录请求已提交，页面会自动检测登录结果': 'Login request submitted; the page will detect the result',
  '密码已更新，所有会话已失效，请重新登录': 'Password updated; all sessions invalidated, please sign in again',
  'Token 格式不合法': 'Invalid token format',
  'WebUI 不可用': 'WebUI unavailable',
  'QQ 号必须为数字': 'QQ number must be numeric',
  '群号必须为纯数字': 'Group number must be numeric',
  '写入重启触发器失败': 'Failed to write restart trigger',
  '需要验证码，请在 NapCat WebUI 人工处理': 'Verification code required — handle it in NapCat WebUI',
  '需要新设备验证，请在 NapCat WebUI 人工处理': 'New-device verification required — handle it in NapCat WebUI',
  '当前没有可显示的二维码，请稍后刷新': 'No QR code available yet — refresh shortly',
  '当前配置群（机器人离线，列表不可拉取）': 'Configured group (bot offline, list unavailable)',
  '机器人离线时无法拉取群列表，可手动输入群号保存': 'Group list unavailable while bot is offline; enter a group number manually',
  '该账号未保存密码。请在上方登录区用手机扫码，或用「账号密码登录」':
    'No password saved for this account. Scan the QR code or use password login above.',
  '仅展示列表，不自动触发登录': 'List only; no automatic login',
  '凭据、Token、私钥与短信正文不在此接口返回': 'Credentials, tokens, private keys and SMS bodies are never returned',
  '密码仅存服务器 600 文件，接口永不返回值': 'Passwords are stored server-side (mode 600) and never returned',
  '开发者 Token 仅存服务器，接口永不返回值': 'Developer token is stored server-side and never returned',
  '密码哈希与会话密钥仅存服务器，接口永不返回': 'Password hash and session secret stay on the server',
  '已请求重启 NapCat，系统将在数秒内执行；可用「刷新状态」查看恢复情况':
    'NapCat restart requested; use "Refresh status" to check recovery',
  '短信服务在下次转发前读取，无需重启': 'Applied on the next forward, no restart needed',
  '短信网关在下次转发前读取，无需重启': 'Applied on the next forward, no restart needed',

  // ---- pagination / units (interpolated) ----
  '共 {total} 条 · 第 {page}/{pages} 页 · 每页 {size} 条':
    '{total} records · Page {page}/{pages} · {size} per page',
  '{count} 个事件': '{count} events',
  '{n} 个事件': '{n} events',
  '{n} 秒': '{n} s',
  '{n} 小时': '{n} h',
  '元': 'CNY',
  '分钟': 'min',
  '封': 'emails',
  '条': 'SMS',

  // ---- overview ----
  '在线服务': 'Services online',
  '异常 / 降级': 'Errors / degraded',
  '今日投递记录': "Today's deliveries",
  '转发成功': 'Forwarded',
  '兜底送达': 'Fallback delivered',
  '失败 / 未知': 'Failed / unknown',
  '服务状态': 'Service status',
  '正在检测服务状态…': 'Checking service status…',
  '近 7 天投递结果': '7-day delivery outcomes',
  '按接收时间 UTC 归集': 'Grouped by received time (UTC)',
  '近 24h 成功': '24h success',
  '近 24h 失败': '24h failed',
  '近 7d 成功': '7d success',
  '近 7d 失败': '7d failed',

  // ---- records / events ----
  '时间': 'Time',
  '来源': 'Source',
  '发件人': 'Sender',
  '接收号': 'Recipient',
  '发送对象': 'Target',
  '结果': 'Outcome',
  '链路': 'Trace',
  '阶段': 'Stage',
  '通道': 'Channel',
  '说明': 'Note',
  '起始': 'From',
  '截止': 'To',
  '历史号码未采集': 'Number not captured',
  '当时的日志未采集完整号码，无法还原': 'Full number was never captured in the original log',
  '号码未采集': 'Number not captured',
  '历史回填': 'Backfilled',

  // ---- QQ bot ----
  '扫码登录': 'QR code login',
  '账号密码登录': 'Password login',
  'QQ 号': 'QQ number',
  '密码': 'Password',
  '提交登录': 'Sign in',
  '提交中…': 'Submitting…',
  '登录成功': 'Signed in',
  '登录中': 'Signing in',
  '登录中…': 'Signing in…',
  '登录失败': 'Sign-in failed',
  '登录请求失败': 'Sign-in request failed',
  '等待扫码': 'Waiting for scan',
  '已扫码 等待确认': 'Scanned · awaiting confirmation',
  '已扫码，请在手机上确认登录': 'Scanned — confirm on your phone',
  '正在生成二维码': 'Generating QR code',
  '初始化中': 'Initializing',
  '重连中': 'Reconnecting',
  '刷新二维码': 'Refresh QR code',
  '当前没有可显示的二维码': 'No QR code available',
  '可点击「刷新二维码」重新生成': 'Click "Refresh QR code" to generate a new one',
  '登录账号': 'Signed-in account',
  '昵称': 'Nickname',
  '核心状态': 'Core state',
  '已就绪': 'Ready',
  '登录阶段': 'Login phase',
  '检查时间': 'Checked at',
  '快速登录列表': 'Quick login list',
  '转发群设置': 'Forward target group',
  '当前目标群': 'Current group',
  '配置来源': 'Config source',
  '独立配置文件': 'Standalone config file',
  '环境变量 .env': 'Environment (.env)',
  '最近更新': 'Last updated',
  '转发开关': 'Forwarding',
  '保存群号': 'Save group',
  '输入群号': 'Group number',
  '群号必须为 5-12 位数字': 'Group number must be 5–12 digits',
  'QQ 号必须为 5-12 位数字': 'QQ number must be 5–12 digits',
  '机器人离线，暂不能拉取群列表': 'Bot offline — group list unavailable',
  '已保存，短信服务下次转发前自动生效，无需重启': 'Saved. Takes effect on the next forward, no restart needed',
  '连接信息': 'Connection',
  '机器人 QQ': 'Bot QQ',
  '目标类型': 'Target type',
  'OneBot 地址': 'OneBot URL',
  'WebUI 地址': 'WebUI URL',
  '配置文件': 'Config file',
  '多账号切换': 'Switch accounts',
  '当当前 QQ 机器人不可用时，可一键切换到已保存的备用账号（保存密码的账号可免输密码切换）。':
    'Switch to a saved backup account with one click when the current bot is down. Accounts with a saved password can be switched without retyping.',
  '尚未添加备用账号，可在下方添加。': 'No backup accounts yet — add one below.',
  '备注名（如 备用小号）': 'Label (e.g. Backup account)',
  '密码（可选·存后一键切换）': 'Password (optional · enables one-click switch)',
  '添加账号': 'Add account',
  '当前': 'Current',
  '已存密码': 'Password saved',
  '切换': 'Switch',
  '切换中…': 'Switching…',
  '切换失败：': 'Switch failed: ',
  '刷新状态': 'Refresh status',
  '重启 OneBot': 'Restart OneBot',
  '重启中…': 'Restarting…',
  '已请求重启': 'Restart requested',
  '重启请求失败': 'Restart request failed',
  '确认重启 OneBot？': 'Restart OneBot?',
  '确认重启': 'Confirm restart',
  '重启会断开当前 QQ 登录，恢复后需要用扫码或账号密码重新登录；期间短信转发暂停约 30 秒。':
    'Restarting disconnects the current QQ session — you will need to sign in again with a QR code or password. SMS forwarding is paused for about 30 seconds.',
  '；重启期间会断开当前登录，恢复后需要用扫码或账号密码重新登录。':
    ' Restarting disconnects the current session; sign in again with a QR code or password afterwards.',
  '已保存账号，可在「当前账号」面板一键切换': 'Account saved — switch to it from the account panel',
  '未知错误': 'Unknown error',

  // ---- Spug ----
  '账户额度': 'Account balance',
  '资金余额': 'Funds',
  '短信资源包': 'SMS quota',
  '语音资源包': 'Voice quota',
  '邮件资源包': 'Email quota',
  '公众号资源包': 'WeChat quota',
  '投递统计': 'Delivery stats',
  '模板与地址': 'Templates & endpoints',
  '验证码转发模板': 'Verification-code template',
  '掉线提醒模板': 'Offline-alert template',
  '定时告警模板': 'Scheduled-alert template',
  '强制刷新额度': 'Refresh balance',
  '打开 Spug 控制台': 'Open Spug console',
  '开发者 Token': 'Developer token',
  '粘贴开发者 Token（不会回显）': 'Paste developer token (never shown again)',
  '在「凭证管理」复制开发者 Token，粘贴到下方即可显示真实额度。':
    'Copy the developer token from Spug → Credentials and paste it below to show the real balance.',
  '开发者 Token 已保存到服务器（600 权限），页面不会回显':
    'Developer token saved on the server (mode 600) and is never displayed',
  'Token 已清除': 'Token cleared',
  'Token 长度不足': 'Token is too short',
  '尚未配置开发者 Token。': 'No developer token configured yet.',
  '通道可达': 'Channel reachable',
  '通道不可达': 'Channel unreachable',

  // ---- forwarding ladder ----
  '短信转发方式（优先级阶梯）': 'Forwarding priority',
  '短信到达后按从上到下的顺序尝试每个': 'Channels are tried top to bottom for each incoming message.',
  '的渠道；某个渠道失败会自动尝试下一个。拖动行或点箭头调整顺序，关闭开关可跳过该渠道。':
    'If a channel fails, the next one is tried automatically. Drag a row or use the arrows to reorder; turn a channel off to skip it.',
  '保存转发规则': 'Save routing rules',
  '已保存，网关下次转发前自动生效，无需重启': 'Saved. Takes effect on the next forward, no restart needed',
  '上移': 'Move up',
  '下移': 'Move down',

  // ---- system info ----
  '主机': 'Host',
  '主机名': 'Hostname',
  '公网 IP': 'Public IP',
  '操作系统': 'OS',
  '内核': 'Kernel',
  '架构': 'Architecture',
  '运行时长': 'Uptime',
  '负载': 'Load',
  '内存总量': 'Total memory',
  '可用内存': 'Available memory',
  '磁盘': 'Disk',
  '监听端口': 'Listening ports',
  'Docker 容器': 'Docker containers',
  '容器与证书': 'Containers & certificates',
  'TLS 证书': 'TLS certificate',
  '关键路径': 'Key paths',
  '存储路径': 'Storage path',
  '接口地址': 'API endpoints',
  '接口地址与身份': 'Endpoints & identity',
  '身份与目标': 'Identity & target',
  '配置状态': 'Config state',
  '未获取到容器信息': 'Container info unavailable',
  '立即检测': 'Probe now',
  '更新时间': 'Updated at',
  '控制台': 'Console',

  // ---- settings ----
  '外观': 'Appearance',
  '主题': 'Theme',
  '浅色': 'Light',
  '深色': 'Dark',
  '明亮、中性、适合白天': 'Bright and neutral for daytime',
  '低亮度、适合夜间值守': 'Low brightness for night shifts',
  '切换到': 'Switch to ',
  '总览、QQ 机器人、Spug 等页面的状态与数据将按设定间隔自动拉取；关闭后仅保留手动刷新':
    'Overview, QQ Bot, Spug and other pages poll at the chosen interval. Turn off to refresh manually only.',
  '启用自动刷新': 'Enable auto refresh',
  '刷新间隔': 'Interval',
  '5 秒': '5 s', '10 秒': '10 s', '15 秒': '15 s', '30 秒': '30 s', '60 秒': '60 s',
  '页面可见时生效；切到后台自动暂停，回到前台立即刷新一次':
    'Active while the page is visible; paused in the background and refreshed once on return.',
  '修改登录密码': 'Change password',
  '修改后所有已登录会话立即失效，需要用新密码重新登录':
    'All active sessions are invalidated; sign in again with the new password.',
  '当前密码': 'Current password',
  '新密码': 'New password',
  '确认新密码': 'Confirm new password',
  '更新密码': 'Update password',
  '至少 12 位，包含字母与数字': 'At least 12 characters, letters and digits',
  '两次输入的新密码不一致': 'New passwords do not match',
  '新密码至少 12 位，且需同时包含字母和数字':
    'New password must be at least 12 characters with both letters and digits',
  '修改失败': 'Update failed',
  '，正在退出…': ' — signing out…',
  '账户信息': 'Account',
  '会话有效期': 'Session lifetime',
  '密码策略': 'Password policy',
  '凭据文件': 'Credentials file',

  // ---- language ----
  '语言': 'Language',
  '界面语言': 'Interface language',
  '简体中文': '简体中文',
  'English': 'English',
  '切换语言': 'Switch language',
  '选择界面显示语言，设置会保存在本机浏览器。':
    'Choose the interface language. The preference is saved in this browser.',

  // ---- brand / login (new) ----
  '信栖': 'SignalNest',
  '短信转发与运行监测': 'SMS forwarding & operations monitoring',
  '安全登录': 'Secure sign-in',
  '登录以访问运行监测控制台': 'Sign in to access the operations console',
  '账号或密码错误，请重试': 'Incorrect username or password',
  '显示密码': 'Show password',
  '隐藏密码': 'Hide password',
  '品牌资产': 'Brand assets',
  '品牌标识': 'Brand identity',
  '应用图标': 'App icon',
  '中文标识': 'Chinese lockup',
  '英文标识': 'English lockup',
  '当前语言使用的完整标识': 'Full lockup for the selected language',
  '统一查看投递链路、通道状态与系统运行情况。':
    'One place for delivery traces, channel health and system status.',
  '端到端投递追踪': 'End-to-end delivery tracing',
  '通道健康实时可见': 'Live channel health',
  '服务器字段完整展示': 'Unmasked server details',
  '账号': 'Username',
  '登录': 'Sign in',
  '请输入登录密码': 'Enter your password',
  '记住账号': 'Remember username',
};

interface I18nValue {
  lang: Lang;
  setLang: (value: Lang) => void;
  toggle: () => void;
}

const I18nContext = createContext<I18nValue>({
  lang: 'zh', setLang: () => undefined, toggle: () => undefined,
});

/* Language state lives in a tiny external store rather than React state.
 *
 * `t()` is a plain module-level function (not a hook), so components that call
 * it are NOT Context consumers. With a plain useState/Context provider, only
 * the toggle button re-rendered on switch and the rest of the page kept stale
 * Chinese text until a manual F5. useSyncExternalStore lets the App root (and
 * any cached view) subscribe directly, so a switch repaints the whole tree
 * in place without unmounting it - local UI state is preserved. */
type Listener = () => void;
const listeners = new Set<Listener>();

function initialLang(): Lang {
  if (typeof window === 'undefined') return 'zh';
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === 'zh' || saved === 'en') return saved;
  } catch {
    // storage may be blocked
  }
  return 'zh';
}

let currentLang: Lang = initialLang();

function getLangSnapshot(): Lang {
  return currentLang;
}

function subscribeLang(listener: Listener): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Subscribe to language changes. Call at the App root and in any memoized view. */
export function useLang(): Lang {
  return useSyncExternalStore(subscribeLang, getLangSnapshot, getLangSnapshot);
}

function commitLang(value: Lang): void {
  if (value !== 'zh' && value !== 'en') return;
  const changed = currentLang !== value;
  currentLang = value;
  document.documentElement.setAttribute('lang', value === 'zh' ? 'zh-CN' : 'en');
  try { window.localStorage.setItem(STORAGE_KEY, value); } catch { /* ignore */ }
  // Always notify: keeps the html/lang attribute and persisted value in sync
  // even if the language was already the same.
  if (changed) listeners.forEach((fn) => fn());
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const lang = useLang();

  useEffect(() => {
    // Apply on first mount too (covers a saved EN preference from a previous
    // session, where index.html still declares lang="zh-CN").
    document.documentElement.setAttribute('lang', lang === 'zh' ? 'zh-CN' : 'en');
    try { window.localStorage.setItem(STORAGE_KEY, lang); } catch { /* ignore */ }
  }, [lang]);

  const setLang = (value: Lang) => commitLang(value);
  const toggle = () => commitLang(currentLang === 'zh' ? 'en' : 'zh');

  return <I18nContext.Provider value={{ lang, setLang, toggle }}>
    {children}
  </I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  return useContext(I18nContext);
}

export function getLang(): Lang {
  return currentLang;
}

/* A few server strings are printf-formatted (QQ number, timer state, counts),
 * so they cannot be used as flat dictionary keys. Translate those known shapes
 * as a bounded best-effort fallback; anything unmatched still passes through. */
const EN_PATTERNS: [RegExp, string][] = [
  [/^机器人 (\S+) 在线，转发通道正常$/, 'Bot $1 online, forwarding channel healthy'],
  [/^巡检定时器未运行 inactive$/, 'Probe timer not running (inactive)'],
  [/^按设计停用 避免风控 inactive$/, 'Disabled by design to avoid risk control (inactive)'],
  [/^无积压 历史记录 (\d+) 条$/, 'No backlog · $1 historical records'],
  [/^已用 ([\d.]+) 百分点$/, '$1 percentage points used'],
  [/^未登录；OneBot (.+)$/, 'Not signed in; OneBot $1'],
  [/^核心已登录（(.+)），但 OneBot (.+) 不可达，转发暂不可用$/,
    'Core signed in ($1), but OneBot $2 unreachable — forwarding unavailable'],
  [/^机器人 (\S+) 离线，转发通道不可用$/, 'Bot $1 offline, forwarding channel unavailable'],
];

/** Translate a UI string; unknown keys pass through unchanged. */
export function t(key: string, vars?: Record<string, string | number>): string {
  let out = currentLang === 'en' ? (EN[key] ?? key) : key;
  if (currentLang === 'en' && EN[key] === undefined) {
    for (const [pattern, replacement] of EN_PATTERNS) {
      const match = pattern.exec(key);
      if (match) {
        out = replacement.replace(/\$(\d+)/g, (_, index) => match[Number(index)] ?? '');
        break;
      }
    }
  }
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      out = out.replaceAll('{' + name + '}', String(value));
    }
  }
  return out;
}

/** Locale used by date/number formatting; timezone stays Asia/Shanghai. */
export function localeTag(): string {
  return currentLang === 'zh' ? 'zh-CN' : 'en-GB';
}

export function LanguageToggle({ compact = false }: { compact?: boolean }) {
  const { lang, setLang } = useI18n();
  return (
    <div className={'lang-toggle' + (compact ? ' compact' : '')} role="group" aria-label={t('切换语言')}>
      <button type="button" className={lang === 'zh' ? 'active' : ''}
        aria-pressed={lang === 'zh'} onClick={() => setLang('zh')}>中</button>
      <button type="button" className={lang === 'en' ? 'active' : ''}
        aria-pressed={lang === 'en'} onClick={() => setLang('en')}>EN</button>
    </div>
  );
}
