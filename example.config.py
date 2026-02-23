import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 基础配置（复制为 config.py 后按需修改）
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'data.db')}"
SECRET_KEY = "change-me"
POLL_INTERVAL = 10

# 管理员账号
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"
ADMIN_PASSWORD_HASH = ""

# MC Query 配置
USE_QUERY_FOR_PLAYERS = False
QUERY_PORT = 0

# BlueMap 调试日志
BLUEMAP_DEBUG = False
