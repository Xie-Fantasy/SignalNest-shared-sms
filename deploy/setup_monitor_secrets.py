#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run ONCE as root on the server after deploying the monitor extension.

/opt/napcat/config/webui.json is 600 and owned by another uid, so the monitor
service (sms-gateway) cannot read it. This script derives the WebUI login hash
and copies the OneBot token into /etc/sms-monitor/napcat.json (600, owned by
sms-gateway). No QQ password is involved and no value is ever printed.
"""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

WEBUI_CONFIG = Path('/opt/napcat/config/webui.json')
GATEWAY_ENV = Path('/opt/sms-gateway/.env')
OUT = Path('/etc/sms-monitor/napcat.json')


def main():
    webui = json.loads(WEBUI_CONFIG.read_text(encoding='utf-8'))
    webui_hash = hashlib.sha256(
        (str(webui['token']) + '.napcat').encode('utf-8')).hexdigest()
    env = {}
    for line in GATEWAY_ENV.read_text(encoding='utf-8').splitlines():
        key, sep, value = line.strip().partition('=')
        if sep and not key.startswith('#'):
            env[key] = value.strip().strip('"\'')
    if not env.get('NAPCAT_ACCESS_TOKEN'):
        raise SystemExit('OneBot token missing in gateway env')
    payload = {
        'webuiHash': webui_hash,
        'onebotToken': env['NAPCAT_ACCESS_TOKEN'],
        'webuiUrl': 'http://127.0.0.1:6099',
        'onebotUrl': env.get('NAPCAT_API_URL', 'http://127.0.0.1:13000'),
        'generatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    OUT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.chown(OUT.parent, 'sms-gateway', 'sms-gateway')
    os.chmod(OUT.parent, 0o700)
    fd = os.open(OUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    shutil.chown(OUT, 'sms-gateway', 'sms-gateway')
    os.chmod(OUT, 0o600)
    print('Monitor NapCat credentials written (values not displayed).')
    print('File:', OUT, 'mode 600 owner sms-gateway')


if __name__ == '__main__':
    main()
