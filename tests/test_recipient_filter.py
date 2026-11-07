import asyncio
import importlib.util
import os
import secrets
import sys
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault('TARGET_RECIPIENT', '13800138000')
os.environ['SMS_EVENT_LOG_ENABLED'] = 'false'
os.environ.pop('SPUG_CODE_URL', None)
os.environ.pop('SPUG_NOTIFY_URL', None)
os.environ.update(SMS_PUSH_TOKEN=secrets.token_hex(32), QQ_FORWARD_ENABLED='true',
    NAPCAT_ACCESS_TOKEN=secrets.token_hex(32), NAPCAT_API_URL='http://127.0.0.1:13000',
    QQ_TARGET_TYPE='group', QQ_TARGET_ID='1234567891', BOT_QQ_ID='1234567890',
    LOG_MESSAGE_BODY='false')
spec = importlib.util.spec_from_file_location('gateway_recipient', sys.argv.pop(1))
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class RecipientFilterTests(unittest.TestCase):
    allowed = ["13800138000", "+8613800138000", "8613800138000", "+86 138 0013 8000", "138-0013-8000"]
    denied = ["13900139000", "+8613900139000", "", None, "abc", "138001380000"]

    def payload(self, recipient_marker='missing'):
        data = {'sender': '1061234567', 'message': 'test code', 'receivedAt': '2026-09-17'}
        if recipient_marker != 'missing':
            data['recipient'] = recipient_marker
        return gateway.PushMessage(**data)

    def test_allowed_formats_normalize_and_forward(self):
        for recipient in self.allowed:
            with self.subTest(recipient=recipient):
                self.assertEqual(gateway.normalize_recipient(recipient), '13800138000')
                with patch.object(gateway.asyncio, 'to_thread',
                                  new=AsyncMock(return_value=None)) as mocked:
                    result = asyncio.run(gateway.push(self.payload(recipient)))
                self.assertEqual(result, {'success': True, 'forwarded': True, 'channel': 'qq_bot'})
                mocked.assert_awaited_once()

    def test_denied_formats_never_call_qq(self):
        for recipient in self.denied:
            with self.subTest(recipient=recipient):
                with patch.object(gateway.asyncio, 'to_thread',
                                  new=AsyncMock(return_value=None)) as mocked:
                    result = asyncio.run(gateway.push(self.payload(recipient)))
                self.assertEqual(result, {
                    'success': True,
                    'forwarded': False,
                    'reason': 'recipient_not_allowed',
                })
                mocked.assert_not_awaited()

    def test_missing_recipient_never_calls_qq(self):
        with patch.object(gateway.asyncio, 'to_thread',
                          new=AsyncMock(return_value=None)) as mocked:
            result = asyncio.run(gateway.push(self.payload()))
        self.assertEqual(result, {
            'success': True,
            'forwarded': False,
            'reason': 'recipient_not_allowed',
        })
        mocked.assert_not_awaited()


unittest.main()
