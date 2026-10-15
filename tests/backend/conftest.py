# Backend API tests run the app in-process; allow loopback sockets only
import socket

import pytest

# Captured at import time, before the root conftest patches connect
_real_connect = socket.socket.connect
_LOOPBACK = {"127.0.0.1", "::1"}


@pytest.fixture(autouse=True)
def allow_loopback(offline_environment, monkeypatch):
    # TestClient's event loop on Windows links its own sockets with socketpair(),
    # which connects to 127.0.0.1. Anything else stays forbidden
    def guarded(self, address, *args, **kwargs):
        if isinstance(address, tuple) and address[0] in _LOOPBACK:
            return _real_connect(self, address, *args, **kwargs)
        raise AssertionError("Network is forbidden in unit tests")

    monkeypatch.setattr(socket.socket, "connect", guarded)