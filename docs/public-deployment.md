# Public deployment notes / 公开版部署补充

The repository includes the gateway (`app/`), Android client, authenticated monitor (`monitor/`) and React frontend (`web/`). Deployment-specific identifiers and credentials are excluded. These sources require your own configuration; they are not a backup of a running installation.

本仓库现包含网关、Android 客户端、监控后端和前端。真实手机号、QQ 标识、主机地址和第三方推送链接均不随源码发布。请自行配置；本目录不包含运行数据或私人凭据。

## Gateway configuration

Follow the existing README gateway setup. `TARGET_RECIPIENT`, `QQ_TARGET_ID`, `BOT_QQ_ID`, `SMS_PUSH_TOKEN` and `NAPCAT_ACCESS_TOKEN` must be supplied privately. Keep one Uvicorn process. Optional `SPUG_CODE_URL` and `SPUG_NOTIFY_URL` are complete template URLs from your own Spug account; treat them as credentials, never commit them. Android does not use this fallback. The legacy iPhone route returns a `channel` field on success; if all configured channels fail it returns 502.

## Monitor setup (Linux, manual)

1. Install gateway source and virtualenv under `/opt/sms-gateway`; use the existing `sms-gateway` service user. Create `/var/lib/sms-gateway` and its `events` and `android-inbox` subdirectories, owned by that user with mode 700.
2. Copy `monitor/*.py` to `/opt/sms-monitor/`. Build the frontend with `cd web && npm ci && npm run build`; copy `web/dist/` contents to `/opt/sms-monitor/www/monitor/`. Build outputs and node_modules are excluded from Git.
3. Run `/opt/sms-gateway/.venv/bin/python /opt/sms-monitor/init_auth.py` as root once. It generates a password for private one-time terminal display; keep it private. Credentials stay in `/etc/sms-monitor/auth.json`, mode 600, directory mode 700 owned by `sms-gateway`.
4. `deploy/setup_monitor_secrets.py` derives monitor credentials from your own NapCat configuration and gateway `.env`. Inspect its paths before running as root. It never prints credential values. Default NapCat config path: `/opt/napcat/config/webui.json`.
5. Install the example systemd units from `deploy/` after reviewing their paths. Include `deploy/nginx-monitor-locations.conf` inside your own HTTPS server block, check `nginx -t`, then reload. The monitor listens only on `127.0.0.1:18101`; cookies require HTTPS.
6. If you want the panel's restart action, separately install and enable `napcat-restart.path` with its service. This optional root action restarts only the container named `napcat`; it may require QQ login again. Scheduled QQ login/recovery is not included or enabled.

运行账号需可读取网关 `.env` 和事件目录；不要公开 OneBot、NapCat WebUI 或监控回环端口。完整手机号、QQ 号和群号会显示在已登录界面及日志中，必须限制访问。手动密码登录、保存账号档案和重启容器均为显式管理操作，需自行评估权限。启用 Spug 会产生真实费用；开发与测试应使用模拟接口。

The monitor supports Chinese/English, light/dark themes, delivery history, channel status and explicit management actions. Some backend dynamic messages may remain Chinese. System endpoint examples use `sms.example.com`; adapt them for your deployment. System certificate metadata is intentionally blank. No historical logs, credentials, certificate private keys, login sessions or APK signing keys are shipped.

## Verification

Run from the repository root with the root on `PYTHONPATH`:

```bash
PYTHONPATH=. python tests/test_qq_forward.py app/main.py
PYTHONPATH=. python tests/test_recipient_filter.py app/main.py
PYTHONPATH=. python tests/test_android_relay.py
PYTHONPATH=. python tests/test_android_http.py
```

These existing scripts use `unittest.main()` and some accept a source-file argument; they are executed directly rather than collected by pytest. Tests use synthetic identifiers and mocked QQ. No real SMS/group delivery or Spug sends are required.
