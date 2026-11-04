import asyncio
import importlib.util
import json
import os
import secrets
import sys
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.android_relay import AndroidInbox, AndroidMessage


class AndroidInboxTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.forward = Mock()
        self.inbox = AndroidInbox(self.temp.name, lambda x: x, 'allowed', self.forward,
                                  lambda **kw: kw, True)

    async def asyncTearDown(self):
        await self.inbox.stop()
        self.temp.cleanup()

    def payload(self, **changes):
        values = dict(deviceId=str(uuid.uuid4()), clientMessageId=str(uuid.uuid4()),
                      sender='test-sender', recipient='allowed', message='synthetic-content',
                      receivedAt=datetime.now(timezone.utc).isoformat(), simVerified=True)
        values.update(changes)
        return AndroidMessage(**values)

    async def test_duplicate_and_concurrent_requests_send_once(self):
        payload = self.payload()
        results = await asyncio.gather(*(self.inbox.accept(payload) for _ in range(5)))
        self.assertEqual(sum(bool(r.get('deduplicated')) for r in results), 4)
        await self.inbox.cycle()
        await self.inbox.cycle()
        self.forward.assert_called_once()
        record = json.loads(next(self.inbox.directory.glob('*.json')).read_text())
        self.assertEqual(record['state'], 'delivered')
        self.assertNotIn('payload', record)
        self.assertNotIn('synthetic-content', json.dumps(record))

    async def test_changed_content_with_same_id_is_rejected(self):
        payload = self.payload()
        await self.inbox.accept(payload)
        with self.assertRaises(HTTPException) as exc:
            await self.inbox.accept(payload.model_copy(update={'message': 'changed'}))
        self.assertEqual(exc.exception.status_code, 409)

    async def test_private_unverified_and_expired_never_persist(self):
        for changes in ({'recipient': 'private'},
                        {'receivedAt': datetime.fromtimestamp(time.time() - 601, timezone.utc).isoformat()}):
            self.assertFalse((await self.inbox.accept(self.payload(**changes)))['accepted'])
        with self.assertRaises(HTTPException):
            await self.inbox.accept(self.payload(simVerified=False))
        self.assertFalse(list(self.inbox.directory.glob('*.json')))
        self.forward.assert_not_called()

    async def test_ambiguous_onebot_error_never_retries(self):
        payload = self.payload()
        self.forward.side_effect = TimeoutError('synthetic secret')
        await self.inbox.accept(payload)
        await self.inbox.cycle()
        await self.inbox.accept(payload)
        await self.inbox.cycle()
        self.forward.assert_called_once()
        record = json.loads(next(self.inbox.directory.glob('*.json')).read_text())
        self.assertEqual(record['state'], 'delivery_unknown')
        self.assertNotIn('payload', record)

    async def test_restart_during_send_never_replays(self):
        await self.inbox.accept(self.payload())
        path = next(self.inbox.directory.glob('*.json'))
        record = json.loads(path.read_text())
        record['state'] = 'sending'
        self.inbox.write(path, record)
        await self.inbox.start()
        await self.inbox.stop()
        await self.inbox.cycle()
        self.forward.assert_not_called()
        self.assertEqual(json.loads(path.read_text())['state'], 'delivery_unknown')

    async def test_expiry_erases_payload(self):
        await self.inbox.accept(self.payload())
        path = next(self.inbox.directory.glob('*.json'))
        record = json.loads(path.read_text())
        record['expires'] = time.time() - 1
        self.inbox.write(path, record)
        await self.inbox.cycle()
        self.assertEqual(json.loads(path.read_text())['state'], 'expired')
        self.forward.assert_not_called()

    async def test_future_clock_is_rejected(self):
        with self.assertRaises(HTTPException):
            await self.inbox.accept(self.payload(receivedAt=datetime.fromtimestamp(time.time()+300, timezone.utc).isoformat()))

    async def test_known_offline_waits_without_sending_then_recovers(self):
        self.inbox.can_send = Mock(return_value=False)
        await self.inbox.accept(self.payload())
        await self.inbox.cycle()
        self.forward.assert_not_called()
        self.inbox.can_send.return_value = True
        await self.inbox.cycle()
        self.forward.assert_called_once()


unittest.main()
