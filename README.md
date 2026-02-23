# mcservertoqq

Flask + SQLite 的 MC 服务器监控面板，支持 OneBot WS 通知玩家上线/下线。

## 功能
- 管理员登陆后添加/删除服务器
- 列表卡片展示在线人数、延迟、玩家列表、在线状态
- 通过 OneBot WebSocket 发送玩家上下线通知

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如需 BlueMap 截图功能，请安装 Playwright 浏览器内核：

```bash
python -m playwright install chromium
```

配置请直接修改 `config.py`：

```python
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"
SECRET_KEY = "change-me"
```

启动：

```bash
flask --app app run --debug
```

访问：`http://127.0.0.1:5000`

## 配置说明
- `DATABASE_URL`：默认 `sqlite:///data.db`
- `POLL_INTERVAL`：轮询间隔（秒），默认 `30`
- `ADMIN_USERNAME` / `ADMIN_PASSWORD`：管理员账号密码
- `ADMIN_PASSWORD_HASH`：可选，使用 `werkzeug.security.generate_password_hash` 生成
- `USE_QUERY_FOR_PLAYERS`：`true/false`，启用 Query 协议获取玩家列表
- `QUERY_PORT`：Query 端口（默认与服务器端口一致）

OneBot 配置请在“服务器管理”里为每台服务器单独设置（WS/Token/目标类型/目标ID）。

## 注意事项
- 某些服务器不会在 ping 响应中提供完整玩家列表，可能需要启用 `enable-query` 并打开 Query 端口。
- 该示例未启用 CSRF 防护，如需对公网开放建议补充。
