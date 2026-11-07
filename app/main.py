import asyncio
import json
import logging
import os
import re
import secrets
import urllib.request

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app import spug_fallback
from app import forward_route
from app import event_log
from app import runtime_config

TOKEN = os.environ['SMS_PUSH_TOKEN']
if len(TOKEN) < 64:
    raise RuntimeError('SMS_PUSH_TOKEN must contain at least 64 characters')
LOG_BODY = os.environ.get('LOG_MESSAGE_BODY', 'false').lower() == 'true'
MAX_BODY = 65536
TARGET_RECIPIENT = os.environ['TARGET_RECIPIENT']
MAINLAND_MOBILE = re.compile(r'^1[3-9]\d{9}$')
QQ_ENABLED = os.environ.get('QQ_FORWARD_ENABLED', 'false').lower() == 'true'
QQ_URL = os.environ.get('NAPCAT_API_URL', 'http://127.0.0.1:13000').rstrip('/')
QQ_TOKEN = os.environ.get('NAPCAT_ACCESS_TOKEN', '')
QQ_GROUP = os.environ.get('QQ_TARGET_ID', '')
BOT_QQ = os.environ.get('BOT_QQ_ID', '')
if QQ_ENABLED and (not QQ_TOKEN or os.environ.get('QQ_TARGET_TYPE') != 'group'
                   or not QQ_GROUP.isdigit() or not BOT_QQ.isdigit()
                   or QQ_URL != 'http://127.0.0.1:13000'):
    raise RuntimeError('Invalid QQ forwarding configuration')
logger = logging.getLogger('sms_gateway')
logging.basicConfig(level=logging.INFO, format='%(message)s')


class PushMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    sender: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1, max_length=10000)
    receivedAt: str = Field(min_length=1, max_length=128)
    recipient: str = Field(default='', max_length=64)

    @field_validator('recipient', mode='before')
    @classmethod
    def null_recipient_is_empty(cls, value):
        # Missing, null, and empty recipients are handled uniformly and fail closed.
        return '' if value is None else value


api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, debug=False)


@api.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Never echo submitted SMS content, tokens, or raw input in errors.
    return JSONResponse(status_code=422, content={'detail': [
        {'loc': list(e['loc']), 'type': e['type'], 'msg': e['msg']}
        for e in exc.errors()
    ]})


@api.get('/health')
async def health():
    return {'status': 'ok'}


def normalize_recipient(value: str):
    compact = re.sub(r'[\s\-()]', '', value.strip())
    if compact.startswith('+86'):
        compact = compact[3:]
    elif compact.startswith('86') and MAINLAND_MOBILE.fullmatch(compact[2:]):
        compact = compact[2:]
    return compact if MAINLAND_MOBILE.fullmatch(compact) else None


def mask_phone(value):
    if not value:
        return '[unrecognized]'
    return value[:3] + '****' + value[-4:]


def mask_sender(value):
    digits = re.sub(r'\D', '', value)
    if len(digits) < 7:
        return '[redacted]'
    return digits[:3] + '****' + digits[-4:]


def forward_to_qq(payload: PushMessage):
    # No proxy, redirects, automatic retries, or CQ-code interpretation.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(action, body):
        request = urllib.request.Request(QQ_URL + '/' + action,
            json.dumps(body, ensure_ascii=False).encode('utf-8'),
            {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + QQ_TOKEN})
        with opener.open(request, timeout=5) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise RuntimeError('Oversized OneBot response')
            result = json.loads(raw)
        if result.get('status') != 'ok' or result.get('retcode') != 0:
            raise RuntimeError('OneBot operation failed')
        return result.get('data')

    identity = call('get_login_info', {})
    if not isinstance(identity, dict) or str(identity.get('user_id')) != BOT_QQ:
        raise RuntimeError('Unexpected bot identity')
    # Resolve the target at send time so the web monitor can change it without
    # touching .env or restarting this service. Falls back to QQ_TARGET_ID.
    target = runtime_config.target_group()
    text = f'【短信通知】\n发件人：{payload.sender}\n接收时间：{payload.receivedAt}\n\n{payload.message}'
    result = call('send_group_msg', {
        'group_id': int(target),
        'message': [{'type': 'text', 'data': {'text': text}}]
    })
    if not isinstance(result, dict) or result.get('message_id') is None:
        raise RuntimeError('Missing message acknowledgement')


