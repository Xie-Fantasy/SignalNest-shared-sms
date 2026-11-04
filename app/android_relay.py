"""Durable Android inbox without a database or changes to the iPhone protocol.

Once a OneBot send has started, ambiguous failures are never automatically retried.
The private spool erases message contents after delivery, failure, or expiry.
"""
import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AndroidMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    deviceId: str
    clientMessageId: str
    sender: str = Field(min_length=1, max_length=256)
    recipient: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=10000)
    receivedAt: str = Field(min_length=1, max_length=128)
    simVerified: bool

    @field_validator('deviceId', 'clientMessageId')
    @classmethod
    def uuid_only(cls, value):
        try:
            canonical = str(uuid.UUID(value))
        except ValueError:
            raise ValueError('Canonical UUID required') from None
        if canonical != value:
            raise ValueError('Canonical UUID required')
        return value

    @field_validator('receivedAt')
    @classmethod
    def aware_time(cls, value):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError('Invalid timestamp') from None
        if parsed.tzinfo is None:
            raise ValueError('Timezone required')
        return value


class AndroidInbox:
    def __init__(self, directory, normalize, target, forward, legacy_model, qq_enabled, can_send=None):
        self.directory = Path(directory)
        self.normalize = normalize
        self.target = target
        self.forward = forward
        self.legacy_model = legacy_model
        self.qq_enabled = qq_enabled
        self.can_send = can_send
        self.lock = asyncio.Lock()
        self.task = None

    def write(self, path, record):
        # Temp file, fsync, rename and directory fsync make ACK survive power loss.
        temp = path.with_suffix('.tmp')
        fd = os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(record, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        if os.name == 'posix':
            fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    async def start(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        # A crash during OneBot submission is ambiguous, so never replay it.
        for path in self.directory.glob('*.json'):
            record = json.loads(path.read_text(encoding='utf-8'))
            if record['state'] == 'sending':
                record['state'] = 'delivery_unknown'
                record.pop('payload', None)
                self.write(path, record)
        self.task = asyncio.create_task(self.run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def accept(self, payload):
        if not payload.simVerified:
            raise HTTPException(400, 'SIM verification required')
        if self.normalize(payload.recipient) != self.target:
            return {'success': True, 'accepted': False, 'reason': 'recipient_not_allowed'}
        received = datetime.fromisoformat(payload.receivedAt.replace('Z', '+00:00')).timestamp()
        now = time.time()
        if received > now + 120:
            raise HTTPException(400, 'Invalid message time')
        if now - received >= 600:
            return {'success': True, 'accepted': False, 'reason': 'expired'}
        key = hashlib.sha256((payload.deviceId + ':' + payload.clientMessageId).encode()).hexdigest()
        path = self.directory / (key + '.json')
        digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
        async with self.lock:
            if path.exists():
                record = json.loads(path.read_text(encoding='utf-8'))
                if record['digest'] != digest:
                    raise HTTPException(409, 'Message ID already used')
                return {'success': True, 'accepted': True, 'deduplicated': True,
                        'delivery': record['state']}
            if sum(1 for p in self.directory.glob('*.json')) >= 20000:
                return JSONResponse({'detail': 'Inbox capacity reached'}, status_code=503)
            self.write(path, {'digest': digest, 'state': 'pending', 'created': now,
                              'expires': received + 600, 'payload': payload.model_dump()})
        return {'success': True, 'accepted': True, 'delivery': 'pending'}

    async def cycle(self):
        ready = None
        for path in list(self.directory.glob('*.json')):
            payload = None
            async with self.lock:
                record = json.loads(path.read_text(encoding='utf-8'))
                if time.time() - record['created'] > 7 * 86400:
                    path.unlink()
                    continue
                if record['state'] != 'pending':
                    continue
                if time.time() >= record['expires']:
                    record['state'] = 'expired'
                    record.pop('payload', None)
                    self.write(path, record)
                    continue
                if not self.qq_enabled:
                    continue
                if ready is None:
                    ready = True if self.can_send is None else await asyncio.to_thread(self.can_send)
                if not ready:
                    continue
                if time.time() >= record['expires']:
                    record['state'] = 'expired'
                    record.pop('payload', None)
                    self.write(path, record)
                    continue
                record['state'] = 'sending'
                self.write(path, record)
                data = record['payload']
                payload = self.legacy_model(**{k: data[k] for k in
                                              ('sender', 'recipient', 'message', 'receivedAt')})
            try:
                await asyncio.to_thread(self.forward, payload)
                state = 'delivered'
            except Exception:
                state = 'delivery_unknown'
            async with self.lock:
                record['state'] = state
                record.pop('payload', None)
                self.write(path, record)

    async def run(self):
        while True:
            try:
                await self.cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Do not log exception text or any payload.
                pass
            await asyncio.sleep(2)


def install(api, normalize, target, forward, legacy_model, qq_enabled, can_send=None):
    inbox = AndroidInbox(os.environ.get('ANDROID_INBOX_DIR', '/var/lib/sms-gateway/android-inbox'),
                         normalize, target, forward, legacy_model, qq_enabled, can_send)
    @asynccontextmanager
    async def lifespan(application):
        await inbox.start()
        try:
            yield
        finally:
            await inbox.stop()
    api.router.lifespan_context = lifespan

    @api.get('/api/android/status')
    async def status():
        return {'status': 'ok', 'protocol': 2, 'recipient': target,
                'qqConfigured': qq_enabled, 'expirySeconds': 600}

    @api.post('/api/android/message/push')
    async def push_android(payload: AndroidMessage):
        return await inbox.accept(payload)

    @api.get('/api/android/message/status')
    async def delivery_status(deviceId: str, clientMessageId: str):
        try:
            if str(uuid.UUID(deviceId)) != deviceId or str(uuid.UUID(clientMessageId)) != clientMessageId:
                raise ValueError()
        except ValueError:
            raise HTTPException(400, 'Canonical UUID required') from None
        key = hashlib.sha256((deviceId + ':' + clientMessageId).encode()).hexdigest()
        path = inbox.directory / (key + '.json')
        async with inbox.lock:
            if not path.exists():
                raise HTTPException(404, 'Message not found')
            record = json.loads(path.read_text(encoding='utf-8'))
        return {'success': True, 'delivery': record['state']}

    return inbox
