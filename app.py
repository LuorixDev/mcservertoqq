import logging
import os
from dataclasses import dataclass

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

from config import (
    ADMIN_PASSWORD,
    ADMIN_PASSWORD_HASH,
    ADMIN_USERNAME,
    DATABASE_URL,
    SECRET_KEY,
)
from models import Server, ServerBinding, db
from services.monitor import ServerMonitor
from services.onebot_manager import OneBotManager
from services.state import get_status


@dataclass
class AdminUser(UserMixin):
    id: int
    username: str


ADMIN_USER = AdminUser(id=1, username=ADMIN_USERNAME)

if ADMIN_PASSWORD_HASH:
    _ADMIN_HASH = ADMIN_PASSWORD_HASH
else:
    _ADMIN_HASH = generate_password_hash(ADMIN_PASSWORD)


login_manager = LoginManager()
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    if str(user_id) == "1":
        return ADMIN_USER
    return None


def create_app():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        db.create_all()
        _ensure_server_columns()
        _ensure_binding_columns()
        _seed_bindings()

    onebot_defaults = {}

    onebot = OneBotManager(onebot_defaults)
    monitor = ServerMonitor(app, onebot, onebot_defaults)
    app.extensions["server_monitor"] = monitor

    def _start_background():
        onebot.start()
        monitor.start()

    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _start_background()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if username == ADMIN_USERNAME and check_password_hash(_ADMIN_HASH, password):
                login_user(ADMIN_USER)
                return redirect(url_for("admin"))

            flash("用户名或密码错误", "error")

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("index"))

    @app.route("/admin")
    @login_required
    def admin():
        servers = Server.query.order_by(Server.id.desc()).all()
        return render_template("admin.html", servers=servers)

    @app.route("/admin/add", methods=["POST"])
    @login_required
    def admin_add():
        name = request.form.get("name", "").strip()
        host = request.form.get("host", "").strip()
        port = request.form.get("port", "25565").strip()

        if not name or not host:
            flash("名称和地址不能为空", "error")
            return redirect(url_for("admin"))

        try:
            port_int = int(port)
        except ValueError:
            flash("端口必须是数字", "error")
            return redirect(url_for("admin"))

        server = Server(
            name=name,
            host=host,
            port=port_int,
            enabled=True,
        )
        db.session.add(server)
        db.session.commit()

        flash("服务器已添加", "success")
        return redirect(url_for("admin"))

    @app.route("/admin/delete/<int:server_id>", methods=["POST"])
    @login_required
    def admin_delete(server_id):
        server = Server.query.get_or_404(server_id)
        db.session.delete(server)
        db.session.commit()
        flash("服务器已删除", "success")
        return redirect(url_for("admin"))

    @app.route("/admin/reset_players", methods=["POST"])
    @login_required
    def admin_reset_players():
        server_id = request.form.get("server_id", "").strip()
        monitor = app.extensions.get("server_monitor")
        if not monitor:
            flash("监控未初始化", "error")
            return redirect(url_for("admin"))
        if server_id:
            try:
                sid = int(server_id)
            except ValueError:
                flash("服务器ID无效", "error")
                return redirect(url_for("admin"))
            monitor.reset_players(sid)
        else:
            monitor.reset_players()
        flash("玩家列表已清空，下次轮询将重新推送上下线", "success")
        return redirect(url_for("admin"))

    @app.route("/admin/reset_players/<int:server_id>", methods=["POST"])
    @login_required
    def admin_reset_players_one(server_id):
        monitor = app.extensions.get("server_monitor")
        if not monitor:
            flash("监控未初始化", "error")
            return redirect(url_for("admin"))
        monitor.reset_players(server_id)
        flash("玩家列表已清空，下次轮询将重新推送上下线", "success")
        return redirect(url_for("admin"))

    @app.route("/admin/edit/<int:server_id>", methods=["GET", "POST"])
    @login_required
    def admin_edit(server_id):
        server = Server.query.get_or_404(server_id)
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            host = request.form.get("host", "").strip()
            port = request.form.get("port", "25565").strip()

            if not name or not host:
                flash("名称和地址不能为空", "error")
                return redirect(url_for("admin_edit", server_id=server_id))

            try:
                port_int = int(port)
            except ValueError:
                flash("端口必须是数字", "error")
                return redirect(url_for("admin_edit", server_id=server_id))

            server.name = name
            server.host = host
            server.port = port_int
            db.session.commit()

            flash("服务器已更新", "success")
            return redirect(url_for("admin"))

        return render_template("edit_server.html", server=server)

    @app.route("/admin/bindings/<int:server_id>")
    @login_required
    def admin_bindings(server_id):
        server = Server.query.get_or_404(server_id)
        bindings = ServerBinding.query.filter_by(server_id=server_id).order_by(ServerBinding.id.desc()).all()
        return render_template("bindings.html", server=server, bindings=bindings)

    @app.route("/admin/bindings/<int:server_id>/add", methods=["POST"])
    @login_required
    def admin_binding_add(server_id):
        server = Server.query.get_or_404(server_id)
        name = request.form.get("name", "").strip() or "默认"
        onebot_ws_url = request.form.get("onebot_ws_url", "").strip()
        onebot_access_token = request.form.get("onebot_access_token", "").strip()
        onebot_target_type = request.form.get("onebot_target_type", "group").strip()
        onebot_target_id = request.form.get("onebot_target_id", "").strip()
        bluemap_url = request.form.get("bluemap_url", "").strip()
        enable_onebot = bool(request.form.get("enable_onebot"))
        notify_player_changes = bool(request.form.get("notify_player_changes"))
        notify_server_status = bool(request.form.get("notify_server_status"))
        enable_bluemap = bool(request.form.get("enable_bluemap"))
        send_screenshot = bool(request.form.get("send_screenshot"))

        binding = ServerBinding(
            server_id=server.id,
            name=name,
            onebot_ws_url=onebot_ws_url,
            onebot_access_token=onebot_access_token,
            onebot_target_type=onebot_target_type or "group",
            onebot_target_id=onebot_target_id,
            enable_onebot=enable_onebot,
            notify_player_changes=notify_player_changes,
            notify_server_status=notify_server_status,
            bluemap_url=bluemap_url,
            enable_bluemap=enable_bluemap,
            send_screenshot=send_screenshot,
        )
        db.session.add(binding)
        db.session.commit()
        flash("绑定已添加", "success")
        return redirect(url_for("admin_bindings", server_id=server.id))

    @app.route("/admin/bindings/edit/<int:binding_id>", methods=["GET", "POST"])
    @login_required
    def admin_binding_edit(binding_id):
        binding = ServerBinding.query.get_or_404(binding_id)
        if request.method == "POST":
            name = request.form.get("name", "").strip() or "默认"
            onebot_ws_url = request.form.get("onebot_ws_url", "").strip()
            onebot_access_token = request.form.get("onebot_access_token", "").strip()
            onebot_target_type = request.form.get("onebot_target_type", "group").strip()
            onebot_target_id = request.form.get("onebot_target_id", "").strip()
            bluemap_url = request.form.get("bluemap_url", "").strip()
            enable_onebot = bool(request.form.get("enable_onebot"))
            notify_player_changes = bool(request.form.get("notify_player_changes"))
            notify_server_status = bool(request.form.get("notify_server_status"))
            enable_bluemap = bool(request.form.get("enable_bluemap"))
            send_screenshot = bool(request.form.get("send_screenshot"))

            binding.name = name
            binding.onebot_ws_url = onebot_ws_url
            binding.onebot_access_token = onebot_access_token
            binding.onebot_target_type = onebot_target_type or "group"
            binding.onebot_target_id = onebot_target_id
            binding.bluemap_url = bluemap_url
            binding.enable_onebot = enable_onebot
            binding.notify_player_changes = notify_player_changes
            binding.notify_server_status = notify_server_status
            binding.enable_bluemap = enable_bluemap
            binding.send_screenshot = send_screenshot
            db.session.commit()

            flash("绑定已更新", "success")
            return redirect(url_for("admin_bindings", server_id=binding.server_id))

        return render_template("edit_binding.html", binding=binding)

    @app.route("/admin/bindings/delete/<int:binding_id>", methods=["POST"])
    @login_required
    def admin_binding_delete(binding_id):
        binding = ServerBinding.query.get_or_404(binding_id)
        server_id = binding.server_id
        db.session.delete(binding)
        db.session.commit()
        flash("绑定已删除", "success")
        return redirect(url_for("admin_bindings", server_id=server_id))

    @app.route("/admin/message", methods=["GET", "POST"])
    @login_required
    def admin_message():
        bindings = (
            ServerBinding.query.join(Server)
            .order_by(Server.id.desc(), ServerBinding.id.desc())
            .all()
        )
        result = None
        error = None
        selected_id = None
        message = ""

        if request.method == "POST":
            selected_id = request.form.get("binding_id", "").strip()
            message = request.form.get("message", "").strip()

            if not selected_id:
                error = "请选择发送通道"
            elif not message:
                error = "消息内容不能为空"
            else:
                binding = ServerBinding.query.get_or_404(int(selected_id))
                if not binding.enable_onebot:
                    error = "该绑定未启用 OneBot 通知"
                    return render_template(
                        "message.html",
                        bindings=bindings,
                        result=result,
                        error=error,
                        selected_id=selected_id,
                        message=message,
                    )
                settings = {
                    "onebot_ws_url": binding.onebot_ws_url,
                    "onebot_access_token": binding.onebot_access_token,
                    "onebot_target_type": binding.onebot_target_type,
                    "onebot_target_id": binding.onebot_target_id,
                }

                result = onebot.send_text_with_result(settings, message, timeout=6)
                if result.get("ok"):
                    response = result.get("response") or {}
                    status = response.get("status")
                    retcode = response.get("retcode", 0)
                    if status and status != "ok":
                        error = response.get("message") or response.get("wording") or "发送失败"
                    elif retcode not in (0, "0"):
                        error = response.get("message") or response.get("wording") or "发送失败"
                else:
                    error = result.get("error") or "发送失败"

        return render_template(
            "message.html",
            bindings=bindings,
            result=result,
            error=error,
            selected_id=selected_id,
            message=message,
        )

    @app.route("/api/servers")
    def api_servers():
        servers = Server.query.order_by(Server.id.desc()).all()
        payload = []
        for s in servers:
            status = get_status(s.id) or {}
            payload.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "address": s.address(),
                    "online": status.get("online", False),
                    "players_online": status.get("players_online", 0),
                    "players_max": status.get("players_max", 0),
                    "latency_ms": status.get("latency_ms"),
                    "players": status.get("players", []),
                    "players_display": status.get("players_display", []),
                    "players_known": status.get("players_known", False),
                    "checked_at": status.get("checked_at"),
                }
            )
        return jsonify(payload)

    return app


