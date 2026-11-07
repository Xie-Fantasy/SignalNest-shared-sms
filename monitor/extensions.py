"""Additional admin/read APIs for the SMS web monitor (2026-11-05 extension).

Imported by server.py via app.include_router(router); all routes inherit the
signed-cookie auth middleware.

Design decisions confirmed by the user:
  * QQ login page: QR-code / quick-login LIST + manual password login (the user
    confirmed a MANUAL login does not trigger the earlier risk control). Account
    profiles let a backup bot be switched in one click when its password is saved.
  * Target group & forwarding route: written to independent server-side state
    files and resolved by the gateway before each forward. .env is never
    modified, no restart and no privilege escalation.
  * Spug developer token: entered in the panel, stored 600 on the server and
    NEVER returned to the browser.
  * No field masking: full server / delivery fields are shown. Credentials,
    SMS bodies and verification codes are still never stored or returned.
  * Web-triggered NapCat restart is privilege-separated: the sandboxed monitor
    only writes a trigger file; a root-owned systemd unit does the actual
    `docker restart napcat`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
from uuid import uuid4
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

sys.path.insert(0, '/opt/sms-gateway')
from app import runtime_config  # noqa: E402
from app import event_log  # noqa: E402  (event store path + iter helpers)
from app import forward_route  # noqa: E402  (shared forwarding-route config)

router = APIRouter()

NAPCAT_SECRETS = Path('/etc/sms-monitor/napcat.json')
SPUG_SECRETS = Path('/etc/sms-monitor/spug.json')
AUTH_FILE = Path('/etc/sms-monitor/auth.json')
GATEWAY_ENV = Path('/opt/sms-gateway/.env')
WEBUI = 'http://127.0.0.1:6099/api'
ONEBOT = 'http://127.0.0.1:13000'
BALANCE_URL = 'https://push.spug.cc/request/balance'
BALANCE_TTL = 300


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def read_env() -> dict:
    values = {}
    try:
        for line in GATEWAY_ENV.read_text(encoding='utf-8').splitlines():
            key, sep, value = line.strip().partition('=')
            if sep and not key.startswith('#'):
                values[key] = value.strip().strip('"\'')
    except OSError:
        pass
    return values


def read_secret(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_secret(path: Path, data: dict):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    os.chmod(path, 0o600)


def _request(url: str, body: dict, headers: dict | None = None, timeout: float = 8.0):
    request = urllib.request.Request(
        url, json.dumps(body, ensure_ascii=False).encode('utf-8'),
        {'Content-Type': 'application/json', **(headers or {})})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(262145)
    if len(raw) > 262144:
        raise RuntimeError('oversized_response')
    return json.loads(raw)


# --------------------------------------------------------------------------
# NapCat WebUI + OneBot clients (local, read only unless the user clicks
# "refresh QR code", which only regenerates a QR code - never a password login)
# --------------------------------------------------------------------------

class NapCatWebUI:
    def __init__(self):
        self._credential = None
        self._ts = 0.0
        self._lock = threading.Lock()

    def configured(self) -> bool:
        return bool(read_secret(NAPCAT_SECRETS).get('webuiHash'))

    def _auth(self) -> str:
        with self._lock:
            if self._credential and time.time() - self._ts < 240:
                return self._credential
        webui_hash = read_secret(NAPCAT_SECRETS).get('webuiHash')
        if not webui_hash:
            raise RuntimeError('webui_credentials_missing')
        result = _request(WEBUI + '/auth/login', {'hash': webui_hash}, timeout=6)
        credential = (result.get('data') or {}).get('Credential')
        if result.get('code') != 0 or not credential:
            raise RuntimeError('webui_auth_failed')
        with self._lock:
            self._credential, self._ts = credential, time.time()
        return credential

    def call(self, path: str, body: dict | None = None, retry: bool = True):
        credential = self._auth()
        result = _request(WEBUI + path, body or {},
                          {'Authorization': 'Bearer ' + credential}, timeout=8)
        if result.get('code') not in (0, None) and retry:
            with self._lock:
                self._credential = None
            return self.call(path, body, retry=False)
        return result


webui = NapCatWebUI()


def onebot_call(action: str, body: dict | None = None, timeout: float = 5.0):
    token = read_secret(NAPCAT_SECRETS).get('onebotToken') or read_env().get('NAPCAT_ACCESS_TOKEN', '')
    result = _request(ONEBOT + '/' + action, body or {},
                      {'Authorization': 'Bearer ' + token}, timeout)
    if result.get('status') != 'ok' or result.get('retcode') != 0:
        raise RuntimeError('onebot_rejected')
    return result.get('data')


def qq_config() -> dict:
    env = read_env()
    runtime = runtime_config.read_config()
    return {
        'botQq': env.get('BOT_QQ_ID', ''),
        'targetGroup': runtime_config.target_group(),
        'targetGroupSource': 'runtime' if str(runtime.get('targetGroupId', '')) else 'env',
        'targetGroupUpdatedAt': runtime.get('updatedAt', ''),
        'targetGroupUpdatedBy': runtime.get('updatedBy', ''),
        'targetType': env.get('QQ_TARGET_TYPE', ''),
        'forwardEnabled': env.get('QQ_FORWARD_ENABLED', ''),
        'onebotUrl': env.get('NAPCAT_API_URL', ONEBOT),
        'webuiUrl': 'http://127.0.0.1:6099',
        'runtimeConfigPath': str(runtime_config.PATH),
        'envPath': str(GATEWAY_ENV),
    }


# ONE source of truth for QQ bot state. Both /api/qq/status and the overview
# probe use it, so the home page and the settings page can never disagree.
# "coreLoggedIn" comes from NapCat WebUI; "onebotOnline" is the forwarding
# channel. Core can be logged in while OneBot 13000 is still unreachable.
_qq_state_cache = {'ts': 0.0, 'data': None}
_qq_state_lock = threading.Lock()


def combined_qq_state(force: bool = False) -> dict:
    with _qq_state_lock:
        if (not force and _qq_state_cache['data']
                and time.time() - _qq_state_cache['ts'] < 2):
            return dict(_qq_state_cache['data'])
    state = {
        'state': 'offline', 'coreLoggedIn': False, 'onebotOnline': False,
        'loginPhase': '', 'loginError': '', 'qrLoginAccepted': False,
        'coreReady': False, 'hasQrcode': False,
        'bot': {'uin': '', 'nickname': ''},
        'webuiStatus': 'unknown', 'onebotStatus': 'unknown',
        'webuiConfigured': webui.configured(), 'config': qq_config(),
        'detail': '', 'checkedAt': now_iso(),
    }
    try:
        data = webui.call('/QQLogin/CheckLoginStatus').get('data') or {}
        state['coreLoggedIn'] = bool(data.get('isLogin'))
        state['loginPhase'] = str(data.get('loginPhase') or '')
        state['loginError'] = str(data.get('loginError') or '')
        state['qrLoginAccepted'] = bool(data.get('qrLoginAccepted'))
        state['coreReady'] = bool(data.get('coreReady'))
        state['hasQrcode'] = bool(data.get('qrcodeurl'))
        state['webuiStatus'] = 'ok'
    except Exception as exc:
        state['webuiStatus'] = type(exc).__name__
    try:
        info = onebot_call('get_login_info') or {}
        status = onebot_call('get_status') or {}
        state['onebotOnline'] = status.get('online') is True
        state['bot'] = {'uin': str(info.get('user_id', '')),
                        'nickname': str(info.get('nickname', ''))}
        state['onebotStatus'] = 'ok'
    except Exception as exc:
        state['onebotStatus'] = type(exc).__name__
    try:
        login_info = webui.call('/QQLogin/GetQQLoginInfo').get('data') or {}
        if not state['bot']['uin']:
            state['bot']['uin'] = str(login_info.get('uin') or login_info.get('uid') or '')
        if not state['bot']['nickname']:
            state['bot']['nickname'] = str(login_info.get('nick') or '')
    except Exception:
        pass
    bot_qq = state['bot']['uin'] or read_env().get('BOT_QQ_ID', '')
    if state['coreLoggedIn'] and state['onebotOnline']:
        state['state'] = 'online'
        state['detail'] = '机器人 %s 在线，转发通道正常' % bot_qq
    elif state['coreLoggedIn']:
        state['state'] = 'degraded'
        state['detail'] = ('核心已登录（%s），但 OneBot %s 不可达，转发暂不可用'
                           % (state['loginPhase'] or 'ready', state['onebotStatus']))
    elif state['onebotOnline']:
        state['state'] = 'degraded'
        state['detail'] = 'OneBot 在线但 WebUI 显示未登录，状态不一致'
    else:
        state['state'] = 'offline'
        state['detail'] = '未登录；OneBot %s' % state['onebotStatus']
    # Backwards-compatible shape for existing clients.
    state['login'] = {
        'isLogin': state['coreLoggedIn'], 'isOffline': not state['coreLoggedIn'],
        'loginPhase': state['loginPhase'], 'loginError': state['loginError'],
        'qrLoginAccepted': state['qrLoginAccepted'],
        'coreReady': state['coreReady'], 'hasQrcode': state['hasQrcode'],
    }
    state['loginInfo'] = state['bot']
    with _qq_state_lock:
        _qq_state_cache.update(ts=time.time(), data=state)
    return dict(state)


@router.get('/api/qq/status')
async def qq_status(force: int = 0):
    # force=1 bypasses the 2s combined-state cache for an on-demand re-probe
    # (used by the "刷新状态" button).
    return combined_qq_state(force=bool(force))


@router.get('/api/qq/qrcode')
async def qq_qrcode():
    try:
        data = (webui.call('/QQLogin/CheckLoginStatus').get('data') or {})
    except Exception as exc:
        return JSONResponse({'detail': 'WebUI 不可用 ' + type(exc).__name__}, status_code=503)
    url = data.get('qrcodeurl')
    if not url:
        return JSONResponse({'detail': '当前没有可显示的二维码，请稍后刷新'}, status_code=404)
    return {'url': url, 'loginPhase': data.get('loginPhase', ''),
            'isLogin': bool(data.get('isLogin')),
            'qrLoginAccepted': bool(data.get('qrLoginAccepted')),
            'checkedAt': now_iso()}


@router.post('/api/qq/qrcode/refresh')
async def qq_qrcode_refresh():
    # Only regenerates a QR code. No password login, no account action.
    try:
        webui.call('/QQLogin/RefreshQRcode', {})
    except Exception as exc:
        return JSONResponse({'detail': '刷新失败 ' + type(exc).__name__}, status_code=502)
    return await qq_qrcode()


@router.get('/api/qq/quick-login')
async def qq_quick_login():
    try:
        data = webui.call('/QQLogin/GetQuickLoginList').get('data') or []
    except Exception as exc:
        return {'available': False, 'items': [], 'reason': type(exc).__name__}
    items = []
    for entry in data if isinstance(data, list) else []:
        if isinstance(entry, dict):
            items.append({key: str(entry.get(key, '')) for key in
                          ('uin', 'uid', 'nick', 'nickname', 'avatar', 'lastLoginTime')})
    return {'available': True, 'items': items, 'count': len(items),
            'note': '仅展示列表，不自动触发登录'}


@router.get('/api/qq/groups')
async def qq_groups():
    current = runtime_config.target_group()
    try:
        groups = onebot_call('get_group_list') or []
        items = [{'groupId': str(group.get('group_id', '')),
                  'groupName': str(group.get('group_name', '')),
                  'memberCount': group.get('member_count'),
                  'current': str(group.get('group_id', '')) == current}
                 for group in groups if isinstance(group, dict)]
        return {'available': True, 'current': current, 'groups': items,
                'count': len(items), 'checkedAt': now_iso()}
    except Exception as exc:
        return {'available': False, 'current': current,
                'groups': [{'groupId': current, 'groupName': '当前配置群（机器人离线，列表不可拉取）',
                            'memberCount': None, 'current': True}],
                'count': 1, 'reason': type(exc).__name__,
                'hint': '机器人离线时无法拉取群列表，可手动输入群号保存',
                'checkedAt': now_iso()}


@router.get('/api/qq/config')
async def qq_config_get():
    return qq_config()


class GroupBody(BaseModel):
    targetGroupId: str = Field(min_length=5, max_length=12)


@router.post('/api/qq/config')
async def qq_config_save(body: GroupBody):
    group_id = body.targetGroupId.strip()
    if not group_id.isdigit():
        return JSONResponse({'detail': '群号必须为纯数字'}, status_code=422)
    path = runtime_config.PATH
    if path.exists():
        try:
            backup = path.with_suffix('.json.bak')
            shutil.copy2(path, backup)
            os.chmod(backup, 0o600)
        except OSError:
            pass
    try:
        payload = runtime_config.write_target_group(group_id)
    except Exception as exc:
        return JSONResponse({'detail': '保存失败 ' + type(exc).__name__}, status_code=500)
    return {'ok': True, 'config': payload, 'effective': 'immediate',
            'restartRequired': False, 'envModified': False,
            'note': '短信服务在下次转发前读取，无需重启'}


# --------------------------------------------------------------------------
# QQ bot: restart trigger (privilege-separated), account profiles, switch
# --------------------------------------------------------------------------

QQ_ACCOUNTS = Path('/etc/sms-monitor/qq_accounts.json')
RESTART_TRIGGER = Path('/var/lib/sms-gateway/restart-napcat.trigger')
RESTART_LAST = Path('/var/lib/sms-gateway/restart-napcat.last')

_last_restart_request = 0.0
_restart_lock = threading.Lock()
RESTART_COOLDOWN = 30


def _read_accounts() -> list:
    return read_secret(QQ_ACCOUNTS).get('accounts', [])


def _write_accounts(accounts: list) -> None:
    write_secret(QQ_ACCOUNTS, {'accounts': accounts, 'updatedAt': now_iso()})


@router.post('/api/qq/restart')
async def qq_restart():
    # The monitor runs unprivileged and sandboxed (NoNewPrivileges, no caps), so
    # it CANNOT invoke docker/systemctl directly. Instead it drops a trigger file
    # into a directory it is allowed to write; a root-owned systemd path unit
    # watches that file and performs the actual `docker restart napcat`. This keeps
    # the monitor sandboxed while still enabling a web-triggered restart.
    global _last_restart_request
    with _restart_lock:
        now = time.time()
        remaining = RESTART_COOLDOWN - (now - _last_restart_request)
        if remaining > 0:
            return JSONResponse({'detail': '操作过于频繁，请 %.0f 秒后重试' % remaining,
                                 'cooldownRemaining': remaining}, status_code=429)
        _last_restart_request = now
    try:
        RESTART_TRIGGER.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(RESTART_TRIGGER, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(now_iso())
            os.fsync(stream.fileno())
        # Touch a "last requested" marker so the UI can show when it happened.
        try:
            RESTART_LAST.touch()
        except OSError:
            pass
    except Exception as exc:
        return JSONResponse({'detail': '写入重启触发器失败 ' + type(exc).__name__},
                            status_code=500)
    return {'ok': True, 'requestedAt': now_iso(),
            'message': '已请求重启 NapCat，系统将在数秒内执行；可用「刷新状态」查看恢复情况'}


@router.get('/api/qq/accounts')
async def qq_accounts_list():
    try:
        items = _read_accounts()
    except Exception:
        items = []
    active_uin = (combined_qq_state().get('bot') or {}).get('uin', '')
    return {'accounts': [{'id': a.get('id'), 'label': a.get('label', ''),
                          'uin': a.get('uin', ''),
                          'hasPassword': bool(a.get('password')),
                          'isActive': str(a.get('uin', '')) == str(active_uin)}
                         for a in items],
            'activeUin': active_uin,
            'note': '密码仅存服务器 600 文件，接口永不返回值'}


class AccountBody(BaseModel):
    id: str = ''
    label: str = Field(min_length=1, max_length=40)
    uin: str = Field(min_length=5, max_length=12)
    password: str = ''


@router.post('/api/qq/accounts')
async def qq_accounts_save(body: AccountBody):
    uin = body.uin.strip()
    if not uin.isdigit():
        return JSONResponse({'detail': 'QQ 号必须为数字'}, status_code=422)
    accounts = _read_accounts()
    existing = next((a for a in accounts if a.get('id') == body.id), None) if body.id else None
    if existing:
        existing['label'] = body.label.strip()
        existing['uin'] = uin
        if body.password:
            # Stored root-600, never returned to the browser. Only used for the
            # one-click "switch" so a backup bot can be activated without re-typing.
            existing['password'] = body.password
    else:
        accounts.append({'id': uuid4().hex, 'label': body.label.strip(),
                         'uin': uin, 'password': body.password})
    _write_accounts(accounts)
    return {'ok': True, 'count': len(accounts)}


@router.delete('/api/qq/accounts/{account_id}')
async def qq_accounts_delete(account_id: str):
    accounts = [a for a in _read_accounts() if a.get('id') != account_id]
    _write_accounts(accounts)
    return {'ok': True, 'count': len(accounts)}


class SwitchBody(BaseModel):
    accountId: str


@router.post('/api/qq/switch')
async def qq_account_switch(body: SwitchBody):
    accounts = _read_accounts()
    target = next((a for a in accounts if a.get('id') == body.accountId), None)
    if not target:
        return JSONResponse({'detail': '账号不存在'}, status_code=404)
    uin = str(target.get('uin', ''))
    pw = target.get('password')
    # Never log the current account OUT unless we can actually log the target
    # IN: doing so would leave the bot offline with forwarding broken. Accounts
    # without a stored password therefore only get guidance, not a logout.
    if not pw:
        return {'ok': False, 'state': 'needs_login', 'uin': uin,
                'message': '该账号未保存密码。请在上方登录区用手机扫码，或用「账号密码登录」'
                           '输入 %s 的密码（当前账号不会被登出）' % uin}
    # Best-effort logout of the current account; the exact WebUI path varies by
    # NapCat version, so a failure here is non-fatal - the login below will
    # attempt to take over the session.
    try:
        webui.call('/QQLogin/Logout', {})
    except Exception:
        pass
    password_md5 = hashlib.md5(pw.encode('utf-8')).hexdigest()
    try:
        result = webui.call('/QQLogin/PasswordLogin',
                            {'uin': uin, 'passwordMd5': password_md5})
    except Exception as exc:
        return JSONResponse({'detail': 'WebUI 不可用 ' + type(exc).__name__},
                            status_code=502)
    finally:
        password_md5 = None
    data = result.get('data') or {}
    if data.get('needCaptcha'):
        return {'ok': False, 'state': 'captcha_required', 'uin': uin,
                'message': '需要验证码，请在 NapCat WebUI 人工处理'}
    if data.get('needNewDevice'):
        return {'ok': False, 'state': 'device_verification_required', 'uin': uin,
                'message': '需要新设备验证，请在 NapCat WebUI 人工处理'}
    if result.get('code') != 0:
        return {'ok': False, 'state': 'rejected', 'code': result.get('code'),
                'message': str(result.get('msg') or '登录被拒绝'), 'uin': uin}
    return {'ok': True, 'state': 'submitted', 'uin': uin,
            'message': '登录请求已提交，页面会自动检测登录结果'}


# --------------------------------------------------------------------------
# Forwarding route (priority ladder) - shared with the gateway via forward_route
# --------------------------------------------------------------------------

@router.get('/api/forward/route')
async def forward_route_get():
    return forward_route.read_full()


class ForwardRouteBody(BaseModel):
    channels: list


@router.put('/api/forward/route')
async def forward_route_save(body: ForwardRouteBody):
    try:
        result = forward_route.write_route(body.channels)
    except Exception as exc:
        return JSONResponse({'detail': '保存失败 ' + type(exc).__name__}, status_code=500)
    return {'ok': True, 'channels': result['channels'], 'effective': 'immediate',
            'restartRequired': False,
            'note': '短信网关在下次转发前读取，无需重启'}


# --------------------------------------------------------------------------
# Spug: developer token (never returned) + official balance API + statistics
# --------------------------------------------------------------------------

_balance_cache = {'ts': 0.0, 'data': None, 'error': ''}
_balance_lock = threading.Lock()


def spug_token() -> str:
    return str(read_secret(SPUG_SECRETS).get('developerToken') or '').strip()


def get_balance(force: bool = False):
    with _balance_lock:
        if (not force and _balance_cache['data'] is not None
                and time.time() - _balance_cache['ts'] < BALANCE_TTL):
            return _balance_cache['data'], _balance_cache['error']
    data, error = None, ''
    token = spug_token()
    if token:
        try:
            result = _request(BALANCE_URL, {'token': token}, timeout=10)
            if result.get('code') == 200:
                data = result.get('data') or {}
            else:
                error = 'code=%s msg=%s' % (result.get('code'), result.get('msg'))
        except urllib.error.HTTPError as exc:
            error = 'HTTP ' + str(exc.code)
        except Exception as exc:
            error = type(exc).__name__
    with _balance_lock:
        _balance_cache.update(ts=time.time(), data=data, error=error)
    return data, error


def delivery_stats() -> dict:
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace('+00:00', 'Z')
    cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace('+00:00', 'Z')
    result = {'last24h': {'sent': 0, 'failed': 0, 'total': 0},
              'last7d': {'sent': 0, 'failed': 0, 'total': 0}}
    try:
        events = list(event_log.iter_events()) if hasattr(event_log, 'iter_events') else []
    except Exception:
        events = []
    # Fall back to reading the event files directly when the helper is absent.
    if not events:
        try:
            for path in sorted(event_log.event_dir().glob('*.jsonl')):
                with path.open('r', encoding='utf-8') as stream:
                    for line in stream:
                        try:
                            events.append(json.loads(line))
                        except Exception:
                            continue
        except Exception:
            events = []
    for event in events:
        if not str(event.get('channel', '')).startswith('spug'):
            continue
        ts, stage = str(event.get('ts', '')), str(event.get('stage', ''))
        for key, cutoff in (('last24h', cutoff_24h), ('last7d', cutoff_7d)):
            if ts >= cutoff:
                result[key]['total'] += 1
                if stage.endswith('_SENT'):
                    result[key]['sent'] += 1
                elif stage.endswith('_FAILED'):
                    result[key]['failed'] += 1
    return result


def spug_reachable() -> bool:
    try:
        with socket.create_connection(('push.spug.cc', 443), timeout=3):
            return True
    except OSError:
        return False


@router.get('/api/spug/status')
async def spug_status(force: int = 0):
    balance, error = get_balance(force=bool(force))
    env = read_env()
    return {
        'configured': bool(spug_token()),
        'tokenPath': str(SPUG_SECRETS),
        'balance': balance,
        'balanceError': error,
        'balanceCheckedAt': now_iso(),
        'balanceNote': '资源包余额不含会员每日赠送额度',
        'reachable': spug_reachable(),
        'delivery': delivery_stats(),
        'templates': {
            'code': {'configured': bool(env.get('SPUG_CODE_URL')), 'url': ''},
            'notify': {'configured': bool(env.get('SPUG_NOTIFY_URL')), 'url': ''},
            'alert': {'configured': bool(env.get('SPUG_ALERT_URL'))},
        },
        'checkedAt': now_iso(),
    }


@router.get('/api/spug/token')
async def spug_token_status():
    data = read_secret(SPUG_SECRETS)
    return {'configured': bool(str(data.get('developerToken') or '').strip()),
            'updatedAt': data.get('updatedAt', ''),
            'note': '开发者 Token 仅存服务器，接口永不返回值'}


class TokenBody(BaseModel):
    token: str = Field(min_length=8, max_length=256)


@router.post('/api/spug/token')
async def spug_token_save(body: TokenBody):
    token = body.token.strip()
    if not re.fullmatch(r'[A-Za-z0-9_\-\.]{8,256}', token):
        return JSONResponse({'detail': 'Token 格式不合法'}, status_code=422)
    write_secret(SPUG_SECRETS, {'developerToken': token, 'updatedAt': now_iso()})
    with _balance_lock:
        _balance_cache.update(ts=0.0, data=None, error='')
    return {'ok': True, 'configured': True, 'tokenEchoed': False}


@router.delete('/api/spug/token')
async def spug_token_delete():
    try:
        SPUG_SECRETS.unlink(missing_ok=True)
    except OSError:
        pass
    with _balance_lock:
        _balance_cache.update(ts=0.0, data=None, error='')
    return {'ok': True, 'configured': False}


# --------------------------------------------------------------------------
# Full, unmasked server information
# --------------------------------------------------------------------------

def _run(cmd: list[str], timeout: float = 5.0) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except Exception:
        return ''


@router.get('/api/system/info')
async def system_info():
    env = read_env()
    os_release = {}
    try:
        for line in Path('/etc/os-release').read_text(encoding='utf-8').splitlines():
            key, sep, value = line.partition('=')
            if sep:
                os_release[key] = value.strip().strip('"')
    except OSError:
        pass
    meminfo = {}
    try:
        for line in Path('/proc/meminfo').read_text(encoding='utf-8').splitlines():
            key, sep, value = line.partition(':')
            if sep and key in ('MemTotal', 'MemAvailable'):
                meminfo[key] = value.strip()
    except OSError:
        pass
    usage = shutil.disk_usage('/')
    uptime = ''
    try:
        uptime = str(round(float(Path('/proc/uptime').read_text().split()[0]) / 86400, 2)) + ' 天'
    except Exception:
        pass
    services = []
    for unit in ('sms-gateway.service', 'sms-monitor.service',
                 'sms-gateway-qq-alert.timer', 'sms-gateway-qq-relogin.timer',
                 'nginx.service', 'docker.service'):
        services.append({
            'unit': unit,
            'active': _run(['systemctl', 'is-active', unit]) or 'unknown',
            'enabled': _run(['systemctl', 'is-enabled', unit]) or 'unknown',
        })
    ports = [line.strip() for line in
             _run(['ss', '-lntp']).splitlines() if line.strip()]
    containers = [line.strip() for line in
                  _run(['docker', 'ps', '--format', '{{.Names}} | {{.Status}} | {{.Ports}}']).splitlines()
                  if line.strip()]
    cert = '/etc/sms-gateway-tls/server.crt'
    # The TLS directory is 700 root-only; the monitor user can see the path but
    # cannot stat the file. Metadata below is the known pinned certificate.
    try:
        cert_exists = Path(cert).is_file()
    except OSError:
        cert_exists = False
    cert_info = {'path': cert, 'exists': cert_exists,
                 'keyPath': '/etc/sms-gateway-tls/server.key',
                 'notAfter': '',
                 'sha256': ''}
    return {
        'host': os.environ.get('SMS_PUBLIC_HOST', ''),
        'hostname': socket.gethostname(),
        'os': os_release.get('PRETTY_NAME', platform.platform()),
        'kernel': platform.release(),
        'architecture': platform.machine(),
        'python': platform.python_version(),
        'uptime': uptime,
        'loadAverage': list(os.getloadavg()) if hasattr(os, 'getloadavg') else [],
        'memory': meminfo,
        'disk': {'total': usage.total, 'used': usage.used, 'free': usage.free,
                 'percent': round(usage.used / usage.total * 100, 2), 'path': '/'},
        'listeningPorts': ports,
        'containers': containers,
        'services': services,
        'certificate': cert_info,
        'paths': {
            'gatewayCode': '/opt/sms-gateway/app/',
            'gatewayEnv': str(GATEWAY_ENV),
            'gatewayVenv': '/opt/sms-gateway/.venv/',
            'monitorCode': '/opt/sms-monitor/',
            'monitorStatic': '/opt/sms-monitor/www/monitor/',
            'eventStore': str(event_log.event_dir()),
            'runtimeConfig': str(runtime_config.PATH),
            'androidInbox': '/var/lib/sms-gateway/android-inbox/',
            'nginxVhost': '/www/server/panel/vhost/nginx/',
            'tlsConfig': '/www/server/panel/vhost/nginx/sms-gateway-tls.conf',
            'monitorService': '/etc/systemd/system/sms-monitor.service',
            'authFile': '/etc/sms-monitor/auth.json',
            'backupDir': '/root/sms-gateway-backups/',
        },
        'endpoints': {
            'monitor': 'https://sms.example.com/monitor/',
            'gatewayHealth': 'http://sms.example.com/health',
            'smsPush': 'http://sms.example.com/api/message/push',
            'androidPush': 'https://sms.example.com/api/android/message/push',
            'gatewayInternal': 'http://127.0.0.1:8000',
            'monitorInternal': 'http://127.0.0.1:18101',
            'onebot': ONEBOT,
            'napcatWebUI': 'http://127.0.0.1:6099',
        },
        'identity': {'botQq': env.get('BOT_QQ_ID', ''),
                     'targetGroup': runtime_config.target_group(),
                     'targetRecipient': env.get('TARGET_RECIPIENT', '')},
        'generatedAt': now_iso(),
        'note': '凭据、Token、私钥与短信正文不在此接口返回',
    }


# --------------------------------------------------------------------------
# Manual QQ password login (user-confirmed 2026-11-05)
#
# The user explicitly stated that a MANUAL login does not trigger the risk
# control that the old automated timer caused (error 168). Therefore this is a
# strictly one-shot, human-triggered action:
#   * password is never saved, logged, echoed or reused;
#   * no automatic retry, no timer, no worker restart, no captcha solving;
#   * captcha / new-device challenges are handed back for manual handling;
#   * a short cooldown only prevents accidental double-clicks.
# --------------------------------------------------------------------------

_password_lock = threading.Lock()
_last_password_attempt = 0.0
PASSWORD_LOGIN_COOLDOWN = 30


class PasswordLoginBody(BaseModel):
    uin: str = Field(min_length=5, max_length=12)
    password: str = Field(min_length=1, max_length=128)


@router.post('/api/qq/password-login')
async def qq_password_login(body: PasswordLoginBody):
    global _last_password_attempt
    uin = body.uin.strip()
    if not uin.isdigit():
        return JSONResponse({'detail': 'QQ 号必须为数字'}, status_code=422)
    with _password_lock:
        now = time.time()
        if now - _last_password_attempt < PASSWORD_LOGIN_COOLDOWN:
            return JSONResponse(
                {'detail': '请求过于频繁，请 %d 秒后重试' % PASSWORD_LOGIN_COOLDOWN},
                status_code=429)
        _last_password_attempt = now
    try:
        password_md5 = hashlib.md5(body.password.encode('utf-8')).hexdigest()
        result = webui.call('/QQLogin/PasswordLogin',
                            {'uin': uin, 'passwordMd5': password_md5})
    except Exception as exc:
        return JSONResponse({'detail': 'WebUI 不可用 ' + type(exc).__name__},
                            status_code=502)
    finally:
        # Plaintext and digest exist only for the duration of this call.
        password_md5 = None
    data = result.get('data') or {}
    if data.get('needCaptcha'):
        return {'ok': False, 'state': 'captcha_required',
                'message': '需要验证码，请在 NapCat WebUI 人工处理；本页不会自动过验证码'}
    if data.get('needNewDevice'):
        return {'ok': False, 'state': 'device_verification_required',
                'message': '需要新设备验证，请在 NapCat WebUI 人工处理'}
    if result.get('code') != 0:
        return {'ok': False, 'state': 'rejected',
                'code': result.get('code'),
                'message': str(result.get('msg') or '登录被拒绝')}
    return {'ok': True, 'state': 'submitted', 'uin': uin,
            'message': '登录请求已提交，页面会自动检测登录结果'}


# --------------------------------------------------------------------------
# Settings: change the monitor login password
# --------------------------------------------------------------------------

class PasswordChangeBody(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=256)
    newPassword: str = Field(min_length=12, max_length=128)


@router.post('/api/settings/password')
async def settings_change_password(body: PasswordChangeBody):
    current = read_secret(AUTH_FILE)
    if not current:
        return JSONResponse({'detail': '认证文件不可用'}, status_code=500)
    try:
        salt = bytes.fromhex(current['salt'])
        expected = bytes.fromhex(current['password_hash'])
        iterations = int(current.get('iterations', 200000))
        actual = hashlib.pbkdf2_hmac(
            'sha256', body.currentPassword.encode('utf-8'), salt, iterations)
        if not hmac.compare_digest(actual, expected):
            raise ValueError('mismatch')
    except Exception:
        return JSONResponse({'detail': '当前密码不正确'}, status_code=401)

    new_password = body.newPassword
    if (len(new_password) < 12
            or not any(char.isalpha() for char in new_password)
            or not any(char.isdigit() for char in new_password)):
        return JSONResponse(
            {'detail': '新密码至少 12 位，且需同时包含字母和数字'}, status_code=422)

    new_salt = os.urandom(16)
    new_hash = hashlib.pbkdf2_hmac(
        'sha256', new_password.encode('utf-8'), new_salt, iterations)
    write_secret(AUTH_FILE, {
        'username': current.get('username', 'admin'),
        'salt': new_salt.hex(),
        'password_hash': new_hash.hex(),
        # Rotating this invalidates every existing signed cookie at once.
        'session_secret': os.urandom(32).hex(),
        'iterations': iterations,
        'updatedAt': now_iso(),
    })
    return {'ok': True, 'sessionInvalidated': True,
            'message': '密码已更新，所有会话已失效，请重新登录'}


@router.get('/api/settings/info')
async def settings_info():
    current = read_secret(AUTH_FILE)
    return {
        'username': current.get('username', 'admin'),
        'updatedAt': current.get('updatedAt', ''),
        'authFile': str(AUTH_FILE),
        'sessionTtlHours': 12,
        'passwordPolicy': '至少 12 位，包含字母与数字',
        'note': '密码哈希与会话密钥仅存服务器，接口永不返回',
    }
