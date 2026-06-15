"""One-click launcher: starts the MCP server, waits for it, then runs the web app.

    python run.py

Stops the MCP child process on exit. Requires Intiface Central and LM Studio to
be running separately.
"""
from __future__ import annotations

import atexit
import signal
import socket
import subprocess
import sys
import time

import config

HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
PY = sys.executable


def wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.3)
    return False


def main() -> None:
    print(f"[run] starting MCP server on {config.MCP_HOST}:{config.MCP_PORT} …")
    mcp_proc = subprocess.Popen([PY, "mcp_server.py"], cwd=HERE)

    def cleanup(*_a):
        if mcp_proc.poll() is None:
            mcp_proc.terminate()
            try:
                mcp_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                mcp_proc.kill()

    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda *a: (cleanup(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *a: (cleanup(), sys.exit(0)))

    if not wait_for_port(config.MCP_HOST, config.MCP_PORT):
        print("[run] MCP server did not start in time; check Intiface/logs.")
        cleanup()
        sys.exit(1)
    print("[run] MCP server is up.")

    import uvicorn
    from app import app

    print(f"[run] open  http://{config.APP_HOST}:{config.APP_PORT}")
    uvicorn.run(app, host=config.APP_HOST, port=config.APP_PORT)


if __name__ == "__main__":
    main()
