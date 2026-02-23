# mcservertoqq

Flask + SQLite 的 MC 服务器监控面板，支持 OneBot 11 WS 推送和 BlueMap 截图。

## 功能
- 管理员登录后添加、编辑、删除服务器
- 服务器卡片显示在线人数、延迟、在线状态、玩家列表与在线时长
- 每台服务器可绑定多个通知目标，每个绑定独立配置 OneBot 与 BlueMap
- 玩家上下线提醒，可选服务器在线/离线提醒
- BlueMap 玩家位置截图（可选）
- 管理后台支持发送测试消息、清空玩家列表（触发重新上线提醒）

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

复制配置模板并修改：

```bash
cp example.config.py config.py
```

如需 BlueMap 截图功能，请安装 Playwright 浏览器内核：

```bash
python -m playwright install chromium
```

启动：

```bash
python app.py
```

访问：`http://127.0.0.1:5000`

## 配置说明
配置文件：`config.py`

- `DATABASE_URL`：默认 `sqlite:///data.db`
- `SECRET_KEY`：Flask 密钥
- `POLL_INTERVAL`：轮询间隔（秒），默认 `10`
- `ADMIN_USERNAME` / `ADMIN_PASSWORD`：管理员账号密码
- `ADMIN_PASSWORD_HASH`：可选，使用 `werkzeug.security.generate_password_hash` 生成
- `USE_QUERY_FOR_PLAYERS`：`True/False`，启用 Query 协议获取玩家列表
- `QUERY_PORT`：Query 端口（默认 0 表示跟随服务器端口）
- `BLUEMAP_DEBUG`：输出 BlueMap 调试日志

OneBot 与 BlueMap 的地址、Token、目标群等均在“绑定管理”里为每个绑定单独配置。

## 使用说明
- 登录后台：`/login`
- 在“服务器管理”中添加服务器
- 点击“绑定管理”为服务器添加一个或多个绑定
- 在绑定中配置 OneBot WS 和目标群，按需开启通知与截图
- “消息”页面用于测试发送消息并查看回调结果
- “清空玩家列表”用于触发重新上线提醒

## OneBot 说明
本项目作为 WebSocket 客户端主动连接 OneBot 11 服务端。请确保你的机器人框架已开启 WS 服务并可被访问。

常见示例：
- `ws://<host>:<port>`
- `ws://<host>:<port>?access_token=<token>`

## BlueMap 说明
- 配置 BlueMap 根地址，例如 `http://example.com:8100`
- 程序会读取 `settings.json` 并遍历地图的 `players.json`
- 如果玩家 `foreign=true`，表示不在当前世界，会被忽略
- 开启“发送截图”后，会在玩家上线时抓取 BlueMap 视角截图并发送

## MC Query 说明
部分服务器 Ping 不返回玩家列表，建议启用 Query 协议：
- 服务端开启 `enable-query`
- 设置 `USE_QUERY_FOR_PLAYERS=True` 并配置 `QUERY_PORT`

## 注意事项
- 默认仅适合内网或受控环境，若公开部署请增加安全防护
- 数据库存储在 `data.db`
- 如果升级版本后发现旧配置缺失，首次启动会自动迁移并生成默认绑定
