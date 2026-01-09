"""
MUDClient - Telnet client for MUD server testing.

Connects to MUD servers, handles login flows, sends commands,
and captures responses for validation.
"""

import socket
import time
import logging
import re
from typing import Optional, List, Tuple, Callable, Union
from dataclasses import dataclass, field
from enum import Enum, auto

from .ansi import clean_output
from .response import MUDResponse


class ConnectionState(Enum):
    """Tracks the client's connection state."""
    DISCONNECTED = auto()
    CONNECTED = auto()
    AUTHENTICATING = auto()
    IN_GAME = auto()


@dataclass
class PromptConfig:
    """
    Configuration for prompt detection.

    Attributes:
        patterns: List of regex patterns that indicate a prompt
        end_chars: Simple characters that indicate end of prompt (e.g., '>', ':')
        custom_detector: Optional callable for custom prompt detection
    """
    patterns: List[str] = field(default_factory=lambda: [
        r'>\s*$',           # Standard ">" prompt
        r':\s*$',           # Menu/input prompt ending in ":"
        r'\]\s*$',          # Bracketed prompt ending in "]"
    ])
    end_chars: str = ">]:"
    custom_detector: Optional[Callable[[str], bool]] = None


@dataclass
class LoginConfig:
    """
    Configuration for the login flow.

    Different MUDs have different login sequences. Configure this
    to match your MUD's login flow.

    Attributes:
        steps: List of (prompt_pattern, response) tuples
        success_patterns: Patterns that indicate successful login
        failure_patterns: Patterns that indicate failed login
    """
    steps: List[Tuple[str, str]] = field(default_factory=list)
    success_patterns: List[str] = field(default_factory=lambda: [
        r'>\s*$',           # Got a game prompt
        r'Exits:',          # Room description
        r'reconnected',     # Reconnection message
    ])
    failure_patterns: List[str] = field(default_factory=lambda: [
        r'[Ii]nvalid',
        r'[Ff]ailed',
        r'[Ii]ncorrect',
    ])


