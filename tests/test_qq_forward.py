import asyncio
import importlib.util
import io
import json
import os
import secrets
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault('TARGET_RECIPIENT', '13800138000')
os.environ['SMS_EVENT_LOG_ENABLED'] = 'false'
os.environ.pop('SPUG_CODE_URL', None)
os.environ.pop('SPUG_NOTIFY_URL', None)
os.environ.update(SMS_PUSH_TOKEN=secrets.token_hex(32), QQ_FORWARD_ENABLED='true',
    NAPCAT_ACCESS_TOKEN=secrets.token_hex(32), NAPCAT_API_URL='http://127.0.0.1:13000',
    QQ_TARGET_TYPE='group', QQ_TARGET_ID='1234567891', BOT_QQ_ID='1234567890', LOG_MESSAGE_BODY='false')
spec = importlib.util.spec_from_file_location('gateway', sys.argv.pop(1))
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


def response(data, status='ok', retcode=0):
    return io.BytesIO(json.dumps(dict(status=status, retcode=retcode, data=data)).encode())


class ForwardTests(unittest.TestCase):
    def setUp(self):
        self.payload = gateway.PushMessage(sender='Test', message='中文 [CQ:at,qq=all]',
            receivedAt='2026-09-15', recipient='13800138000')
        self.opener = MagicMock()

    def run_push(self):
        with patch.object(gateway.urllib.request, 'build_opener', return_value=self.opener):
            return asyncio.run(gateway.push(self.payload))

    def test_success_and_plain_text(self):
        self.opener.open.side_effect = [response({'user_id': 1234567890}), response({'message_id': 42})]
        self.assertEqual(self.run_push(), {'success': True, 'forwarded': True, 'channel': 'qq_bot'})
        req = self.opener.open.call_args_list[-1].args[0]
        body = json.loads(req.data)
        self.assertEqual(body['group_id'], 1234567891)
        self.assertEqual(body['message'][0]['type'], 'text')
        self.assertIn(self.payload.message, body['message'][0]['data']['text'])

    def test_wrong_account_never_sends(self):
        self.opener.open.side_effect = [response({'user_id': 123})]
        self.assertEqual(self.run_push().status_code, 502)
        self.assertEqual(self.opener.open.call_count, 1)

    def test_rejected_send_returns_failure(self):
        self.opener.open.side_effect = [response({'user_id': 1234567890}), response(None, 'failed', 1200)]
        self.assertEqual(self.run_push().status_code, 502)

    def test_timeout_does_not_retry(self):
        self.opener.open.side_effect = [response({'user_id': 1234567890}), TimeoutError('sensitive upstream content')]
        result = self.run_push()
        self.assertEqual(result.status_code, 502)
        self.assertNotIn(b'sensitive', result.body)
        self.assertEqual(self.opener.open.call_count, 2)

    def test_disabled_does_not_send(self):
        with patch.object(gateway, 'QQ_ENABLED', False):
            self.assertEqual(self.run_push(), {
                'success': True, 'forwarded': False, 'reason': 'qq_forward_disabled'
            })
        self.opener.open.assert_not_called()


unittest.main()
