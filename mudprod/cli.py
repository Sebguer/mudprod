#!/usr/bin/env python3
"""
CLI for mudprod session server.

Usage:
    mudprod start                     Start the session server
    mudprod connect HOST PORT [STEPS] Connect to a MUD
    mudprod send COMMAND              Send command, print response
    mudprod raw TEXT                  Send raw text (no wait)
    mudprod read                      Read available output
    mudprod status                    Show session status
    mudprod stop                      Stop server and disconnect

Set MUDPROD_LOG to a file path to log all I/O.
"""

import sys
import os
import json
from datetime import datetime

from .server import SessionClient, SessionServer, start_server_background, DEFAULT_SOCKET_PATH


def log_io(direction: str, text: str) -> None:
    """Log input/output to file if MUDPROD_LOG is set."""
    log_file = os.environ.get("MUDPROD_LOG")
    if not log_file:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"[{timestamp}] {direction}\n")
        f.write(f"{'='*60}\n")
        f.write(text)
        f.write("\n")


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage: mudprod <command> [args]")
        print("Commands: start, connect, send, raw, read, status, stop")
        return 1

    cmd = args[0]
    rest = args[1:]

    if cmd == "start":
        if SessionClient.is_server_running():
            print("already running")
        else:
            start_server_background()
            print("started")
        return 0

    if cmd == "stop":
        if SessionClient.is_server_running():
            client = SessionClient()
            client.shutdown()
            print("stopped")
        else:
            print("not running")
        return 0

    # All other commands need the server running
    if not SessionClient.is_server_running():
        print("error: server not running (use: mudprod start)")
        return 1

    client = SessionClient()

    if cmd == "status":
        r = client.status(session=rest[0] if rest else None)
        if "sessions" in r:
            for name, info in r["sessions"].items():
                print(f"{name}: {info['state']}")
        else:
            print(r.get("state", r))
        return 0

    if cmd == "connect":
        if len(rest) < 2:
            print("Usage: mudprod connect HOST PORT [LOGIN_STEPS_JSON] [SESSION]")
            return 1
        host = rest[0]
        port = int(rest[1])
        steps = json.loads(rest[2]) if len(rest) > 2 else []
        session = rest[3] if len(rest) > 3 else os.environ.get("MUDPROD_SESSION", "default")
        log_io(">>> CONNECT", f"{host}:{port} session={session}")
        r = client.connect(host, port, session=session, login_steps=steps)
        log_io("<<< CONNECT", r.get("state", str(r)))
        print(r.get("state", r.get("error", r)))
        return 0 if r.get("success") else 1

    if cmd == "send":
        text = " ".join(rest)
        session = os.environ.get("MUDPROD_SESSION", "default")
        log_io(">>> SEND", text)
        r = client.send(text, session=session)
        if r.get("success"):
            log_io("<<< RECV", r["clean"])
            print(r["clean"])
        else:
            log_io("<<< ERROR", r.get("error", "unknown"))
            print(f"error: {r.get('error')}")
            return 1
        return 0

    if cmd == "raw":
        text = " ".join(rest)
        session = os.environ.get("MUDPROD_SESSION", "default")
        log_io(">>> RAW", text)
        r = client.send_raw(text + "\n", session=session)
        print("sent" if r.get("success") else f"error: {r.get('error')}")
        return 0

    if cmd == "read":
        session = os.environ.get("MUDPROD_SESSION", "default")
        r = client.read(session=session)
        if r.get("success"):
            log_io("<<< READ", r["clean"])
            print(r["clean"])
        else:
            print(f"error: {r.get('error')}")
        return 0

    if cmd == "disconnect":
        session = rest[0] if rest else "default"
        r = client.disconnect(session=session)
        print(r.get("message", r.get("error", r)))
        return 0

    if cmd == "repeat":
        # repeat <command> - auto-send on balance recovery
        # repeat off - disable
        text = " ".join(rest) if rest else "off"
        session = os.environ.get("MUDPROD_SESSION", "default")
        r = client.repeat(text, session=session)
        print(r.get("message", r.get("error", r)))
        return 0 if r.get("success") else 1

    if cmd == "trigger":
        # trigger <pattern> <command> - add trigger
        # trigger clear - clear all
        session = os.environ.get("MUDPROD_SESSION", "default")
        if rest and rest[0] == "clear":
            r = client.trigger("", "", session=session, action="clear")
        elif len(rest) >= 2:
            pattern = rest[0]
            command = " ".join(rest[1:])
            r = client.trigger(pattern, command, session=session)
        else:
            print("Usage: trigger <pattern> <command>  OR  trigger clear")
            return 1
        print(r.get("message", r.get("error", r)))
        return 0 if r.get("success") else 1

    if cmd == "triggers":
        session = os.environ.get("MUDPROD_SESSION", "default")
        r = client.triggers(session=session)
        if r.get("success"):
            if r.get("repeat"):
                print(f"Repeat on balance: {r['repeat']}")
            for t in r.get("triggers", []):
                print(f"  '{t['pattern']}' -> '{t['command']}'")
            if not r.get("repeat") and not r.get("triggers"):
                print("No triggers set")
        else:
            print(f"error: {r.get('error')}")
        return 0

    print(f"Unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
