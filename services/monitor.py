import json
import logging
import threading
import time
from datetime import datetime
from urllib.request import urlopen


from services.mc_status import fetch_status
from services.state import update_status
from services.time_utils import format_duration
from models import Server
from config import BLUEMAP_DEBUG, POLL_INTERVAL, USE_QUERY_FOR_PLAYERS, QUERY_PORT


class ServerMonitor:
    def __init__(self, app, onebot, onebot_defaults: dict):
        self.app = app
        self.onebot = onebot
        self._onebot_defaults = onebot_defaults
        self._thread = None
        self._stop = threading.Event()
        self._last_players = {}
        self._last_counts = {}
        self._player_seen_at = {}
        self._last_online = {}
        self._offline_since = {}
        self._last_polled = {}
        self._logger = logging.getLogger("monitor")
        self._bluemap_settings = {}
        self._bluemap_debug = BLUEMAP_DEBUG
        self._bluemap_world_hits = {}

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def reset_players(self, server_id: int | None = None):
        if server_id is None:
            target_ids = list(self._last_players.keys())
        else:
            target_ids = [server_id]
        for sid in target_ids:
            self._last_players[sid] = set()
            self._player_seen_at[sid] = {}
            if self._last_counts.get(sid) is None:
                self._last_counts[sid] = 0

    def _loop(self):
        while not self._stop.is_set():
            self._poll_once()
            time.sleep(POLL_INTERVAL)

    def _poll_once(self):
        now = time.time()
        with self.app.app_context():
            servers = Server.query.filter_by(enabled=True).all()
            servers = [
                {
                    "id": s.id,
                    "name": s.name,
                    "host": s.host,
                    "port": s.port,
                    "bindings": [
                        {
                            "id": b.id,
                            "name": b.name,
                            "onebot_ws_url": b.onebot_ws_url,
                            "onebot_access_token": b.onebot_access_token,
                            "onebot_target_type": b.onebot_target_type,
                            "onebot_target_id": b.onebot_target_id,
                            "enable_onebot": b.enable_onebot,
                            "notify_player_changes": b.notify_player_changes,
                            "notify_server_status": b.notify_server_status,
                            "bluemap_url": b.bluemap_url,
                            "enable_bluemap": b.enable_bluemap,
                            "send_screenshot": b.send_screenshot,
                        }
                        for b in s.bindings
                    ],
                }
                for s in servers
            ]

        for s in servers:
            offline_since = self._offline_since.get(s["id"])
            last_polled = self._last_polled.get(s["id"], 0)
            if offline_since and now - offline_since >= 1800 and now - last_polled < 60:
                continue

            status = fetch_status(s["host"], s["port"], USE_QUERY_FOR_PLAYERS, QUERY_PORT)
            self._last_polled[s["id"]] = now
            status["checked_at"] = datetime.utcnow().isoformat() + "Z"
            current_count = status.get("players_online") or 0
            max_count = status.get("players_max") or 0
            last_count = self._last_counts.get(s["id"])
            last_players = self._last_players.get(s["id"]) or set()
            last_online = self._last_online.get(s["id"])

            if not status["online"]:
                status["players_display"] = []
                if last_online is True:
                    for binding in self._iter_bindings(s):
                        if self._notify_server_status(binding):
                            self.onebot.send_text(
                                self._settings_for_binding(binding),
                                f"[{s['name']}] 服务器离线",
                            )
                if last_online is not False:
                    self._offline_since[s["id"]] = now
                else:
                    self._offline_since.setdefault(s["id"], now)
                update_status(s["id"], status)
                self._last_counts[s["id"]] = None
                self._last_players[s["id"]] = set()
                self._player_seen_at[s["id"]] = {}
                self._last_online[s["id"]] = False
                continue

            if last_online is False:
                for binding in self._iter_bindings(s):
                    if self._notify_server_status(binding):
                        self.onebot.send_text(
                            self._settings_for_binding(binding),
                            f"[{s['name']}] 服务器已上线",
                        )
            self._offline_since.pop(s["id"], None)
            self._last_online[s["id"]] = True

            players_list = status.get("players") or []
            players_list = [name for name in players_list if name and name != "Anonymous Player"]
            current_players = set(players_list)

            seen_at = self._player_seen_at.get(s["id"], {})

            if current_count == 0 and last_players:
                durations = {name: now - seen_at.get(name, now) for name in last_players}
                for binding in self._iter_bindings(s):
                    if self._notify_player_changes(binding):
                        self.onebot.send_player_change(
                            self._settings_for_binding(binding),
                            s["name"],
                            [],
                            sorted(last_players),
                            current_count,
                            max_count,
                            durations,
                        )
                last_players = set()
                seen_at = {}

            if current_players:
                for name in current_players:
                    if name not in seen_at:
                        seen_at[name] = now

                if last_count is not None and current_players != last_players:
                    joined = sorted(current_players - last_players)
                    left = sorted(last_players - current_players)
                    if joined or left:
                        durations = {name: now - seen_at.get(name, now) for name in left}
                        for binding in self._iter_bindings(s):
                            if self._notify_player_changes(binding):
                                self.onebot.send_player_change(
                                    self._settings_for_binding(binding),
                                    s["name"],
                                    joined,
                                    left,
                                    current_count,
                                    max_count,
                                    durations,
                                )
                            if self._send_bluemap_screenshot(binding):
                                for name in joined:
                                    self._schedule_bluemap_lookup(s, binding, name)
                    for name in left:
                        seen_at.pop(name, None)
                last_players = current_players

            display_players = players_list if players_list else sorted(last_players)
            status["players_display"] = [
                f"{name}:{format_duration(now - seen_at.get(name, now))}"
                for name in display_players
            ]

            if last_count is not None and current_count == 0 and last_count > 0:
                for binding in self._iter_bindings(s):
                    if self._notify_player_changes(binding):
                        self.onebot.send_text(
                            self._settings_for_binding(binding),
                            f"[{s['name']}] 呜呜呜，服务器暂时没人在线哦~",
                        )

            self._last_counts[s["id"]] = current_count
            self._last_players[s["id"]] = current_players
            self._player_seen_at[s["id"]] = seen_at
            update_status(s["id"], status)

    def _settings_for_binding(self, binding: dict) -> dict:
        return {
            "onebot_ws_url": binding.get("onebot_ws_url") or self._onebot_defaults.get("ws_url", ""),
            "onebot_access_token": binding.get("onebot_access_token")
            or self._onebot_defaults.get("access_token", ""),
            "onebot_target_type": binding.get("onebot_target_type")
            or self._onebot_defaults.get("target_type", "group"),
            "onebot_target_id": binding.get("onebot_target_id")
            or self._onebot_defaults.get("target_id", ""),
        }

    def _onebot_enabled(self, binding: dict) -> bool:
        value = binding.get("enable_onebot")
        if value is None:
            return True
        return bool(value)

    def _notify_player_changes(self, binding: dict) -> bool:
        if not self._onebot_enabled(binding):
            return False
        value = binding.get("notify_player_changes")
        if value is None:
            return True
        return bool(value)

    def _notify_server_status(self, binding: dict) -> bool:
        if not self._onebot_enabled(binding):
            return False
        value = binding.get("notify_server_status")
        if value is None:
            return True
        return bool(value)

    def _send_bluemap_screenshot(self, binding: dict) -> bool:
        if not self._onebot_enabled(binding):
            return False
        enable_bluemap = binding.get("enable_bluemap")
        if enable_bluemap is None:
            enable_bluemap = bool(binding.get("bluemap_url"))
        send_screenshot = binding.get("send_screenshot")
        if send_screenshot is None:
            send_screenshot = True
        return bool(enable_bluemap) and bool(send_screenshot) and bool(binding.get("bluemap_url"))

    @staticmethod
    def _iter_bindings(server: dict):
        return server.get("bindings") or []

    def _schedule_bluemap_lookup(self, server: dict, binding: dict, player_name: str):
        if not binding.get("bluemap_url"):
            return
        thread = threading.Thread(
            target=self._bluemap_worker,
            args=(server, binding, player_name),
            daemon=True,
        )
        thread.start()

    def _bluemap_worker(self, server: dict, binding: dict, player_name: str):
        base_url = (binding.get("bluemap_url") or "").rstrip("/")
        if not base_url:
            return

        settings = self._get_bluemap_settings(base_url)
        if not settings:
            return

        live_root = settings.get("liveDataRoot") or "maps"
        maps = settings.get("maps") or []

        if self._bluemap_debug or self.app.debug:
            self._logger.info(
                "BlueMap lookup player=%s maps=%d base=%s",
                player_name,
                len(maps),
                base_url,
            )

        world, pos = self._find_player_world(base_url, live_root, maps, player_name)
        if not world or not pos:
            if self._bluemap_debug or self.app.debug:
                self._logger.info("BlueMap player not found: %s", player_name)
            return

        try:
            if self._bluemap_debug or self.app.debug:
                self._logger.info(
                    "BlueMap capture start player=%s world=%s pos=%s",
                    player_name,
                    world,
                    pos,
                )
            image_bytes = self._capture_bluemap_screenshot(
                base_url,
                world,
                live_root,
                player_name,
                pos,
            )
        except Exception as exc:
            if self._bluemap_debug or self.app.debug:
                self._logger.info("BlueMap capture failed: %s", exc)
            return

        if image_bytes:
            self.onebot.send_image_base64(
                self._settings_for_binding(binding),
                image_bytes,
                f"[{server['name']}] {player_name} 位置截图",
            )

    def _find_player_world(self, base_url: str, live_root: str, maps: list, player_name: str):
        maps = self._order_maps(base_url, maps)
        for world in maps:
            data = self._fetch_players(base_url, live_root, world)
            if not data:
                continue
            for player in data.get("players") or []:
                if player.get("name") != player_name:
                    continue
                if player.get("foreign") is True:
                    continue
                pos = player.get("position") or {}
                x = pos.get("x")
                y = pos.get("y")
                z = pos.get("z")
                if x is None or y is None or z is None:
                    continue
                self._note_world_hit(base_url, world)
                return world, {"x": x, "y": y, "z": z}
        return None, None

    def _capture_bluemap_screenshot(
        self,
        base_url: str,
        world: str,
        live_root: str,
        player_name: str,
        pos: dict,
    ) -> bytes | None:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            if self._bluemap_debug or self.app.debug:
                self._logger.info("Playwright not available: %s", exc)
            return None

        target = self._build_bluemap_link(base_url, world, pos["x"], pos["y"], pos["z"])

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            players_path = f"/{live_root}/{world}/live/players.json"

            def _on_response(resp):
                url = resp.url
                if players_path in url:
                    pass

            page.on("response", _on_response)
            if self._bluemap_debug or self.app.debug:
                self._logger.info("BlueMap open URL: %s", target)
            page.goto(target, wait_until="load", timeout=30000)
            hook_status = self._setup_bluemap_hooks(page)
            if self._bluemap_debug or self.app.debug:
                self._logger.info("BlueMap hook status: %s", hook_status)

            start = time.time()
            while time.time() - start < 15:
                latest = self._find_player_position(base_url, live_root, world, player_name)
                if latest:
                    target = self._build_bluemap_link(
                        base_url, world, latest["x"], latest["y"], latest["z"]
                    )
                    if self._bluemap_debug or self.app.debug:
                        self._logger.info("BlueMap update URL: %s", target)
                    page.evaluate("url => { location.hash = url.split('#')[1]; }", target)

                if self._is_bluemap_ready(page):
                    break
                page.wait_for_timeout(500)

            if self._bluemap_debug or self.app.debug:
                self._logger.info("BlueMap screenshot player=%s", player_name)

            image = page.screenshot(type="png")
            browser.close()
            return image

    def _find_player_position(self, base_url: str, live_root: str, world: str, player_name: str):
        data = self._fetch_players(base_url, live_root, world)
        if not data:
            return None
        for player in data.get("players") or []:
            if player.get("name") != player_name:
                continue
            if player.get("foreign") is True:
                return None
            pos = player.get("position") or {}
            x = pos.get("x")
            y = pos.get("y")
            z = pos.get("z")
            if x is None or y is None or z is None:
                return None
            self._note_world_hit(base_url, world)
            return {"x": x, "y": y, "z": z}
        return None

    def _fetch_players(self, base_url: str, live_root: str, world: str):
        players_url = f"{base_url}/{live_root}/{world}/live/players.json"
        if self._bluemap_debug or self.app.debug:
            self._logger.info("BlueMap GET %s", players_url)
        return self._fetch_json(players_url)

    def _note_world_hit(self, base_url: str, world: str):
        key = base_url.rstrip("/")
        worlds = self._bluemap_world_hits.setdefault(key, {})
        worlds[world] = worlds.get(world, 0) + 1

    def _order_maps(self, base_url: str, maps: list):
        key = base_url.rstrip("/")
        counts = self._bluemap_world_hits.get(key, {})
        if not counts:
            return maps
        return sorted(maps, key=lambda w: counts.get(w, 0), reverse=True)

    @staticmethod
    def _is_map_ready(page) -> bool:
        script = """
        () => {
          const canvas = document.querySelector('canvas');
          if (!canvas || canvas.width < 50 || canvas.height < 50) return false;
          try {
            const ctx = canvas.getContext('2d');
            const w = canvas.width;
            const h = canvas.height;
            const sample = ctx.getImageData(0, 0, Math.min(10, w), Math.min(10, h)).data;
            for (let i = 0; i < sample.length; i += 4) {
              if (sample[i + 3] > 0) return true;
            }
          } catch (e) {
            return false;
          }
          return false;
        }
        """
        return page.evaluate(script)

    @staticmethod
    def _is_bluemap_ready(page) -> bool:
        try:
            return page.evaluate(
                "() => !!(window.__bmMapLoaded && window.__bmCameraStable)"
            )
        except Exception:
            return False

    @staticmethod
    def _setup_bluemap_hooks(page) -> str:
        script = """
        () => {
          if (window.__bmHooked) return "hooked";
          const mv =
            window.mapViewer ||
            (window.BlueMapApp && window.BlueMapApp.mapViewer) ||
            (window.app && window.app.mapViewer) ||
            window.bluemapMapViewer;
          if (!mv || !mv.events) return "missing";
          window.__bmHooked = true;
          window.__bmMapLoaded = !!(mv.data && mv.data.mapState === "loaded");
          window.__bmCameraStable = false;
          let stabilizeTimeout;
          const scheduleStable = () => {
            if (stabilizeTimeout) clearTimeout(stabilizeTimeout);
            stabilizeTimeout = setTimeout(() => {
              window.__bmCameraStable = true;
            }, 1500);
          };
          mv.events.addEventListener("bluemapMapChanged", () => {
            if (mv.data && mv.data.mapState === "loaded") {
              window.__bmMapLoaded = true;
            }
            scheduleStable();
          });
          mv.events.addEventListener("bluemapCameraMoved", () => {
            window.__bmCameraStable = false;
            scheduleStable();
          });
          scheduleStable();
          return "hooked";
        }
        """
        try:
            return page.evaluate(script)
        except Exception:
            return "error"

    def _fetch_json(self, url: str):
        try:
            with urlopen(url, timeout=5) as resp:
                if resp.status != 200:
                    if self._bluemap_debug or self.app.debug:
                        self._logger.info("BlueMap http %s status=%s", url, resp.status)
                    return None
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            if self._bluemap_debug or self.app.debug:
                self._logger.info("BlueMap fetch failed %s err=%s", url, exc)
            return None

    def _get_bluemap_settings(self, base_url: str):
        now = time.time()
        cached = self._bluemap_settings.get(base_url)
        if cached and now - cached["ts"] < 300:
            if self._bluemap_debug or self.app.debug:
                self._logger.info("BlueMap settings cache hit: %s", base_url)
            return cached["data"]

        settings_url = f"{base_url}/settings.json"
        if self._bluemap_debug or self.app.debug:
            self._logger.info("BlueMap GET %s", settings_url)
        settings = self._fetch_json(settings_url)
        if settings:
            self._bluemap_settings[base_url] = {"ts": now, "data": settings}
        return settings

    @staticmethod
    def _build_bluemap_link(base_url: str, world: str, x: float, y: float, z: float) -> str:
        ix = int(round(x))
        iy = int(round(y))
        iz = int(round(z))
        return f"{base_url}/#{world}:{ix}:{iy}:{iz}:20:-0.78:0.47:0:0:perspective"
