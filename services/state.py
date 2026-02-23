import threading

_status_cache = {}
_cache_lock = threading.Lock()


def update_status(server_id, status):
    with _cache_lock:
        _status_cache[server_id] = status


def get_status(server_id):
    with _cache_lock:
        return _status_cache.get(server_id)


def all_status():
    with _cache_lock:
        return dict(_status_cache)
