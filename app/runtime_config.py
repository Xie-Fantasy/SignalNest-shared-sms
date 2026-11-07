"""Runtime-editable forwarding target, kept outside the sensitive .env.

The web monitor writes this file; the gateway resolves the target group before
each forward. No service restart, no privilege escalation, no .env change.

Fallback: if the file is missing or invalid, QQ_TARGET_ID from the environment
is used, so an accidental deletion can never break forwarding.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PATH = Path(os.environ.get('SMS_RUNTIME_CONFIG',
                          '/var/lib/sms-gateway/runtime-config.json'))


def _env_default() -> str:
    # sms-gateway.service loads .env via EnvironmentFile, but sms-monitor.service
    # does not. Fall back to reading just this one key from the file so both
    # processes resolve the same default group.
    value = os.environ.get('QQ_TARGET_ID', '').strip()
    if value:
        return value
    try:
        for line in Path('/opt/sms-gateway/.env').read_text(encoding='utf-8').splitlines():
            key, sep, candidate = line.strip().partition('=')
            if sep and key == 'QQ_TARGET_ID':
                return candidate.strip().strip('"\'')
    except OSError:
        pass
    return ''


DEFAULT_GROUP = _env_default()
_lock = threading.Lock()
_cache = {'ts': 0.0, 'value': None}
TTL = 2.0


def _valid(value: str) -> bool:
    return value.isdigit() and 5 <= len(value) <= 12


def target_group() -> str:
    now = time.time()
    with _lock:
        if _cache['value'] and now - _cache['ts'] < TTL:
            return _cache['value']
    value = DEFAULT_GROUP
    try:
        data = json.loads(PATH.read_text(encoding='utf-8'))
        candidate = str(data.get('targetGroupId', '')).strip()
        if _valid(candidate):
            value = candidate
    except Exception:
        pass
    with _lock:
        _cache.update(ts=now, value=value or DEFAULT_GROUP)
        return _cache['value']


def label() -> str:
    return 'QQ群 ' + target_group()


def read_config() -> dict:
    try:
        data = json.loads(PATH.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_target_group(group_id: str, source: str = 'web-monitor') -> dict:
    group_id = str(group_id).strip()
    if not _valid(group_id):
        raise ValueError('invalid group id')
    payload = {
        'targetGroupId': group_id,
        'updatedAt': datetime.now(timezone.utc).isoformat(
            timespec='seconds').replace('+00:00', 'Z'),
        'updatedBy': source,
    }
    PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = PATH.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, PATH)
    with _lock:
        _cache.update(ts=0.0, value=None)
    return payload
