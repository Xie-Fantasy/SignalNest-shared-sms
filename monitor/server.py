"""Authenticated monitoring and administration API on loopback port 18101.

Probes are read-only. Explicit admin endpoints can update routing, perform
manual QQ login and request NapCat restart. Delivery metadata includes full
identifiers; protect access and obtain consent. Event APIs exclude SMS bodies.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

EVENT_DIR = Path(os.environ.get('SMS_EVENT_DIR', '/var/lib/sms-gateway/events'))
AUTH_FILE = Path(os.environ.get('SMS_MONITOR_AUTH_FILE', '/etc/sms-monitor/auth.json'))
GATEWAY_ENV = Path('/opt/sms-gateway/.env')
INBOX_DIR = Path('/var/lib/sms-gateway/android-inbox')
ONEBOT_URL = 'http://127.0.0.1:13000'
GATEWAY_HEALTH = 'http://127.0.0.1:8000/health'
COOKIE_NAME = 'smsmon'
SESSION_TTL = 12 * 3600
MAX_SCAN_LINES = 50000
OVERVIEW_TTL = 5

# Only a small, explicit set of keys is read from the gateway .env.
_ENV_KEYS = frozenset({
    'NAPCAT_ACCESS_TOKEN', 'QQ_TARGET_ID', 'BOT_QQ_ID',
    'QQ_FORWARD_ENABLED', 'QQ_TARGET_TYPE', 'SPUG_CODE_URL', 'SPUG_NOTIFY_URL',
})

# 2026-11-05: user explicitly requested NO masking of server or delivery
# fields. Full sender, recipient, QQ numbers, group ids, IPs and paths are
# shown. Only control characters, angle brackets and backslashes are rejected
# to keep the JSONL clean; React escapes all rendered text. Credentials, SMS
# bodies and verification codes are still never collected or returned.
_FORBIDDEN = re.compile(r'[\x00-\x1f\x7f<>\\]')


def display(value: Any, limit: int = 256) -> str:
    if value is None:
        return ''
    text = str(value)[:limit]
    return '[redacted]' if _FORBIDDEN.search(text) else text


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


# --------------------------------------------------------------------------
# Authentication: PBKDF2 password hash + HMAC signed cookie, in-memory throttle
# --------------------------------------------------------------------------

class Auth:
    def __init__(self):
        self._data: dict | None = None
        self._mtime = 0
        self._lock = threading.Lock()
        self._fails: dict[str, tuple[int, float]] = {}

    def load(self):
        try:
            stat = AUTH_FILE.stat()
            if self._data is None or stat.st_mtime_ns != self._mtime:
                with self._lock:
                    self._data = json.loads(AUTH_FILE.read_text(encoding='utf-8'))
                    self._mtime = stat.st_mtime_ns
        except Exception:
            return None
        return self._data

    def verify(self, username: str, password: str, ip: str):
        now = time.time()
        record = self._fails.get(ip)
        if record and record[1] > now:
            return False, 'locked'
        data = self.load()
        if not data:
            return False, 'unavailable'
        try:
            salt = bytes.fromhex(data['salt'])
            expected = bytes.fromhex(data['password_hash'])
            actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 200000)
            ok = (hmac.compare_digest(actual, expected)
                  and hmac.compare_digest(username.strip(), data['username']))
        except Exception:
            ok = False
        if ok:
            self._fails.pop(ip, None)
            return True, 'ok'
        count = (record[0] if record else 0) + 1
        self._fails[ip] = (count, now + 300 if count >= 5 else 0.0)
        return False, 'locked' if count >= 5 else 'invalid'

    def sign(self, username: str):
        data = self.load()
        if not data:
            return None
        payload = {'u': username, 'exp': int(time.time()) + SESSION_TTL}
        raw = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(',', ':')).encode('utf-8')
        ).decode('ascii').rstrip('=')
        signature = hmac.new(bytes.fromhex(data['session_secret']),
                             raw.encode('ascii'), hashlib.sha256).hexdigest()
        return raw + '.' + signature

    def check(self, token: str | None):
        if not token or '.' not in token:
            return None
        data = self.load()
        if not data:
            return None
        raw, _, signature = token.partition('.')
        expected = hmac.new(bytes.fromhex(data['session_secret']),
                            raw.encode('ascii'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            padded = raw + '=' * (-len(raw) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode('utf-8'))
            if payload.get('exp', 0) < int(time.time()):
                return None
            return display(payload.get('u'), 64)
        except Exception:
            return None


auth = Auth()


# --------------------------------------------------------------------------
# Event store: append-only JSONL written by the gateway
# --------------------------------------------------------------------------

_EVENT_KEYS = ('ts', 'trace', 'source', 'stage', 'channel', 'result',
               'target', 'sender', 'recipient', 'length', 'note', 'origin')

STAGE_LABELS = {
    'RECEIVED': '收到短信', 'IGNORED': '号码不匹配已忽略', 'ACCEPTED': '已接收待转发',
    'SKIPPED': '转发未启用', 'QQ_FORWARDED': '已转发 QQ 群', 'QQ_FORWARD_FAILED': 'QQ 转发失败',
    'SPUG_CODE_SENT': 'Spug 验证码已发', 'SPUG_CODE_FAILED': 'Spug 验证码失败',
    'SPUG_NOTIFY_SENT': 'Spug 掉线提醒已发', 'SPUG_NOTIFY_FAILED': 'Spug 掉线提醒失败',
    'ANDROID_ACCEPTED': 'Android 已入队', 'ANDROID_DEDUP': 'Android 重复消息',
    'ANDROID_IGNORED': 'Android 已忽略', 'ANDROID_EXPIRED': 'Android 已过期',
    'ANDROID_DELIVERED': 'Android 已投递', 'ANDROID_DELIVERY_UNKNOWN': 'Android 结果未知',
    'SERVICE_STATE': '服务状态', 'OTHER': '其他事件',
}
CHANNEL_LABELS = {
    'ingress': '短信接入', 'qq': 'QQ 群转发', 'spug_sms': 'Spug 短信',
    'spug_notify': 'Spug 提醒', 'queue': '待发队列', 'system': '系统',
}
OUTCOME_LABELS = {
    'delivered': '转发成功', 'fallback': '兜底送达', 'failed': '转发失败',
    'ignored': '已忽略', 'unknown': '结果未知', 'pending': '处理中',
}


def normalize_record(raw: dict) -> dict:
    out = {}
    for key in _EVENT_KEYS:
        value = raw.get(key)
        out[key] = display(value) if key not in ('length',) else (
            value if isinstance(value, int) and 0 <= value <= 65536 else None)
    if not out['ts'] or not out['trace']:
        out['ts'] = out['ts'] or utc_now()
        out['trace'] = out['trace'] or 'unknown'
    out['stageLabel'] = STAGE_LABELS.get(out['stage'], out['stage'])
    out['channelLabel'] = CHANNEL_LABELS.get(out['channel'], out['channel'])
    return out


def iter_events():
    if not EVENT_DIR.is_dir():
        return
    seen = 0
    for path in sorted(EVENT_DIR.glob('*.jsonl'), key=lambda p: p.name, reverse=True):
        try:
            with path.open('r', encoding='utf-8') as stream:
                for line in stream:
                    seen += 1
                    if seen > MAX_SCAN_LINES or len(line) > 4096:
                        break
                    try:
                        raw = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(raw, dict):
                        yield normalize_record(raw)
        except OSError:
            continue


def _outcome(stages: list[str], results: list[str]) -> str:
    if 'QQ_FORWARDED' in stages or 'ANDROID_DELIVERED' in stages:
        return 'delivered'
    if any(s.endswith('_SENT') for s in stages):
        return 'fallback'
    if any(s in ('SPUG_CODE_FAILED', 'SPUG_NOTIFY_FAILED', 'QQ_FORWARD_FAILED') for s in stages):
        return 'failed'
    if 'ANDROID_DELIVERY_UNKNOWN' in stages or 'unknown' in results:
        return 'unknown'
    if any(s in ('IGNORED', 'ANDROID_IGNORED', 'ANDROID_EXPIRED',
                 'SKIPPED', 'ANDROID_DEDUP') for s in stages):
        return 'ignored'
    return 'pending'


def aggregate(events: list[dict]) -> list[dict]:
    """Group raw events into one delivery record per inbound SMS (by trace)."""
    groups: OrderedDict[str, dict] = OrderedDict()
    for event in events:
        trace = event['trace']
        group = groups.get(trace)
        if group is None:
            group = {
                'trace': trace, 'ts': event['ts'], 'lastTs': event['ts'],
                'source': event['source'] or 'system', 'sender': '', 'recipient': '',
                'target': '', 'note': '', 'stages': [], 'results': [],
                'channels': [], 'count': 0,
            }
            groups[trace] = group
        group['count'] += 1
        if event['ts'] < group['ts']:
            group['ts'] = event['ts']
        if event['ts'] > group['lastTs']:
            group['lastTs'] = event['ts']
        for key in ('sender', 'recipient', 'target'):
            if not group[key] and event[key] and event[key] != '[unrecognized]':
                group[key] = event[key]
        if event['stage'] and event['stage'] not in group['stages']:
            group['stages'].append(event['stage'])
        if event['channel'] and event['channel'] not in group['channels']:
            group['channels'].append(event['channel'])
        if event['result']:
            group['results'].append(event['result'])
        if event['note'] and not group['note']:
            group['note'] = event['note']
    records = []
    for group in groups.values():
        outcome = _outcome(group['stages'], group['results'])
        records.append({
            'trace': group['trace'], 'ts': group['ts'], 'lastTs': group['lastTs'],
            'source': group['source'], 'sender': group['sender'],
            'recipient': group['recipient'], 'target': group['target'],
            'outcome': outcome, 'outcomeLabel': OUTCOME_LABELS[outcome],
            'stages': group['stages'], 'stageLabels': [STAGE_LABELS.get(s, s) for s in group['stages']],
            'channels': group['channels'], 'note': group['note'], 'count': group['count'],
        })
    records.sort(key=lambda r: r['ts'], reverse=True)
    return records


def match_filters(row: dict, *, since: str, until: str, source: str,
                  channel: str, result: str, q: str, stage: str = '',
                  outcome: str = '') -> bool:
    day = row['ts'][:10]
    if since and day < since:
        return False
    if until and day > until:
        return False
    if source and row.get('source') != source:
        return False
    if result and row.get('result') != result:
        return False
    if outcome and row.get('outcome') != outcome:
        return False
    if stage and row.get('stage') != stage:
        return False
    if channel:
        pool = row.get('channels') or [row.get('channel', '')]
        if channel not in pool:
            return False
    if q:
        needle = q.strip().lower()[:64]
        if needle:
            haystack = ' '.join(str(row.get(k, '')) for k in
                               ('trace', 'sender', 'recipient', 'target', 'note',
                                'stageLabel', 'channelLabel', 'outcomeLabel')).lower()
            if needle not in haystack:
                return False
    return True


def paginate(rows: list[dict], page: int, size: int) -> dict:
    page = max(1, min(page, 100000))
    size = max(1, min(size, 100))
    total = len(rows)
    return {'total': total, 'page': page, 'size': size,
            'pages': (total + size - 1) // size,
            'items': rows[(page - 1) * size: page * size]}


def build_stats(records: list[dict], days: int) -> dict:
    days = max(1, min(days, 90))
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    buckets = OrderedDict(
        (str(start + timedelta(days=i)),
         {'date': str(start + timedelta(days=i)), 'total': 0, 'delivered': 0,
          'fallback': 0, 'failed': 0, 'ignored': 0, 'unknown': 0, 'pending': 0})
        for i in range(days))
    channels: dict[str, int] = {}
    sources: dict[str, int] = {}
    for row in records:
        bucket = buckets.get(row['ts'][:10])
        if bucket:
            bucket['total'] += 1
            bucket[row['outcome']] = bucket.get(row['outcome'], 0) + 1
        for channel in row['channels']:
            if channel:
                channels[channel] = channels.get(channel, 0) + 1
        sources[row['source']] = sources.get(row['source'], 0) + 1
    totals = {key: sum(b[key] for b in buckets.values()) for key in
              ('total', 'delivered', 'fallback', 'failed', 'ignored', 'unknown', 'pending')}
    return {'days': list(buckets.values()), 'totals': totals,
            'channels': [{'key': k, 'label': CHANNEL_LABELS.get(k, k), 'count': v}
                         for k, v in sorted(channels.items(), key=lambda x: -x[1])],
            'sources': sources, 'generatedAt': utc_now()}


# --------------------------------------------------------------------------
# Read-only probes
# --------------------------------------------------------------------------

def _opener():
    # Never use a proxy for loopback / internal checks.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _get_json(url: str, timeout: float = 3.0):
    with _opener().open(urllib.request.Request(url), timeout=timeout) as response:
        return json.loads(response.read(16384))


def _post_json(url: str, body: dict, headers: dict, timeout: float = 4.0):
    request = urllib.request.Request(
        url, json.dumps(body).encode('utf-8'),
        {'Content-Type': 'application/json', **headers})
    with _opener().open(request, timeout=timeout) as response:
        return json.loads(response.read(16384))


def _tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    with socket.create_connection((host, port), timeout=timeout):
        return True


def gateway_env() -> dict:
    values = {}
    try:
        for line in GATEWAY_ENV.read_text(encoding='utf-8').splitlines():
            key, sep, value = line.strip().partition('=')
            if sep and key in _ENV_KEYS and not key.startswith('#'):
                values[key] = value.strip().strip('"\'')
    except OSError:
        pass
    return values


def _unit(name: str) -> str:
    try:
        completed = subprocess.run(['systemctl', 'is-active', name],
                                   capture_output=True, text=True, timeout=3)
        return (completed.stdout or '').strip() or 'unknown'
    except Exception:
        return 'unknown'


def probe_gateway():
    try:
        data = _get_json(GATEWAY_HEALTH, 3)
        if data.get('status') == 'ok':
            return 'online', '短信 API 正常响应'
        return 'degraded', '健康检查返回异常'
    except Exception as exc:
        return 'offline', '健康检查不可达 ' + type(exc).__name__


def probe_qqbot():
    # Use the single source of truth (same state the QQ settings page reports),
    # so the home overview and the settings page can never disagree.
    try:
        state = extensions.combined_qq_state()
        return state.get('state', 'unknown'), state.get('detail', '状态未知')
    except Exception as exc:
        return 'unknown', '状态探测失败 ' + type(exc).__name__


def probe_napcat():
    try:
        _tcp('127.0.0.1', 13000, 2)
        _tcp('127.0.0.1', 6099, 2)
        return 'online', 'OneBot 与 WebUI 端口正常'
    except Exception:
        return 'offline', '容器端口不可达'


def probe_spug():
    # Connectivity only. NEVER call /send: that would deliver real SMS / email.
    try:
        _tcp('push.spug.cc', 443, 3)
    except Exception:
        return 'offline', '推送域名 443 不可达'
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace('+00:00', 'Z')
    sent = failed = 0
    for event in iter_events():
        if event['ts'] < cutoff or not event['channel'].startswith('spug'):
            continue
        if event['stage'].endswith('_SENT'):
            sent += 1
        elif event['stage'].endswith('_FAILED'):
            failed += 1
    if failed and not sent:
        return 'degraded', '通道可达 但近 24 小时投递失败 ' + str(failed) + ' 次'
    if failed:
        return 'degraded', '通道可达 近 24 小时成功 ' + str(sent) + ' 次 失败 ' + str(failed) + ' 次'
    if sent:
        return 'online', '通道可达 近 24 小时成功 ' + str(sent) + ' 次'
    env = gateway_env()
    configured = bool(env.get('SPUG_CODE_URL') and env.get('SPUG_NOTIFY_URL'))
    if configured:
        return 'online', '通道可达 模板已配置 近期无投递'
    return 'degraded', '通道可达 但未读取到模板配置'


def probe_qqalert():
    state = _unit('sms-gateway-qq-alert.timer')
    if state == 'active':
        return 'online', '巡检定时器运行中'
    return 'offline', '巡检定时器未运行 ' + state


def probe_qqrelogin():
    state = _unit('sms-gateway-qq-relogin.timer')
    if state == 'active':
        return 'online', '自动恢复定时器运行中'
    return 'disabled', '按设计停用 避免风控 ' + state


def probe_nginx():
    ok_ports = []
    for port in (80, 443):
        try:
            _tcp('127.0.0.1', port, 2)
            ok_ports.append(str(port))
        except Exception:
            pass
    if len(ok_ports) == 2:
        return 'online', '80 与 443 监听正常'
    if ok_ports:
        return 'degraded', '仅 ' + ' 与 '.join(ok_ports) + ' 可用'
    return 'offline', '接入端口不可达'


def probe_queue():
    if not INBOX_DIR.is_dir():
        return 'unknown', '未找到待发队列目录'
    pending = total = 0
    try:
        for path in INBOX_DIR.glob('*.json'):
            total += 1
            try:
                if json.loads(path.read_text(encoding='utf-8')).get('state') == 'pending':
                    pending += 1
            except Exception:
                continue
    except OSError:
        return 'unknown', '待发队列不可读'
    if pending:
        return 'degraded', '待发 ' + str(pending) + ' 条 共 ' + str(total) + ' 条'
    return 'online', '无积压 历史记录 ' + str(total) + ' 条'


def probe_disk():
    try:
        usage = shutil.disk_usage('/')
        percent = round(usage.used / usage.total * 100, 1)
    except Exception:
        return 'unknown', '磁盘信息不可读'
    detail = '已用 ' + str(percent) + ' 百分点'
    if percent >= 95:
        return 'offline', detail
    if percent >= 85:
        return 'degraded', detail
    return 'online', detail


def probe_monitor():
    return 'online', '只读监控服务运行中'


SERVICES: list[tuple[str, str, str, Callable]] = [
    ('gateway', '短信网关 API', '核心', probe_gateway),
    ('qqbot', 'QQ 机器人', '转发', probe_qqbot),
    ('napcat', 'NapCat 容器', '转发', probe_napcat),
    ('spug', 'Spug 推送通道', '兜底', probe_spug),
    ('qqalert', '掉线告警巡检', '运维', probe_qqalert),
    ('qqrelogin', '自动恢复任务', '运维', probe_qqrelogin),
    ('nginx', 'Nginx 接入', '接入', probe_nginx),
    ('queue', 'Android 待发队列', '队列', probe_queue),
    ('disk', '磁盘空间', '主机', probe_disk),
    ('monitor', 'Web 检测系统', '运维', probe_monitor),
]

_overview_cache = {'ts': 0.0, 'data': None}
_overview_lock = threading.Lock()


def _run_probe(item):
    key, name, group, func = item
    started = time.monotonic()
    try:
        status, detail = func()
    except Exception as exc:
        status, detail = 'unknown', '探测异常 ' + type(exc).__name__
    return {'id': key, 'name': name, 'group': group, 'status': status,
            'detail': display(detail), 'latencyMs': int((time.monotonic() - started) * 1000),
            'checkedAt': utc_now()}


def build_overview(force: bool = False) -> dict:
    with _overview_lock:
        if not force and _overview_cache['data'] and time.time() - _overview_cache['ts'] < OVERVIEW_TTL:
            return _overview_cache['data']
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_run_probe, item): item[0] for item in SERVICES}
        try:
            for future in as_completed(futures, timeout=9):
                try:
                    row = future.result()
                    results[row['id']] = row
                except Exception:
                    pass
        except Exception:
            pass
    for item in SERVICES:
        key, name, group, _ = item
        results.setdefault(key, {'id': key, 'name': name, 'group': group,
                                 'status': 'unknown', 'detail': '探测超时',
                                 'latencyMs': 0, 'checkedAt': utc_now()})
    services = [results[item[0]] for item in SERVICES]
    summary = {status: sum(1 for row in services if row['status'] == status)
               for status in ('online', 'offline', 'degraded', 'unknown', 'disabled')}
    data = {'services': services, 'summary': summary,
            'checkedAt': utc_now(), 'note': '所有探测均为只读 不会发送任何消息'}
    with _overview_lock:
        _overview_cache['ts'] = time.time()
        _overview_cache['data'] = data
    return data


# --------------------------------------------------------------------------
# HTTP API
# --------------------------------------------------------------------------

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, debug=False)

# Admin/read extensions: QQ bot settings, group selection, Spug quota,
# unmasked system info. All routes inherit the cookie auth middleware below.
import extensions  # noqa: E402  (same directory, provided by --app-dir)
app.include_router(extensions.router)


@app.middleware('http')
async def security_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith('/api/') and path != '/api/login' and not auth.check(request.cookies.get(COOKIE_NAME)):
        return JSONResponse({'detail': 'Unauthorized'}, status_code=401,
                            headers={'Cache-Control': 'no-store'})
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    return response


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@app.get('/health')
async def health():
    return {'status': 'ok'}


@app.post('/api/login')
async def login(body: LoginBody, request: Request):
    ip = request.client.host if request.client else 'unknown'
    ok, reason = auth.verify(body.username, body.password, ip)
    if not ok:
        detail = ('尝试次数过多 请 5 分钟后重试' if reason == 'locked'
                  else '认证服务未就绪' if reason == 'unavailable'
                  else '账号或密码错误')
        return JSONResponse({'detail': detail}, status_code=401)
    token = auth.sign(body.username.strip())
    if not token:
        return JSONResponse({'detail': '认证服务未就绪'}, status_code=503)
    response = JSONResponse({'ok': True, 'username': display(body.username.strip(), 64),
                             'expiresIn': SESSION_TTL})
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_TTL, httponly=True,
                        secure=True, samesite='strict', path='/')
    return response


@app.post('/api/logout')
async def logout():
    response = JSONResponse({'ok': True})
    response.delete_cookie(COOKIE_NAME, path='/')
    return response


@app.get('/api/me')
async def me(request: Request):
    return {'username': auth.check(request.cookies.get(COOKIE_NAME))}


@app.get('/api/meta')
async def meta():
    return {'stageLabels': STAGE_LABELS, 'channelLabels': CHANNEL_LABELS,
            'outcomeLabels': OUTCOME_LABELS, 'sources': ['iphone', 'android', 'system'],
            'serverTime': utc_now()}


@app.get('/api/overview')
async def overview(force: int = Query(default=0)):
    return build_overview(force=bool(force))


@app.get('/api/records')
async def records(since: str = Query(default=''), until: str = Query(default=''),
                  source: str = Query(default=''), channel: str = Query(default=''),
                  outcome: str = Query(default=''), q: str = Query(default=''),
                  page: int = Query(default=1), size: int = Query(default=20)):
    rows = [row for row in aggregate(list(iter_events()))
            if match_filters(row, since=since[:10], until=until[:10], source=source,
                             channel=channel, result='', q=q, outcome=outcome)]
    return paginate(rows, page, size)


@app.get('/api/events')
async def events(since: str = Query(default=''), until: str = Query(default=''),
                 source: str = Query(default=''), channel: str = Query(default=''),
                 result: str = Query(default=''), stage: str = Query(default=''),
                 q: str = Query(default=''), page: int = Query(default=1),
                 size: int = Query(default=30)):
    rows = [row for row in iter_events()
            if match_filters(row, since=since[:10], until=until[:10], source=source,
                             channel=channel, result=result, q=q, stage=stage)]
    rows.sort(key=lambda r: r['ts'], reverse=True)
    return paginate(rows, page, size)


@app.get('/api/stats')
async def stats(days: int = Query(default=7, ge=1, le=90)):
    return build_stats(aggregate(list(iter_events())), days)
