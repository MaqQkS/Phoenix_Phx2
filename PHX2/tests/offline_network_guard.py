"""Explicit pytest plugin used by the operational offline review suites."""
import socket

_originals = {}
_blocked = 0


def _deny(*args, **kwargs):
    global _blocked
    _blocked += 1
    raise RuntimeError("OFFLINE_TEST_NETWORK_BLOCKED")


def pytest_sessionstart(session):
    for owner, name in ((socket, "create_connection"), (socket, "getaddrinfo"),
                        (socket.socket, "connect"), (socket.socket, "connect_ex")):
        _originals[(owner, name)] = getattr(owner, name)
        setattr(owner, name, _deny)


def pytest_sessionfinish(session, exitstatus):
    for (owner, name), value in _originals.items():
        setattr(owner, name, value)


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(f"Offline network guard: enabled; blocked socket attempts={_blocked}")
