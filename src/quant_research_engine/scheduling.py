"""本机全量回测与行情/因子日更的共享—排他文件锁。"""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_LOCK_PATH = Path("/tmp/qre-market-refresh.lock")


class RefreshInProgress(RuntimeError):
    """非阻塞获取失败：另一侧正在执行或等待调度。"""


def _lock_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("QRE_SCHEDULING_LOCK_PATH", DEFAULT_LOCK_PATH))


@contextmanager
def refresh_lock(
    path: str | Path | None = None,
    *,
    exclusive: bool,
    blocking: bool = True,
) -> Iterator[None]:
    """日更 ``exclusive=True``；全量回测 ``False``，进程退出自动释放。"""
    lock_path = _lock_path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    if not blocking:
        operation |= fcntl.LOCK_NB
    try:
        try:
            fcntl.flock(handle.fileno(), operation)
        except BlockingIOError as exc:
            raise RefreshInProgress("行情/因子日更与全量回测调度锁被占用") from exc
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
