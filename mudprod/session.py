"""
SessionManager - Persistent connection pool for MUD testing.

Maintains named sessions that persist across test runs,
automatically reconnecting when connections drop.
"""

import logging
import threading
from typing import Dict, Optional, List
from dataclasses import dataclass, field

from .client import MUDClient, LoginConfig, PromptConfig, ConnectionState


@dataclass
class SessionConfig:
    """
    Configuration for creating a session.

    Attributes:
        host: Server hostname or IP
        port: Server port
        login_config: Optional login configuration
        prompt_config: Optional prompt detection configuration
        auto_reconnect: Whether to automatically reconnect on disconnect
        timeout: Connection timeout in seconds
    """
    host: str
    port: int
    login_config: Optional[LoginConfig] = None
    prompt_config: Optional[PromptConfig] = None
    auto_reconnect: bool = True
    timeout: float = 10.0


class SessionManager:
    """
    Manages a pool of named MUD client sessions.

    Sessions persist across multiple test runs and can be reused
    by name. Handles automatic reconnection and connection health.

    Usage:
        manager = SessionManager()

        # Create a session with config
        config = SessionConfig(
            host="localhost",
            port=4000,
            login_config=LoginConfig(steps=[
                ("name:", "testuser"),
                ("password:", "testpass"),
            ])
        )
        session = manager.create("player1", config)

        # Use the session
        response = session.send_command("look")

        # Later, retrieve the same session
        session = manager.get("player1")
        response = session.send_command("inventory")

        # Clean up when done
        manager.close_all()

    Thread-safe for concurrent test execution.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the session manager.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self._sessions: Dict[str, MUDClient] = {}
        self._configs: Dict[str, SessionConfig] = {}
        self._lock = threading.RLock()

    def create(
        self,
        name: str,
        config: SessionConfig,
        connect: bool = True
    ) -> MUDClient:
        """
        Create a new named session.

        Args:
            name: Unique identifier for this session
            config: Session configuration
            connect: Whether to connect immediately (default: True)

        Returns:
            The MUDClient instance

        Raises:
            ValueError: If session name already exists
        """
        with self._lock:
            if name in self._sessions:
                raise ValueError(f"Session '{name}' already exists. Use get() or close() first.")

            client = MUDClient(
                host=config.host,
                port=config.port,
                timeout=config.timeout,
                prompt_config=config.prompt_config,
                logger=self.logger,
                auto_reconnect=config.auto_reconnect,
            )

            self._sessions[name] = client
            self._configs[name] = config

            if connect:
                if not client.connect():
                    self.logger.error(f"Failed to connect session '{name}'")
                elif config.login_config:
                    if not client.login(config.login_config):
                        self.logger.error(f"Failed to login session '{name}'")

            self.logger.info(f"Created session '{name}'")
            return client

    def get(self, name: str) -> Optional[MUDClient]:
        """
        Get an existing session by name.

        Args:
            name: Session identifier

        Returns:
            The MUDClient instance, or None if not found
        """
        with self._lock:
            return self._sessions.get(name)

    def get_or_create(
        self,
        name: str,
        config: SessionConfig
    ) -> MUDClient:
        """
        Get an existing session or create a new one.

        If the session exists but is disconnected, attempts to reconnect.

        Args:
            name: Session identifier
            config: Session configuration (used only if creating)

        Returns:
            The MUDClient instance
        """
        with self._lock:
            if name in self._sessions:
                client = self._sessions[name]
                if not client.is_connected:
                    self.logger.info(f"Session '{name}' disconnected, reconnecting...")
                    client.reconnect()
                return client

            return self.create(name, config)

    def close(self, name: str) -> bool:
        """
        Close and remove a session.

        Args:
            name: Session identifier

        Returns:
            True if session was closed, False if not found
        """
        with self._lock:
            if name not in self._sessions:
                return False

            client = self._sessions.pop(name)
            self._configs.pop(name, None)
            client.disconnect()
            self.logger.info(f"Closed session '{name}'")
            return True

    def close_all(self) -> int:
        """
        Close all sessions.

        Returns:
            Number of sessions closed
        """
        with self._lock:
            count = len(self._sessions)
            for name in list(self._sessions.keys()):
                self.close(name)
            self.logger.info(f"Closed {count} sessions")
            return count

    def list_sessions(self) -> List[str]:
        """
        List all session names.

        Returns:
            List of session names
        """
        with self._lock:
            return list(self._sessions.keys())

    def status(self) -> Dict[str, Dict]:
        """
        Get status of all sessions.

        Returns:
            Dict mapping session names to status info
        """
        with self._lock:
            result = {}
            for name, client in self._sessions.items():
                result[name] = {
                    "connected": client.is_connected,
                    "in_game": client.is_in_game,
                    "state": client.state.name,
                    "host": client.host,
                    "port": client.port,
                }
            return result

    def ensure_all_connected(self) -> Dict[str, bool]:
        """
        Ensure all sessions are connected, reconnecting if needed.

        Returns:
            Dict mapping session names to connection success status
        """
        with self._lock:
            results = {}
            for name, client in self._sessions.items():
                results[name] = client.ensure_connected()
            return results

    def __len__(self) -> int:
        """Number of sessions."""
        with self._lock:
            return len(self._sessions)

    def __contains__(self, name: str) -> bool:
        """Check if session exists."""
        with self._lock:
            return name in self._sessions

    def __enter__(self) -> "SessionManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - closes all sessions."""
        self.close_all()
        return None
