from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Server(db.Model):
    __tablename__ = "servers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    host = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, nullable=False, default=25565)
    enabled = db.Column(db.Boolean, default=True)
    onebot_ws_url = db.Column(db.String(255), default="")
    onebot_access_token = db.Column(db.String(255), default="")
    onebot_target_type = db.Column(db.String(20), default="group")
    onebot_target_id = db.Column(db.String(50), default="")
    enable_onebot = db.Column(db.Boolean, default=True)
    notify_player_changes = db.Column(db.Boolean, default=True)
    notify_server_status = db.Column(db.Boolean, default=True)
    bluemap_url = db.Column(db.String(255), default="")
    enable_bluemap = db.Column(db.Boolean, default=False)
    send_screenshot = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def address(self) -> str:
        return f"{self.host}:{self.port}"


class ServerBinding(db.Model):
    __tablename__ = "server_bindings"

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey("servers.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, default="默认")
    onebot_ws_url = db.Column(db.String(255), default="")
    onebot_access_token = db.Column(db.String(255), default="")
    onebot_target_type = db.Column(db.String(20), default="group")
    onebot_target_id = db.Column(db.String(50), default="")
    enable_onebot = db.Column(db.Boolean, default=True)
    notify_player_changes = db.Column(db.Boolean, default=True)
    notify_server_status = db.Column(db.Boolean, default=True)
    bluemap_url = db.Column(db.String(255), default="")
    enable_bluemap = db.Column(db.Boolean, default=False)
    send_screenshot = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    server = db.relationship(
        "Server",
        backref=db.backref("bindings", lazy=True, cascade="all, delete-orphan"),
    )
