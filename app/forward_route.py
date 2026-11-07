"""Configurable forwarding-route (priority ladder) shared by the gateway and the
web monitor.

The web monitor writes this file; the gateway resolves the ordered, enabled
channel list before each forward and tries them in sequence. No service
restart, no privilege escalation, no .env change.

Safety:
  * If the file is missing or invalid, the DEFAULT route (qq_bot -> sms) is
    used, so an accidental deletion can never break forwarding.
  * Only known channel keys are accepted; unknown entries are dropped.
  * Per-channel enable flags let the user turn a channel off without deleting it.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

PATH = Path(os.environ.get('SMS_FORWARD_ROUTE',
                           '/var/lib/sms-gateway/forward-route.json'))

# Channels the system knows how to use. `sms` here means the Spug fallback
# (verification-code SMS + offline-notice SMS/email). Extend this list when new
# channels (e.g. webhook, email) are implemented.
KNOWN_CHANNELS = ('qq_bot', 'sms')

DEFAULT_ROUTE = [
    {'key': 'qq_bot', 'enabled': True,
     'label': 'QQ 机器人', 'desc': '通过 OneBot 转发到 QQ 群'},
    {'key': 'sms', 'enabled': True,
     'label': 'Spug 短信兜底', 'desc': 'QQ 不可用时以短信/邮件兜底'},
]

_lock = threading.Lock()
_cache = {'ts': 0.0, 'value': None}
TTL = 2.0


def _normalize(data: object) -> list[dict]:
    """Return a validated, ordered list of channel dicts.

    Unknown keys are dropped; missing keys are re-added from defaults; the
    final order is the user's saved order, falling back to DEFAULT_ROUTE when
    the saved data is unusable.
    """
    if not isinstance(data, dict):
        return [dict(c) for c in DEFAULT_ROUTE]
    raw = data.get('channels')
    if not isinstance(raw, list) or not raw:
        return [dict(c) for c in DEFAULT_ROUTE]
    by_key = {c['key']: c for c in DEFAULT_ROUTE}
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get('key', ''))
        if key not in by_key:
            continue
        enabled = bool(item.get('enabled', by_key[key]['enabled']))
        out.append({'key': key, 'enabled': enabled,
                    'label': by_key[key]['label'], 'desc': by_key[key]['desc']})
    # Ensure every known channel appears exactly once, appending any missing.
    seen = {c['key'] for c in out}
    for c in DEFAULT_ROUTE:
        if c['key'] not in seen:
            out.append(dict(c))
    return out


def read_route() -> list[dict]:
    now = time.time()
    with _lock:
        if _cache['value'] is not None and now - _cache['ts'] < TTL:
            return _cache['value']
    value = DEFAULT_ROUTE
    try:
        data = json.loads(PATH.read_text(encoding='utf-8'))
        value = _normalize(data)
    except Exception:
        value = [dict(c) for c in DEFAULT_ROUTE]
    with _lock:
        _cache.update(ts=now, value=value)
        return _cache['value']


def enabled_channels() -> list[str]:
    """Ordered list of enabled channel keys for the gateway to try."""
    return [c['key'] for c in read_route() if c.get('enabled')]


def read_full() -> dict:
    return {'channels': read_route(),
            'knownChannels': list(KNOWN_CHANNELS),
            'path': str(PATH)}


def write_route(channels: list[dict]) -> dict:
    normalized = _normalize({'channels': channels})
    PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = PATH.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump({'channels': normalized}, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, PATH)
    with _lock:
        _cache.update(ts=0.0, value=None)
    return {'ok': True, 'channels': normalized, 'path': str(PATH)}
