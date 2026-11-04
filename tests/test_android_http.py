"""ASGI tests with random credentials and mocked QQ; no network traffic."""
import asyncio
import json
import os
import secrets
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

os.environ['SMS_PUSH_TOKEN'] = secrets.token_hex(32)
os.environ['QQ_FORWARD_ENABLED'] = 'false'
from app import main


class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        main.android_inbox.directory = main.android_inbox.directory.__class__(self.temp.name)
        main.android_inbox.forward = Mock()

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def request(self, path, body=None, token=True):
        path, _, query = path.partition('?')
        raw = b'' if body is None else json.dumps(body).encode()
        headers = [(b'content-type', b'application/json')]
        if token:
            headers.append((b'authorization', ('Bearer ' + main.TOKEN).encode()))
        scope = dict(type='http', asgi={'version': '3.0'}, http_version='1.1', method='GET' if body is None else 'POST',
                     scheme='https', path=path, raw_path=path.encode(), query_string=query.encode(),
                     root_path='', headers=headers, server=('test', 443), client=('test', 1))
        consumed = False
        async def receive():
            nonlocal consumed
            if consumed:
                return {'type': 'http.disconnect'}
            consumed = True
            return {'type': 'http.request', 'body': raw, 'more_body': False}
        output = []
        async def send(event):
            output.append(event)
        await main.app(scope, receive, send)
        status = next(e['status'] for e in output if e['type'] == 'http.response.start')
        data = b''.join(e.get('body', b'') for e in output if e['type'] == 'http.response.body')
        return status, json.loads(data)

    def payload(self):
        return dict(deviceId=str(uuid.uuid4()), clientMessageId=str(uuid.uuid4()), sender='synthetic',
                    message='synthetic', recipient=main.TARGET_RECIPIENT, simVerified=True,
                    receivedAt=datetime.now(timezone.utc).isoformat())

    async def test_android_routes_require_auth(self):
        self.assertEqual((await self.request('/api/android/status', token=False))[0], 401)
        self.assertEqual((await self.request('/api/android/message/push', self.payload(), False))[0], 401)
        self.assertEqual((await self.request('/api/android/status'))[1]['protocol'], 2)

    async def test_v2_repeated_request_is_durable_and_idempotent(self):
        payload = self.payload()
        first = await self.request('/api/android/message/push', payload)
        second = await self.request('/api/android/message/push', payload)
        self.assertEqual(first[0], 200)
        self.assertTrue(first[1]['accepted'])
        self.assertTrue(second[1]['deduplicated'])
        self.assertEqual(len(list(main.android_inbox.directory.glob('*.json'))), 1)
        main.android_inbox.forward.assert_not_called()
        status, response = await self.request('/api/android/message/status?deviceId=' + payload['deviceId']
            + '&clientMessageId=' + payload['clientMessageId'])
        self.assertEqual(status, 200)
        self.assertEqual(response['delivery'], 'pending')
        self.assertNotIn('synthetic', json.dumps(response))

    async def test_invalid_payload_does_not_echo_sensitive_input(self):
        payload = self.payload()
        payload['unknown'] = 'DO_NOT_ECHO'
        status, response = await self.request('/api/android/message/push', payload)
        self.assertEqual(status, 422)
        self.assertNotIn('DO_NOT_ECHO', json.dumps(response))
        payload.pop('unknown')
        payload['receivedAt'] = 'DO_NOT_ECHO'
        status, response = await self.request('/api/android/message/push', payload)
        self.assertEqual(status, 422)
        self.assertNotIn('DO_NOT_ECHO', json.dumps(response))

    async def test_old_iphone_contract_still_accepts_four_fields(self):
        status, response = await self.request('/api/message/push',
            dict(sender='synthetic', message='synthetic', recipient='13800138000', receivedAt='synthetic-time'))
        self.assertEqual(status, 200)
        self.assertFalse(response['forwarded'])

    async def test_unverified_sim_never_writes_inbox(self):
        payload = self.payload()
        payload['simVerified'] = False
        self.assertEqual((await self.request('/api/android/message/push', payload))[0], 400)
        self.assertEqual(list(main.android_inbox.directory.glob('*.json')), [])


unittest.main()
