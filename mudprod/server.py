"""
Session Server - Background process for persistent MUD connections.

Maintains MUD connections across multiple client invocations,
allowing agents to pilot a MUD over many turns without reconnecting.
"""

import json
import os
import socket
import threading
import time
import logging
import signal
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import asdict

from .client import MUDClient, LoginConfig, PromptConfig
from .session import SessionManager, SessionConfig


DEFAULT_SOCKET_PATH = "/tmp/mudprod.sock"
DEFAULT_PID_FILE = "/tmp/mudprod.pid"


class SessionServer:
    """
    Background server that maintains persistent MUD connections.

    Accepts commands via Unix socket, executes them on persistent
    MUD sessions, and returns responses.

    Usage:
        # Start server (typically in background)
        server = SessionServer()
        server.start()

        # From another process, use SessionClient to send commands
    """

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET_PATH,
        pid_file: str = DEFAULT_PID_FILE,
        logger: Optional[logging.Logger] = None,
    ):
        self.socket_path = socket_path
        self.pid_file = pid_file
        self.logger = logger or logging.getLogger(__name__)
        self.manager = SessionManager(logger=self.logger)
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        # Triggers: session_name -> list of (pattern, command)
        self._triggers: Dict[str, list] = {}
        # Repeat commands: session_name -> command to repeat on balance
        self._repeat_commands: Dict[str, str] = {}
        # Background monitor threads
        self._monitor_threads: Dict[str, threading.Thread] = {}

    def start(self) -> None:
        """Start the server and listen for commands."""
        # Clean up old socket
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        # Write PID file
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Create Unix socket
        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(self.socket_path)
        self._server_socket.listen(5)
        self._running = True

        self.logger.info(f"Session server started on {self.socket_path}")

        try:
            while self._running:
                try:
                    self._server_socket.settimeout(1.0)
                    client_socket, _ = self._server_socket.accept()
                    self._handle_client(client_socket)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self._running:
                        self.logger.error(f"Error accepting connection: {e}")
        finally:
            self._cleanup()

    def _handle_signal(self, signum, frame) -> None:
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self._running = False

    def _cleanup(self) -> None:
        """Clean up resources."""
        self.manager.close_all()
        if self._server_socket:
            self._server_socket.close()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        if os.path.exists(self.pid_file):
            os.unlink(self.pid_file)
        self.logger.info("Server stopped")

    def _handle_client(self, client_socket: socket.socket) -> None:
        """Handle a client connection."""
        try:
            data = b""
            while True:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            if data:
                request = json.loads(data.decode("utf-8"))
                response = self._process_request(request)
                client_socket.sendall(json.dumps(response).encode("utf-8"))
        except Exception as e:
            self.logger.error(f"Error handling client: {e}")
            try:
                client_socket.sendall(json.dumps({
                    "success": False,
                    "error": str(e)
                }).encode("utf-8"))
            except:
                pass
        finally:
            client_socket.close()

    def _process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a command request."""
        cmd = request.get("command")

        if cmd == "connect":
            return self._cmd_connect(request)
        elif cmd == "send":
            return self._cmd_send(request)
        elif cmd == "send_raw":
            return self._cmd_send_raw(request)
        elif cmd == "read":
            return self._cmd_read(request)
        elif cmd == "peek":
            return self._cmd_peek(request)
        elif cmd == "batch":
            return self._cmd_batch(request)
        elif cmd == "status":
            return self._cmd_status(request)
        elif cmd == "disconnect":
            return self._cmd_disconnect(request)
        elif cmd == "repeat":
            return self._cmd_repeat(request)
        elif cmd == "trigger":
            return self._cmd_trigger(request)
        elif cmd == "triggers":
            return self._cmd_triggers(request)
        elif cmd == "shutdown":
            self._running = False
            return {"success": True, "message": "Server shutting down"}
        else:
            return {"success": False, "error": f"Unknown command: {cmd}"}

    def _cmd_connect(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle connect command."""
        name = request.get("session", "default")
        host = request.get("host")
        port = request.get("port")
        login_steps = request.get("login_steps", [])

        if not host or not port:
            return {"success": False, "error": "host and port required"}

        try:
            login_config = None
            if login_steps:
                login_config = LoginConfig(steps=login_steps)

            config = SessionConfig(
                host=host,
                port=port,
                login_config=login_config,
                auto_reconnect=True,
                timeout=request.get("timeout", 15.0),
            )

            if name in self.manager:
                session = self.manager.get(name)
                if session and session.is_connected:
                    return {
                        "success": True,
                        "message": "Already connected",
                        "state": session.state.name,
                    }
                # Reconnect
                session.reconnect()
            else:
                session = self.manager.create(name, config)

            return {
                "success": session.is_connected,
                "state": session.state.name if session else "DISCONNECTED",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _cmd_send(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle send command (send and wait for response)."""
        name = request.get("session", "default")
        text = request.get("text", "")
        wait_time = request.get("wait_time", 5.0)

        session = self.manager.get(name)
        if not session:
            return {"success": False, "error": f"Session '{name}' not found"}

        if not session.is_connected:
            session.reconnect()
            if not session.is_connected:
                return {"success": False, "error": "Not connected"}

        response = session.send_command(text, wait_time=wait_time)

        # Check triggers on the response
        self._check_triggers_inline(name, response.raw, session)

        return {
            "success": True,
            "raw": response.raw,
            "clean": response.clean,
            "lines": response.lines,
            "prompt_detected": response.prompt_detected,
        }

    def _check_triggers_inline(self, name: str, data: str, session) -> None:
        """Check triggers and fire them (inline, not threaded)."""
        import re

        # Check for balance recovery (repeat command)
        if name in self._repeat_commands:
            if "You have recovered balance" in data:
                cmd = self._repeat_commands[name]
                self.logger.info(f"Balance recovered, queuing: {cmd}")
                session.send_raw(f"{cmd}\n")

        # Check custom triggers
        for pattern, cmd in self._triggers.get(name, []):
            if re.search(pattern, data, re.IGNORECASE):
                self.logger.info(f"Trigger matched '{pattern}', sending: {cmd}")
                session.send_raw(f"{cmd}\n")

    def _cmd_send_raw(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle send_raw command (send without waiting)."""
        name = request.get("session", "default")
        text = request.get("text", "")

        session = self.manager.get(name)
        if not session:
            return {"success": False, "error": f"Session '{name}' not found"}

        session.send_raw(text)
        return {"success": True}

    def _cmd_read(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle read command (read available data)."""
        name = request.get("session", "default")

        session = self.manager.get(name)
        if not session:
            return {"success": False, "error": f"Session '{name}' not found"}

        response = session.read_available()

        # Check triggers on the response
        if response.raw:
            self._check_triggers_inline(name, response.raw, session)

        return {
            "success": True,
            "raw": response.raw,
            "clean": response.clean,
        }

    def _cmd_peek(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle peek command - check for data without blocking.

        Unlike 'read', peek uses select() to wait up to max_wait seconds
        for data to arrive. Returns immediately if data is available.
        """
        import select as sel

        name = request.get("session", "default")
        max_wait = request.get("max_wait", 0.1)  # Default 100ms

        session = self.manager.get(name)
        if not session:
            return {"success": False, "error": f"Session '{name}' not found"}

        if not session.is_connected or session._socket is None:
            return {"success": False, "error": "Not connected"}

        # Use select to check if data is available
        start = time.time()
        data = ""

        while time.time() - start < max_wait:
            remaining = max_wait - (time.time() - start)
            poll_time = min(0.05, remaining)

            readable, _, _ = sel.select([session._socket], [], [], poll_time)
            if readable:
                chunk = session._read_available()
                if chunk:
                    data += chunk
                    # Check for more data immediately
                    continue
            elif data:
                # Got data and no more coming
                break

        # Check triggers if we got data
        if data:
            self._check_triggers_inline(name, data, session)

        from .response import MUDResponse
        response = MUDResponse(raw=data)

        return {
            "success": True,
            "raw": response.raw,
            "clean": response.clean,
            "has_data": bool(data),
        }

    def _cmd_batch(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle batch command - send multiple commands and collect responses.

        Reduces round-trip latency by batching multiple commands.
        """
        name = request.get("session", "default")
        commands = request.get("commands", [])
        wait_time = request.get("wait_time", 2.0)  # Shorter default for batches
        fast = request.get("fast", False)

        if not commands:
            return {"success": False, "error": "No commands provided"}

        session = self.manager.get(name)
        if not session:
            return {"success": False, "error": f"Session '{name}' not found"}

        if not session.is_connected:
            session.reconnect()
            if not session.is_connected:
                return {"success": False, "error": "Not connected"}

        results = []
        for cmd in commands:
            response = session.send_command(cmd, wait_time=wait_time, fast=fast)
            self._check_triggers_inline(name, response.raw, session)
            results.append({
                "command": cmd,
                "raw": response.raw,
                "clean": response.clean,
                "prompt_detected": response.prompt_detected,
            })

        return {
            "success": True,
            "results": results,
            "count": len(results),
        }

    def _cmd_status(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle status command."""
        name = request.get("session")

        if name:
            session = self.manager.get(name)
            if not session:
                return {"success": False, "error": f"Session '{name}' not found"}
            return {
                "success": True,
                "connected": session.is_connected,
                "in_game": session.is_in_game,
                "state": session.state.name,
            }
        else:
            return {
                "success": True,
                "sessions": self.manager.status(),
            }

    def _cmd_disconnect(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle disconnect command."""
        name = request.get("session", "default")

        # Stop any monitoring for this session
        self._stop_monitor(name)

        if self.manager.close(name):
            return {"success": True, "message": f"Session '{name}' closed"}
        else:
            return {"success": False, "error": f"Session '{name}' not found"}

    def _cmd_repeat(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle repeat command - auto-send command on balance recovery."""
        name = request.get("session", "default")
        cmd = request.get("text", "")

        if not cmd or cmd.lower() == "off":
            # Stop repeating
            if name in self._repeat_commands:
                del self._repeat_commands[name]
            return {"success": True, "message": "Repeat disabled"}

        session = self.manager.get(name)
        if not session:
            return {"success": False, "error": f"Session '{name}' not found"}

        self._repeat_commands[name] = cmd
        return {"success": True, "message": f"Will repeat '{cmd}' on balance recovery"}

    def _cmd_trigger(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle trigger command - add or remove triggers."""
        name = request.get("session", "default")
        pattern = request.get("pattern", "")
        cmd = request.get("text", "")
        action = request.get("action", "add")

        if action == "clear":
            self._triggers[name] = []
            return {"success": True, "message": "All triggers cleared"}

        if action == "remove":
            if name in self._triggers:
                self._triggers[name] = [
                    (p, c) for p, c in self._triggers[name] if p != pattern
                ]
            return {"success": True, "message": f"Trigger for '{pattern}' removed"}

        if not pattern or not cmd:
            return {"success": False, "error": "pattern and text required"}

        if name not in self._triggers:
            self._triggers[name] = []

        self._triggers[name].append((pattern, cmd))
        return {"success": True, "message": f"Trigger added: '{pattern}' -> '{cmd}'"}

    def _cmd_triggers(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """List triggers for a session."""
        name = request.get("session", "default")
        triggers = self._triggers.get(name, [])
        repeat = self._repeat_commands.get(name, None)
        return {
            "success": True,
            "triggers": [{"pattern": p, "command": c} for p, c in triggers],
            "repeat": repeat,
        }

    def _start_monitor(self, name: str) -> None:
        """Start background monitor thread for a session."""
        if name in self._monitor_threads:
            return  # Already monitoring

        session = self.manager.get(name)
        if not session:
            return

        def monitor_loop():
            self.logger.info(f"Starting monitor for session '{name}'")
            while self._running and name in self._repeat_commands or name in self._triggers:
                session = self.manager.get(name)
                if not session or not session.is_connected:
                    time.sleep(0.5)
                    continue

                try:
                    data = session._read_available()
                    if data:
                        self._process_triggers(name, data, session)
                except Exception as e:
                    self.logger.error(f"Monitor error for '{name}': {e}")

                time.sleep(0.1)

            self.logger.info(f"Monitor stopped for session '{name}'")
            if name in self._monitor_threads:
                del self._monitor_threads[name]

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()
        self._monitor_threads[name] = thread

    def _stop_monitor(self, name: str) -> None:
        """Stop monitoring a session."""
        if name in self._repeat_commands:
            del self._repeat_commands[name]
        if name in self._triggers:
            del self._triggers[name]
        # Thread will exit on next iteration

    def _process_triggers(self, name: str, data: str, session) -> None:
        """Process incoming data against triggers."""
        import re

        # Check for balance recovery (repeat command)
        if name in self._repeat_commands:
            if "You have recovered balance" in data:
                cmd = self._repeat_commands[name]
                self.logger.info(f"Balance recovered, sending: {cmd}")
                session.send_raw(f"{cmd}\n")

        # Check custom triggers
        for pattern, cmd in self._triggers.get(name, []):
            if re.search(pattern, data, re.IGNORECASE):
                self.logger.info(f"Trigger matched '{pattern}', sending: {cmd}")
                session.send_raw(f"{cmd}\n")


class SessionClient:
    """
    Client for communicating with the SessionServer.

    Usage:
        client = SessionClient()

        # Connect to a MUD
        client.connect("localhost", 4000, login_steps=[
            ("name:", "user"),
            ("password:", "pass"),
        ])

        # Send commands
        response = client.send("look")
        print(response["clean"])

        # Check status
        print(client.status())
    """

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH):
        self.socket_path = socket_path

    def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send a request to the server and return the response."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self.socket_path)
            sock.sendall(json.dumps(request).encode("utf-8") + b"\n")

            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk

            return json.loads(data.decode("utf-8"))
        finally:
            sock.close()

    def connect(
        self,
        host: str,
        port: int,
        session: str = "default",
        login_steps: list = None,
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        """Connect to a MUD server."""
        return self._send_request({
            "command": "connect",
            "session": session,
            "host": host,
            "port": port,
            "login_steps": login_steps or [],
            "timeout": timeout,
        })

    def send(
        self,
        text: str,
        session: str = "default",
        wait_time: float = 5.0,
    ) -> Dict[str, Any]:
        """Send a command and get response."""
        return self._send_request({
            "command": "send",
            "session": session,
            "text": text,
            "wait_time": wait_time,
        })

    def send_raw(self, text: str, session: str = "default") -> Dict[str, Any]:
        """Send raw text without waiting."""
        return self._send_request({
            "command": "send_raw",
            "session": session,
            "text": text,
        })

    def read(self, session: str = "default") -> Dict[str, Any]:
        """Read available data."""
        return self._send_request({
            "command": "read",
            "session": session,
        })

    def peek(self, session: str = "default", max_wait: float = 0.1) -> Dict[str, Any]:
        """
        Peek for available data without blocking long.

        Args:
            session: Session name
            max_wait: Max time to wait for data (default 100ms)

        Returns:
            Response with 'has_data' bool indicating if data was found
        """
        return self._send_request({
            "command": "peek",
            "session": session,
            "max_wait": max_wait,
        })

    def batch(
        self,
        commands: list,
        session: str = "default",
        wait_time: float = 2.0,
        fast: bool = False,
    ) -> Dict[str, Any]:
        """
        Send multiple commands and collect all responses.

        Args:
            commands: List of commands to send
            session: Session name
            wait_time: Time to wait for each response
            fast: Use fast mode (shorter timeout)

        Returns:
            Response with 'results' list of individual command responses
        """
        return self._send_request({
            "command": "batch",
            "session": session,
            "commands": commands,
            "wait_time": wait_time,
            "fast": fast,
        })

    def status(self, session: str = None) -> Dict[str, Any]:
        """Get session status."""
        req = {"command": "status"}
        if session:
            req["session"] = session
        return self._send_request(req)

    def disconnect(self, session: str = "default") -> Dict[str, Any]:
        """Disconnect a session."""
        return self._send_request({
            "command": "disconnect",
            "session": session,
        })

    def repeat(self, command: str, session: str = "default") -> Dict[str, Any]:
        """Set a command to repeat on balance recovery. Use 'off' to disable."""
        return self._send_request({
            "command": "repeat",
            "session": session,
            "text": command,
        })

    def trigger(
        self,
        pattern: str,
        command: str,
        session: str = "default",
        action: str = "add"
    ) -> Dict[str, Any]:
        """Add/remove a trigger. Actions: add, remove, clear."""
        return self._send_request({
            "command": "trigger",
            "session": session,
            "pattern": pattern,
            "text": command,
            "action": action,
        })

    def triggers(self, session: str = "default") -> Dict[str, Any]:
        """List active triggers."""
        return self._send_request({
            "command": "triggers",
            "session": session,
        })

    def shutdown(self) -> Dict[str, Any]:
        """Shut down the server."""
        return self._send_request({"command": "shutdown"})

    @staticmethod
    def is_server_running(socket_path: str = DEFAULT_SOCKET_PATH) -> bool:
        """Check if server is running."""
        if not os.path.exists(socket_path):
            return False
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(socket_path)
            sock.close()
            return True
        except:
            return False


def start_server_background(
    socket_path: str = DEFAULT_SOCKET_PATH,
    log_file: str = "/tmp/mudprod_server.log",
) -> int:
    """
    Start the session server in the background.

    Returns:
        PID of the server process
    """
    pid = os.fork()
    if pid > 0:
        # Parent - wait a moment for server to start
        time.sleep(0.5)
        return pid

    # Child - become session leader
    os.setsid()

    # Fork again
    pid = os.fork()
    if pid > 0:
        os._exit(0)

    # Grandchild - this is our server
    # Redirect stdout/stderr to log file
    sys.stdout.flush()
    sys.stderr.flush()

    with open(log_file, "a") as log:
        os.dup2(log.fileno(), sys.stdout.fileno())
        os.dup2(log.fileno(), sys.stderr.fileno())

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    server = SessionServer(socket_path=socket_path)
    server.start()
    os._exit(0)
