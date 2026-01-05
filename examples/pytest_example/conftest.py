"""
pytest fixtures for MUD testing.

This file provides reusable fixtures for your test files.
Customize the HOST, PORT, and login configuration for your MUD.
"""

import pytest
from mudprod import MUDClient, LoginConfig

# Configure for your MUD
HOST = "localhost"
PORT = 4000
USERNAME = "testuser"
PASSWORD = "testpass"


@pytest.fixture(scope="session")
def server_available():
    """Check if server is available before running tests."""
    import socket
    try:
        sock = socket.create_connection((HOST, PORT), timeout=5)
        sock.close()
        return True
    except (socket.error, socket.timeout):
        pytest.skip(f"MUD server at {HOST}:{PORT} is not available")
        return False


@pytest.fixture
def client(server_available):
    """Provide a connected and logged-in client."""
    c = MUDClient(HOST, PORT)

    if not c.connect():
        pytest.fail("Could not connect to server")

    # Customize login steps for your MUD
    login_config = LoginConfig(
        steps=[
            ("name", USERNAME),
            ("password", PASSWORD),
        ],
    )

    if not c.login(login_config):
        c.disconnect()
        pytest.fail("Could not login")

    yield c

    # Cleanup
    try:
        c.send_command("quit")
    except:
        pass
    c.disconnect()


@pytest.fixture
def raw_client(server_available):
    """Provide a connected but NOT logged-in client."""
    c = MUDClient(HOST, PORT)

    if not c.connect():
        pytest.fail("Could not connect to server")

    yield c
    c.disconnect()