def _ensure_server_columns():
    expected = {
        "onebot_ws_url": "TEXT",
        "onebot_access_token": "TEXT",
        "onebot_target_type": "TEXT",
        "onebot_target_id": "TEXT",
        "enable_onebot": "INTEGER",
        "notify_player_changes": "INTEGER",
        "notify_server_status": "INTEGER",
        "bluemap_url": "TEXT",
        "enable_bluemap": "INTEGER",
        "send_screenshot": "INTEGER",
    }
    result = db.session.execute(text("PRAGMA table_info(servers)"))
    existing = {row[1] for row in result.fetchall()}
    for name, coltype in expected.items():
        if name not in existing:
            db.session.execute(text(f"ALTER TABLE servers ADD COLUMN {name} {coltype}"))
    db.session.execute(text("UPDATE servers SET enable_onebot=1 WHERE enable_onebot IS NULL"))
    db.session.execute(
        text("UPDATE servers SET notify_player_changes=1 WHERE notify_player_changes IS NULL")
    )
    db.session.execute(
        text("UPDATE servers SET notify_server_status=1 WHERE notify_server_status IS NULL")
    )
    db.session.execute(text("UPDATE servers SET send_screenshot=1 WHERE send_screenshot IS NULL"))
    db.session.execute(
        text(
            "UPDATE servers SET enable_bluemap=1 "
            "WHERE enable_bluemap IS NULL AND bluemap_url IS NOT NULL AND bluemap_url != ''"
        )
    )
    db.session.commit()