class MUDClient:
    """
    Telnet client for MUD server interaction.

    Basic usage:
        client = MUDClient("localhost", 4000)
        client.connect()
        client.send_raw("myusername\\n")
        client.send_raw("mypassword\\n")

        response = client.send_command("look")
        print(response.clean)

        client.disconnect()

    With login helper:
        client = MUDClient("localhost", 4000)
        client.connect()

        login_config = LoginConfig(steps=[
            ("name:", "myusername"),
            ("password:", "mypassword"),
        ])
        client.login(login_config)

        response = client.send_command("look")
        client.disconnect()

    As context manager:
        with MUDClient("localhost", 4000) as client:
            client.login(login_config)
            response = client.send_command("look")
        # Automatically disconnects
    """

    DEFAULT_TIMEOUT = 10.0
    DEFAULT_COMMAND_TIMEOUT = 5.0
    READ_DELAY = 0.3
    READ_CHUNK_SIZE = 4096

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = DEFAULT_TIMEOUT,
        prompt_config: Optional[PromptConfig] = None,
        logger: Optional[logging.Logger] = None,
        auto_reconnect: bool = False,
    ):
        """
        Initialize MUD client.

        Args:
            host: Server hostname or IP
            port: Server port
            timeout: Connection timeout in seconds
            prompt_config: Custom prompt detection configuration
            logger: Optional logger instance
            auto_reconnect: Automatically reconnect if connection drops
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.prompt_config = prompt_config or PromptConfig()
        self.logger = logger or logging.getLogger(__name__)
        self.auto_reconnect = auto_reconnect

        self._socket: Optional[socket.socket] = None
        self._state = ConnectionState.DISCONNECTED
        self._buffer = ""
        self._login_config: Optional[LoginConfig] = None

    def __enter__(self) -> "MUDClient":
        """Context manager entry - connects automatically."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - disconnects automatically."""
        self.disconnect()
        return None

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Whether client is connected to server."""
        return self._socket is not None and self._state != ConnectionState.DISCONNECTED

    @property
    def is_in_game(self) -> bool:
        """Whether client is logged in and in-game."""
        return self._state == ConnectionState.IN_GAME

    def connect(self) -> bool:
        """
        Establish TCP connection to the MUD server.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._socket = socket.create_connection(
                (self.host, self.port),
                timeout=self.timeout
            )
            self._socket.setblocking(False)
            self._state = ConnectionState.CONNECTED

            # Read initial greeting/banner
            time.sleep(0.5)
            greeting = self._read_available()
            self.logger.debug(f"Greeting: {greeting[:200]}...")

            self.logger.info(f"Connected to {self.host}:{self.port}")
            return True

        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            return False

    def disconnect(self) -> None:
        """Clean disconnect from server."""
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None
        self._state = ConnectionState.DISCONNECTED
        self.logger.info("Disconnected")

    def reconnect(self) -> bool:
        """
        Reconnect to the server and re-login if credentials are stored.

        Returns:
            True if reconnection (and re-login if applicable) successful
        """
        self.logger.info("Attempting reconnect...")
        self.disconnect()

        if not self.connect():
            return False

        if self._login_config:
            return self.login(self._login_config)

        return True

    def ensure_connected(self) -> bool:
        """
        Ensure the client is connected, reconnecting if necessary.

        Returns:
            True if connected (or successfully reconnected)
        """
        if self.is_connected:
            return True

        if self.auto_reconnect:
            return self.reconnect()

        return False

    def login(self, config: LoginConfig) -> bool:
        """
        Execute login flow based on configuration.

        Args:
            config: LoginConfig with steps and success/failure patterns

        Returns:
            True if login successful, False otherwise
        """
        self._state = ConnectionState.AUTHENTICATING
        self._login_config = config  # Store for auto-reconnect

        try:
            for prompt_pattern, response_text in config.steps:
                # Wait for the expected prompt
                found, output = self.wait_for_pattern(
                    prompt_pattern,
                    timeout=self.timeout,
                    regex=True
                )

                if not found:
                    self.logger.warning(f"Did not see expected prompt: {prompt_pattern}")
                    # Continue anyway - some MUDs don't wait for input

                # Send the response
                self.send_raw(f"{response_text}\n")
                time.sleep(self.READ_DELAY)

            # Read final response and check for success/failure
            time.sleep(self.READ_DELAY * 2)
            final_output = self._read_available()
            clean = clean_output(final_output)

            # Check for failure patterns
            for pattern in config.failure_patterns:
                if re.search(pattern, clean):
                    self.logger.error(f"Login failed - matched: {pattern}")
                    return False

            # Check for success patterns
            for pattern in config.success_patterns:
                if re.search(pattern, clean):
                    self._state = ConnectionState.IN_GAME
                    self.logger.info("Login successful")
                    return True

            # No explicit success pattern, but also no failure
            self._state = ConnectionState.IN_GAME
            self.logger.info("Login completed (no explicit success pattern)")
            return True

        except Exception as e:
            self.logger.error(f"Login failed: {e}")
            return False

    def send_command(
        self,
        command: str,
        wait_time: float = None
    ) -> MUDResponse:
        """
        Send a command and receive response.

        Args:
            command: The command to send (e.g., "look", "say hello")
            wait_time: Time to wait for response (default: DEFAULT_COMMAND_TIMEOUT)

        Returns:
            MUDResponse with raw and cleaned output
        """
        if not self.ensure_connected():
            self.logger.error("Not connected and could not reconnect")
            return MUDResponse(raw="", prompt_detected=False)

        if wait_time is None:
            wait_time = self.DEFAULT_COMMAND_TIMEOUT

        start = time.time()

        self.send_raw(f"{command}\n")
        time.sleep(min(wait_time, self.READ_DELAY * 2))

        # Read response with timeout
        response = ""
        while time.time() - start < wait_time:
            chunk = self._read_available()
            if chunk:
                response += chunk
                # If we see a prompt, we're done
                if self._detect_prompt(response):
                    break
            time.sleep(0.1)

        return MUDResponse(
            raw=response,
            prompt_detected=self._detect_prompt(response)
        )

    def send_raw(self, data: str) -> None:
        """
        Send raw data to server without waiting for response.

        Args:
            data: Raw string to send (include \\n for newlines)
        """
        if self._socket:
            self._socket.sendall(data.encode('utf-8'))
            self.logger.debug(f"Sent: {repr(data)}")

    def read_available(self) -> MUDResponse:
        """Read all immediately available data from server."""
        raw = self._read_available()
        return MUDResponse(raw=raw)

    def wait_for_pattern(
        self,
        pattern: str,
        timeout: float = 10.0,
        regex: bool = False
    ) -> Tuple[bool, str]:
        """
        Wait for a specific pattern in output.

        Args:
            pattern: String or regex pattern to wait for
            timeout: Max time to wait in seconds
            regex: Treat pattern as regex

        Returns:
            Tuple of (found: bool, accumulated_output: str)
        """
        start = time.time()
        accumulated = ""

        while time.time() - start < timeout:
            chunk = self._read_available()
            accumulated += chunk

            clean = clean_output(accumulated)

            if regex:
                if re.search(pattern, clean, re.IGNORECASE):
                    return True, accumulated
            else:
                if pattern.lower() in clean.lower():
                    return True, accumulated

            time.sleep(0.1)

        return False, accumulated

    def _read_available(self) -> str:
        """Read all immediately available data from socket."""
        if not self._socket:
            return ""

        data = b""
        try:
            while True:
                chunk = self._socket.recv(self.READ_CHUNK_SIZE)
                if not chunk:
                    # Empty bytes means server closed the connection
                    self.logger.info("Server closed connection")
                    self._state = ConnectionState.DISCONNECTED
                    self._socket = None
                    break
                data += chunk
        except BlockingIOError:
            pass  # No more data available
        except ConnectionResetError:
            self.logger.info("Connection reset by server")
            self._state = ConnectionState.DISCONNECTED
            self._socket = None
        except Exception as e:
            self.logger.debug(f"Read error (often normal): {e}")

        result = data.decode('utf-8', errors='replace')
        if result:
            self.logger.debug(f"Read {len(result)} bytes")
        return result

    def _detect_prompt(self, text: str) -> bool:
        """
        Detect if text ends with a MUD prompt.

        Uses the configured PromptConfig to detect prompts.
        """
        # Custom detector takes precedence
        if self.prompt_config.custom_detector:
            return self.prompt_config.custom_detector(text)

        clean = clean_output(text).rstrip()

        # Check simple end characters
        if clean and clean[-1] in self.prompt_config.end_chars:
            return True

        # Check regex patterns
        for pattern in self.prompt_config.patterns:
            if re.search(pattern, clean):
                return True

        return False


def quick_connect(
    host: str,
    port: int,
    command: str,
    login_steps: List[Tuple[str, str]] = None,
) -> str:
    """
    Quick one-shot test: connect, optionally login, run command, return output.

    Args:
        host: Server hostname
        port: Server port
        command: Command to execute
        login_steps: Optional list of (prompt, response) tuples for login

    Returns:
        Cleaned command output
    """
    client = MUDClient(host, port)
    try:
        if not client.connect():
            return "ERROR: Could not connect"

        if login_steps:
            config = LoginConfig(steps=login_steps)
            if not client.login(config):
                return "ERROR: Could not login"

        response = client.send_command(command)
        return response.clean
    finally:
        client.disconnect()
