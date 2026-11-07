#!/usr/bin/env python3
"""Run ONCE as root on the server to create the web monitor login.

    python3 /opt/sms-monitor/init_auth.py

The generated password is printed once to the terminal and is never written to
any file, log, repository or build artifact. Use --password to set your own.
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

AUTH_FILE = Path(os.environ.get('SMS_MONITOR_AUTH_FILE', '/etc/sms-monitor/auth.json'))
ITERATIONS = 200000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', default='admin')
    parser.add_argument('--password', default=None,
                        help='omit to generate a random password shown once')
    args = parser.parse_args()
    password = args.password or secrets.token_urlsafe(18)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    data = {
        'username': args.username.strip(),
        'salt': salt.hex(),
        'password_hash': digest.hex(),
        'session_secret': secrets.token_hex(32),
        'iterations': ITERATIONS,
        'updatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    AUTH_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # The service runs as sms-gateway, so it must be able to traverse this dir.
    shutil.chown(AUTH_FILE.parent, 'sms-gateway', 'sms-gateway')
    os.chmod(AUTH_FILE.parent, 0o700)
    fd = os.open(AUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    shutil.chown(AUTH_FILE, 'sms-gateway', 'sms-gateway')
    os.chmod(AUTH_FILE, 0o600)
    print('Monitor credentials written to ' + str(AUTH_FILE))
    print('USERNAME: ' + data['username'])
    if not args.password:
        print('PASSWORD (shown ONCE, save it now): ' + password)
    else:
        print('PASSWORD: set from --password (not printed)')


if __name__ == '__main__':
    main()
