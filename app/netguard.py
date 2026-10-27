"""파이썬 네트워크 차단 장치 (지시서 2절 4항).

127.0.0.1·localhost·유닉스 소켓이 아닌 곳으로 연결하려 하면 예외를 던지고,
시도한 주소만 logs/netguard.log에 남긴다(값은 남기지 않는다).
"""
from __future__ import annotations

import datetime as _dt
import os
import socket

_LOCAL = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}
_LOG = None


def _hit(kind: str, addr) -> None:
    line = f"{_dt.datetime.now().isoformat(timespec='seconds')} pid={os.getpid()} {kind} {addr!r}\n"
    if _LOG:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(line)
    raise ConnectionRefusedError(f"netguard: 외부 연결 차단 ({kind})")


def _is_local(host) -> bool:
    if host is None:
        return True
    h = str(host).strip("[]").lower()
    return h in _LOCAL or h.startswith("127.")


def install(log_path: str) -> None:
    global _LOG
    _LOG = log_path
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    if getattr(socket, "_netguard_installed", False):
        return
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex
    orig_create = socket.create_connection
    orig_gai = socket.getaddrinfo

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address[0]):
            _hit("socket.connect", address[0])
        return orig_connect(self, address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address[0]):
            _hit("socket.connect_ex", address[0])
        return orig_connect_ex(self, address)

    def create_connection(address, *a, **kw):
        if not _is_local(address[0]):
            _hit("socket.create_connection", address[0])
        return orig_create(address, *a, **kw)

    def getaddrinfo(host, *a, **kw):
        if not _is_local(host):
            _hit("socket.getaddrinfo", host)
        return orig_gai(host, *a, **kw)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.create_connection = create_connection
    socket.getaddrinfo = getaddrinfo
    socket._netguard_installed = True


OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "KORDOC_OFFLINE": "1",
    "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}


def set_offline_env() -> None:
    os.environ.update(OFFLINE_ENV)
