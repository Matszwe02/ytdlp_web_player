import os
import sys
from threading import Lock

_MAX_BYTES = 10 * 1024 * 1024
_lock = Lock()
LOG_PATH = None


class _Tee:
    def __init__(self, original, path):
        self._original = original
        self._path = path

    def write(self, s):
        try:
            self._original.write(s)
        except Exception:
            pass
        if not s or LOG_PATH is None:
            return
        try:
            with _lock:
                try:
                    size = os.path.getsize(self._path)
                except FileNotFoundError:
                    size = 0
                if size > _MAX_BYTES:
                    try:
                        with open(self._path, 'rb') as f:
                            f.seek(-_MAX_BYTES // 2, 2)
                            tail = f.read()
                        with open(self._path, 'wb') as f:
                            f.write(tail)
                    except Exception:
                        pass
                with open(self._path, 'a', encoding='utf-8', errors='replace') as f:
                    f.write(s)
        except Exception:
            pass

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return self._original.isatty()
        except Exception:
            return False

    def fileno(self):
        return self._original.fileno()

    def __getattr__(self, name):
        return getattr(self._original, name)


def init(path):
    global LOG_PATH
    LOG_PATH = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'a').close()
    if not isinstance(sys.stdout, _Tee):
        sys.stdout = _Tee(sys.stdout, path)
    if not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr, path)


def read_since(offset):
    if LOG_PATH is None or not os.path.exists(LOG_PATH):
        return b'', 0
    try:
        size = os.path.getsize(LOG_PATH)
    except OSError:
        return b'', 0
    if offset > size:
        offset = 0
    with open(LOG_PATH, 'rb') as f:
        f.seek(offset)
        data = f.read()
    return data, size


def read_tail(max_bytes=64 * 1024):
    if LOG_PATH is None or not os.path.exists(LOG_PATH):
        return b'', 0
    try:
        size = os.path.getsize(LOG_PATH)
    except OSError:
        return b'', 0
    start = max(0, size - max_bytes)
    with open(LOG_PATH, 'rb') as f:
        f.seek(start)
        data = f.read()
    return data, size
