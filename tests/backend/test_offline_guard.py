import socket

import pytest


def test_non_loopback_is_still_forbidden():
    with pytest.raises(AssertionError, match="Network is forbidden"):
        socket.socket().connect(("93.184.216.34", 80))