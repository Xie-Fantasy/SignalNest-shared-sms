#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QQ 转发失败时的 Spug 短信/邮件兜底转发。

触发条件：OneBot send_group_msg 失败（QQ bot 掉线/风控）时调用。
职责：
1. 从原短信文本提取验证码（4-6 位数字/字母），通过模板 2 发给模板配置的接收人。
2. 通过模板 3 给模板配置的告警接收人发送「掉线提醒」（短信编码 + 邮箱完整内容）。

注意：
- Spug 短信通道只有官方验证码模板，正文固定「您的验证码是${code}…」，
  code 限 4-6 位数字/字母。因此验证码转发只能承载验证码本身，发件人等
  完整上下文只能走邮箱通道。
- 所有 Spug 请求零重试、零代理、短超时，失败只记日志，绝不影响主流程。
- 事件日志（Web 检测系统）只记录是否成功与发送对象类别，绝不写入验证码、
  短信正文或模板 URL。
"""

import json
import logging
import os
import re
import urllib.request

from app import event_log

logger = logging.getLogger('sms_gateway')

# 模板编码从 .env 读取（模板 2=验证码转发，模板 3=掉线提醒）
SPUG_CODE_URL = os.environ.get('SPUG_CODE_URL', '').strip()       # /send/<code> 完整 URL
SPUG_NOTIFY_URL = os.environ.get('SPUG_NOTIFY_URL', '').strip()   # /send/<code> 完整 URL

# 提取验证码：关键词附近 4-6 位数字/字母（字母不限大小写）
_CODE_KEYWORDS = (
    '验证码', '校验码', '动态码', '激活码', '登录码', '短信码',
    'verification', 'verify', 'code', 'otp', '验证', '确认码',
)
_CODE_RE = re.compile(r'([A-Za-z0-9]{4,6})')
# 关键词锚定的整体匹配，例如「验证码是123456」「验证码：Ab3D」
_ANCHORED_RE = re.compile(
    r'(?:验证码|校验码|动态码|激活码|登录码|确认码|verification\s*code|verify\s*code|otp)'
    r'[^\w]*[:：是为]\s*([A-Za-z0-9]{4,6})',
    re.IGNORECASE,
)
# 反序格式：「123456（验证码）」「123456 为您本次登录验证码」—— 数字在前，关键词在后
_REVERSED_RE = re.compile(
    r'(?<![A-Za-z0-9])([A-Za-z0-9]{4,6})'
    r'[^\w]{0,4}'
    r'(?:验证码|校验码|动态码|激活码|登录码|确认码|verification\s*code|verify\s*code|otp)',
    re.IGNORECASE,
)
# 纯数字验证码（更保守，避免误把长号码当验证码）
_PURE_DIGIT_4_6 = re.compile(r'(?<!\d)(\d{4,6})(?!\d)')


def _http_post(url, payload):
    """发送 Spug POST 请求，零重试，失败抛异常。"""
    if not url:
        raise RuntimeError('Spug URL not configured')
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(
        url, body, {'Content-Type': 'application/json; charset=utf-8'}, method='POST')
    with opener.open(request, timeout=10) as response:
        raw = response.read(4096)
    result = json.loads(raw.decode('utf-8', 'replace'))
    if result.get('code') != 200:
        raise RuntimeError(f"Spug rejected: {result.get('msg')}")
    return result


def extract_code(message: str):
    """从短信文本提取 4-6 位验证码，失败返回 None。"""
    if not message:
        return None
    # 1) 关键词锚定：验证码是/为/：后面紧跟的 4-6 位
    m = _ANCHORED_RE.search(message)
    if m:
        return m.group(1)
    # 2) 反序：数字在前，验证码关键词在后
    m = _REVERSED_RE.search(message)
    if m:
        return m.group(1)
    # 3) 纯数字 4-6 位（最常见）
    m = _PURE_DIGIT_4_6.search(message)
    if m:
        return m.group(1)
    # 4) 兜底：任意 4-6 位字母数字，但只在文本较短时（避免误提取长串）
    if len(message) <= 80:
        m = _CODE_RE.search(message)
        if m:
            return m.group(1)
    return None


def forward_code(payload, trace=None):
    """把验证码转发给共享号 B/A（模板 2）。返回是否成功。"""
    code = extract_code(getattr(payload, 'message', ''))
    has_code = code is not None
    if code is None:
        logger.info('[SPUG CODE] no code extracted; fallback to offline marker')
        code = 'NOCODE'
    try:
        result = _http_post(SPUG_CODE_URL, {'code': code})
        # Never write the verification code itself to logs or events.
        logger.info('[SPUG CODE SENT] has_code=%s request_id=%s',
                    int(has_code), result.get('request_id'))
        event_log.emit('SPUG_CODE_SENT', trace=trace, source='iphone',
                       channel='spug_sms', result='ok',
                       target='共享号A与共享号B 短信',
                       note='code_extracted' if has_code else 'no_code')
        return True
    except Exception as exc:
        logger.error('[SPUG CODE FAILED] %s: %s', type(exc).__name__, exc)
        event_log.emit('SPUG_CODE_FAILED', trace=trace, source='iphone',
                       channel='spug_sms', result='failed',
                       target='共享号A与共享号B 短信', note=type(exc).__name__)
        return False


def notify_offline(payload, trace=None):
    """掉线提醒给共享号 C + 主邮箱（模板 3）。返回是否成功。"""
    # 短信侧只发固定编码（QBOT2），邮箱侧承载完整内容
    message = getattr(payload, 'message', '')
    sender = getattr(payload, 'sender', '')
    received_at = getattr(payload, 'receivedAt', '')
    # 截断正文，避免超长触发过滤或撑爆邮箱
    body_snippet = (message or '')[:200]
    try:
        result = _http_post(SPUG_NOTIFY_URL, {
            'code': 'QBOT2',
            'key1': '已离线',
            'key2': f'发件人:{sender} 内容:{body_snippet}',
            'key3': received_at or '',
        })
        logger.info('[SPUG NOTIFY SENT] request_id=%s', result.get('request_id'))
        event_log.emit('SPUG_NOTIFY_SENT', trace=trace, source='iphone',
                       channel='spug_notify', result='ok',
                       target='共享号C 短信与邮箱', note='offline_notice')
        return True
    except Exception as exc:
        logger.error('[SPUG NOTIFY FAILED] %s: %s', type(exc).__name__, exc)
        event_log.emit('SPUG_NOTIFY_FAILED', trace=trace, source='iphone',
                       channel='spug_notify', result='failed',
                       target='共享号C 短信与邮箱', note=type(exc).__name__)
        return False


def fallback(payload, trace=None):
    """QQ 转发失败时的完整兜底：验证码转发 + 掉线提醒。"""
    ok_code = forward_code(payload, trace)
    ok_notify = notify_offline(payload, trace)
    return ok_code or ok_notify
