"""Append-only delivery metadata for the authenticated monitor.

Full sender/recipient identifiers may be recorded. Message bodies, verification
codes and credentials must never be passed to emit(). Logging failures do not
interrupt delivery. Only one gateway process is supported.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()
_DIR = Path(os.environ.get('SMS_EVENT_DIR', '/var/lib/sms-gateway/events'))
_ENABLED = os.environ.get('SMS_EVENT_LOG_ENABLED', 'true').lower() == 'true'

# 2026-11-05: user explicitly asked that server / delivery fields are NOT
# masked. Full sender, recipient, QQ numbers, group ids, paths and IPs are now
# stored. Only control characters, backslashes and angle brackets are rejected
# (JSON is produced by json.dumps and React escapes on render, but this keeps
# the JSONL clean and blocks trivial injection). Message bodies, verification
# codes and tokens are still NEVER passed to emit() by any caller.
_FORBIDDEN = re.compile(r'[\x00-\x1f\x7f<>\\]')
_MAX_FIELD = 256
_SOURCES = frozenset({'iphone', 'android', 'system'})
_RESULTS = frozenset({'ok', 'failed', 'ignored', 'unknown', 'pending'})
_STAGES = frozenset({
    'RECEIVED', 'IGNORED', 'ACCEPTED', 'SKIPPED',
    'QQ_FORWARDED', 'QQ_FORWARD_FAILED',
    'SPUG_CODE_SENT', 'SPUG_CODE_FAILED',
    'SPUG_NOTIFY_SENT', 'SPUG_NOTIFY_FAILED',
    'ANDROID_ACCEPTED', 'ANDROID_DEDUP', 'ANDROID_IGNORED',
    'ANDROID_EXPIRED', 'ANDROID_DELIVERED', 'ANDROID_DELIVERY_UNKNOWN',
    'SERVICE_STATE',
})


def _clean(value) -> str:
    if value is None:
        return ''
    text = str(value)
    if len(text) > _MAX_FIELD:
        text = text[:_MAX_FIELD]
    return '[redacted]' if _FORBIDDEN.search(text) else text


def new_trace() -> str:
    """Opaque correlation id for one inbound SMS; never derived from content."""
    return secrets.token_hex(8)


def mask_phone(value) -> str:
    if not value:
        return '[unrecognized]'
    digits = re.sub(r'\D', '', str(value))
    if len(digits) < 7:
        return '[redacted]'
    return digits[:3] + '****' + digits[-4:]


def mask_sender(value) -> str:
    digits = re.sub(r'\D', '', str(value or ''))
    if len(digits) < 7:
        return '[redacted]'
    return digits[:3] + '****' + digits[-4:]


def event_dir() -> Path:
    return _DIR


def emit(stage, *, trace='', source='iphone', channel='', result='',
         target='', sender='', recipient='', length=None, note='',
         origin='live', ts=None):
    """Append one event. Never raises, never blocks on external I/O."""
    if not _ENABLED:
        return
    try:
        timestamp = ts or datetime.now(timezone.utc).isoformat(
            timespec='milliseconds').replace('+00:00', 'Z')
        record = {
            'ts': timestamp,
            'trace': _clean(trace) or new_trace(),
            'source': source if source in _SOURCES else 'system',
            'stage': stage if stage in _STAGES else 'OTHER',
            'channel': _clean(channel),
            'result': result if result in _RESULTS else 'unknown',
            'target': _clean(target),
            'sender': _clean(sender),
            'recipient': _clean(recipient),
            'length': length if isinstance(length, int) and 0 <= length <= 65536 else None,
            'note': _clean(note),
            'origin': 'backfill' if origin == 'backfill' else 'live',
        }
        data = (json.dumps(record, ensure_ascii=False,
                           separators=(',', ':')) + '\n').encode('utf-8')
        with _LOCK:
            _DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
            day = (ts or datetime.now(timezone.utc).isoformat())[:10]
            path = _DIR / (day + '.jsonl')
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)
    except Exception:
        # Logging must never influence delivery, even on disk-full or EPERM.
        pass