@api.post('/api/message/push')
async def push(payload: PushMessage):
    trace = event_log.new_trace()
    normalized_recipient = normalize_recipient(payload.recipient)
    # 2026-11-05 (second clarification): NO masking anywhere. The user asked
    # explicitly why phone numbers were still hidden, so journald now stores the
    # full sender / recipient too. Message bodies, verification codes and
    # tokens are still NEVER written to any log or event store.
    record = {
        'sender': payload.sender,
        'recipient': normalized_recipient or payload.recipient,
        'receivedAt': payload.receivedAt,
        'messageLength': len(payload.message),
    }
    full_sender = record['sender']
    full_recipient = record['recipient']
    group_label = runtime_config.label()
    logger.info('[SMS RECEIVED] %s', json.dumps(record, ensure_ascii=False))
    event_log.emit('RECEIVED', trace=trace, source='iphone', channel='ingress',
                   result='ok', sender=full_sender, recipient=full_recipient,
                   length=record['messageLength'], target='短信网关')
    if normalized_recipient != TARGET_RECIPIENT:
        logger.info('[SMS IGNORED] reason=recipient_not_allowed')
        event_log.emit('IGNORED', trace=trace, source='iphone', channel='ingress',
                       result='ignored', sender=full_sender,
                       recipient=full_recipient, length=record['messageLength'],
                       note='recipient_not_allowed')
        return {'success': True, 'forwarded': False, 'reason': 'recipient_not_allowed'}

    logger.info('[SMS ACCEPTED] recipient=%s', full_recipient)
    event_log.emit('ACCEPTED', trace=trace, source='iphone', channel='ingress',
                   result='ok', sender=full_sender, recipient=full_recipient,
                   length=record['messageLength'], target=group_label)
    if not QQ_ENABLED:
        event_log.emit('SKIPPED', trace=trace, source='iphone', channel='qq',
                       result='ignored', note='qq_forward_disabled',
                       sender=full_sender, recipient=full_recipient)
        return {'success': True, 'forwarded': False, 'reason': 'qq_forward_disabled'}

    # Try configured channels in priority order; stop at the first success.
    # Default route is [qq_bot, sms] which reproduces the old behaviour exactly.
    channels = forward_route.enabled_channels()
    for ch in channels:
        try:
            if ch == 'qq_bot':
                if not QQ_ENABLED:
                    logger.info('[QQ SKIPPED] qq_forward_disabled')
                    event_log.emit('SKIPPED', trace=trace, source='iphone', channel='qq',
                                   result='ignored', note='qq_forward_disabled',
                                   sender=full_sender, recipient=full_recipient)
                    continue
                await asyncio.to_thread(forward_to_qq, payload)
                logger.info('[QQ FORWARDED] group=%s', group_label)
                event_log.emit('QQ_FORWARDED', trace=trace, source='iphone', channel='qq',
                               result='ok', sender=full_sender, recipient=full_recipient,
                               target=group_label)
                return {'success': True, 'forwarded': True, 'channel': 'qq_bot'}
            elif ch == 'sms':
                ok = await asyncio.to_thread(spug_fallback.fallback, payload, trace)
                if ok:
                    logger.info('[SPUG FALLBACK FORWARDED] channel=sms')
                    return {'success': True, 'forwarded': True, 'channel': 'sms'}
                # otherwise fall through to the next channel
        except Exception:
            # Exception strings may include upstream content; never log them.
            logger.error('[%s FORWARD FAILED] trying next channel; no automatic retry',
                         ch.upper())
            event_log.emit('QQ_FORWARD_FAILED', trace=trace, source='iphone', channel=ch,
                           result='failed', sender=full_sender,
                           recipient=full_recipient, target=group_label,
                           note='channel_unavailable')
            continue
    logger.error('[FORWARD FAILED] all channels exhausted: %s', ','.join(channels))
    event_log.emit('FORWARD_EXHAUSTED', trace=trace, source='iphone',
                   channel='none', result='failed', sender=full_sender,
                   recipient=full_recipient, target=group_label,
                   note='all_channels_failed')
    return JSONResponse({'detail': 'All forwarding channels failed'}, status_code=502)


class RequestGuard:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.inner(scope, receive, send)

        async def reject(status, detail, headers=None):
            response = JSONResponse({'detail': detail}, status_code=status, headers=headers)
            await response(scope, receive, send)

        if scope['path'] == '/api/message/push' or scope['path'].startswith('/api/android/'):
            values = [v for k, v in scope['headers'] if k == b'authorization']
            parts = values[0].split() if len(values) == 1 else []
            if (len(parts) != 2 or parts[0].lower() != b'bearer'
                    or not secrets.compare_digest(parts[1], TOKEN.encode('ascii'))):
                return await reject(401, 'Unauthorized', {'WWW-Authenticate': 'Bearer'})

        headers = dict(scope['headers'])
        length = headers.get(b'content-length')
        if length is not None:
            try:
                size = int(length)
            except ValueError:
                return await reject(400, 'Invalid Content-Length')
            if size < 0:
                return await reject(400, 'Invalid Content-Length')
            if size > MAX_BODY:
                return await reject(413, 'Request body too large')

        # Bound streamed/chunked bodies too, before FastAPI parses JSON.
        body = bytearray()
        try:
            async with asyncio.timeout(15):
                while True:
                    event = await receive()
                    if event['type'] == 'http.disconnect':
                        return
                    body.extend(event.get('body', b''))
                    if len(body) > MAX_BODY:
                        return await reject(413, 'Request body too large')
                    if not event.get('more_body', False):
                        break
        except TimeoutError:
            return await reject(408, 'Request timeout')

        consumed = False

        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        await self.inner(scope, bounded_receive, send)


def android_qq_ready():
    # Read-only preflight. Known offline states can safely wait without sending.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        results = []
        for action in ('get_login_info', 'get_status'):
            req = urllib.request.Request(QQ_URL + '/' + action, b'{}',
                {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + QQ_TOKEN})
            with opener.open(req, timeout=5) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    return False
                result = json.loads(raw)
            if result.get('status') != 'ok' or result.get('retcode') != 0:
                return False
            results.append(result.get('data'))
        return (isinstance(results[0], dict) and str(results[0].get('user_id')) == BOT_QQ
                and isinstance(results[1], dict) and results[1].get('online') is True)
    except Exception:
        return False


from app.android_relay import install
android_inbox = install(api, normalize_recipient, TARGET_RECIPIENT,
                        forward_to_qq, PushMessage, QQ_ENABLED, android_qq_ready)
app = RequestGuard(api)
