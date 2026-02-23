import socket
from typing import Any, Dict, List, Optional

from mcstatus import JavaServer


def _safe_player_list(sample) -> List[str]:
    if not sample:
        return []
    names = []
    for p in sample:
        name = getattr(p, "name", None)
        if name:
            names.append(name)
    return names


def query_java_status(host: str, port: int, use_query_for_players: bool, query_port: int) -> Dict[str, Any]:
    address = f"{host}:{port}"
    server = JavaServer.lookup(address)

    status = server.status()
    players_online = status.players.online
    players_max = status.players.max
    latency_ms = int(status.latency) if status.latency is not None else None
    players_known = status.players.sample is not None
    players: Optional[List[str]] = _safe_player_list(status.players.sample) if players_known else []

    if use_query_for_players:
        try:
            query_server = JavaServer.lookup(f"{host}:{query_port or port}")
            query = query_server.query()
            if query and query.players and query.players.names is not None:
                players = list(query.players.names)
                players_known = True
        except Exception:
            pass

    return {
        "online": True,
        "players_online": players_online,
        "players_max": players_max,
        "latency_ms": latency_ms,
        "players": players,
        "players_known": players_known,
    }


def fetch_status(host: str, port: int, use_query_for_players: bool, query_port: int) -> Dict[str, Any]:
    try:
        return query_java_status(host, port, use_query_for_players, query_port)
    except (socket.timeout, OSError, Exception):
        return {
            "online": False,
            "players_online": 0,
            "players_max": 0,
            "latency_ms": None,
            "players": [],
            "players_known": False,
        }
