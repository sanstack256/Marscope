"""
MARSCOPE Persistence & Concurrency Utilities (Prompt 22 Section 5).

Provides:
  - Process-safe + thread-safe locked read-modify-write critical sections (`locked_resource`)
  - Atomic JSON/text persistence (`atomic_write_text`, `atomic_write_json`) with
    write -> flush -> os.fsync -> os.replace and temporary-file cleanup on failure
  - Strict finite-float validation (`allow_nan=False`) to prevent silent NaN/Inf JSON corruption
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None  # type: ignore[assignment]

_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_STATE = threading.local()


def _get_thread_lock(lock_path: Path) -> threading.RLock:
    key = str(lock_path.resolve())
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _THREAD_LOCKS[key] = lock
        return lock


@contextmanager
def locked_resource(lock_path: Path) -> Iterator[None]:
    """Acquire an in-process RLock and re-entrant-safe POSIX flock around state mutations."""
    if fcntl is None:
        raise RuntimeError(
            "POSIX file locking (fcntl) is required for safe persistent store writes on this platform."
        )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    key = str(lock_path.resolve())
    tlock = _get_thread_lock(lock_path)
    with tlock:
        held: dict[str, int] = getattr(_THREAD_STATE, "held", None)
        if held is None:
            held = {}
            _THREAD_STATE.held = held
        depth = held.get(key, 0)
        if depth > 0:
            held[key] = depth + 1
            try:
                yield
            finally:
                held[key] = depth
            return
        with lock_path.open("a+", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            held[key] = 1
            try:
                yield
            finally:
                held.pop(key, None)
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def atomic_write_text(target_path: Path, text: str) -> None:
    """Atomically write UTF-8 text via temp file + fsync + os.replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target_path.parent),
        prefix=f".{target_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_json(
    target_path: Path,
    payload: Any,
    *,
    indent: int = 2,
    sort_keys: bool = True,
    allow_nan: bool = False,
) -> None:
    """Serialize JSON strictly (disallowing NaN/Infinity by default) and write atomically."""
    serialized = json.dumps(
        payload,
        indent=indent,
        sort_keys=sort_keys,
        ensure_ascii=False,
        allow_nan=allow_nan,
    )
    atomic_write_text(target_path, serialized)