def _ensure_binding_columns():
    result = db.session.execute(text("PRAGMA table_info(server_bindings)"))
    existing = {row[1] for row in result.fetchall()}
    if not existing:
        db.create_all()
        result = db.session.execute(text("PRAGMA table_info(server_bindings)"))
        existing = {row[1] for row in result.fetchall()}
    expected = {
        "server_id": "INTEGER",
        "name": "TEXT",
        "onebot_ws_url": "TEXT",
        "onebot_access_token": "TEXT",
        "onebot_target_type": "TEXT",
        "onebot_target_id": "TEXT",
        "enable_onebot": "INTEGER",
        "notify_player_changes": "INTEGER",
        "notify_server_status": "INTEGER",
        "bluemap_url": "TEXT",
        "enable_bluemap": "INTEGER",
        "send_screenshot": "INTEGER",
    }
    for name, coltype in expected.items():
        if name not in existing:
            db.session.execute(text(f"ALTER TABLE server_bindings ADD COLUMN {name} {coltype}"))
    db.session.execute(
        text("UPDATE server_bindings SET enable_onebot=1 WHERE enable_onebot IS NULL")
    )
    db.session.execute(
        text(
            "UPDATE server_bindings SET notify_player_changes=1 "
            "WHERE notify_player_changes IS NULL"
        )
    )
    db.session.execute(
        text(
            "UPDATE server_bindings SET notify_server_status=1 "
            "WHERE notify_server_status IS NULL"
        )
    )
    db.session.execute(
        text("UPDATE server_bindings SET send_screenshot=1 WHERE send_screenshot IS NULL")
    )
    db.session.execute(
        text(
            "UPDATE server_bindings SET enable_bluemap=1 "
            "WHERE enable_bluemap IS NULL AND bluemap_url IS NOT NULL AND bluemap_url != ''"
        )
    )
    db.session.commit()


def _seed_bindings():
    servers = Server.query.all()
    for server in servers:
        if server.bindings:
            continue
        binding = ServerBinding(
            server_id=server.id,
            name="默认",
            onebot_ws_url=server.onebot_ws_url,
            onebot_access_token=server.onebot_access_token,
            onebot_target_type=server.onebot_target_type or "group",
            onebot_target_id=server.onebot_target_id,
            enable_onebot=server.enable_onebot if server.enable_onebot is not None else True,
            notify_player_changes=(
                server.notify_player_changes if server.notify_player_changes is not None else True
            ),
            notify_server_status=(
                server.notify_server_status if server.notify_server_status is not None else True
            ),
            bluemap_url=server.bluemap_url,
            enable_bluemap=(
                server.enable_bluemap
                if server.enable_bluemap is not None
                else bool(server.bluemap_url)
            ),
            send_screenshot=server.send_screenshot if server.send_screenshot is not None else True,
        )
        db.session.add(binding)
    db.session.commit()


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
