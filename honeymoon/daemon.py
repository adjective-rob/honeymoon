"""
HONEYMOON Daemon — WebSocket server for the live dashboard.

Streams pipeline events by tailing the audit log in real-time.
Also serves REST-like commands via WebSocket for triggering runs.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from loguru import logger

from honeymoon.ledger import read_ledger


class HoneymoonDaemon:
    """WebSocket + file-watching server that streams pipeline events to the dashboard."""

    def __init__(self, repo_path: Path, port: int = 4200):
        self.repo_path = repo_path.resolve()
        self.port = port
        self.ws_clients: set[Any] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running_command: str | None = None

    def _get_state(self) -> dict:
        """Current state snapshot for new WebSocket connections."""
        ledger = read_ledger(self.repo_path)
        latest = ledger[-1] if ledger else None

        reports_dir = self.repo_path / ".honeymoon" / "reports"
        report_count = len(list(reports_dir.glob("*.json"))) if reports_dir.exists() else 0

        return {
            "type": "state",
            "repo": str(self.repo_path),
            "repo_name": self.repo_path.name,
            "posture": latest.get("posture_score") if latest else None,
            "trend": latest.get("trend") if latest else None,
            "finding_count": latest.get("finding_count", 0) if latest else 0,
            "hardening_runs": len(ledger),
            "report_count": report_count,
            "ledger": ledger,
            "running": self._running_command,
        }

    def _get_reports(self) -> list[dict]:
        """All investigation reports."""
        reports_dir = self.repo_path / ".honeymoon" / "reports"
        reports = []
        if not reports_dir.exists():
            return reports

        for json_file in sorted(reports_dir.glob("*.json"), reverse=True):
            if json_file.stem.startswith("SPEC"):
                continue
            try:
                data = json.loads(json_file.read_text())
                reports.append({
                    "id": json_file.stem,
                    "run_id": data.get("run_id", ""),
                    "mission": data.get("mission", ""),
                    "objective": data.get("objective", ""),
                    "timestamp": data.get("timestamp", ""),
                    "finding_count": len(data.get("findings", {}).get("findings", [])),
                    "findings": data.get("findings", {}).get("findings", []),
                    "summary": data.get("findings", {}).get("summary", ""),
                    "verification": data.get("verification", {}),
                    "budget": data.get("budget", {}),
                    "signed": "signature" in data,
                })
            except Exception:
                pass
        return reports

    def _broadcast(self, data: dict) -> None:
        """Broadcast a message to all connected WebSocket clients."""
        if not self._loop or not self.ws_clients:
            return
        msg = json.dumps(data, default=str)
        for ws in list(self.ws_clients):
            try:
                asyncio.run_coroutine_threadsafe(ws.send(msg), self._loop)
            except Exception:
                self.ws_clients.discard(ws)

    async def _handle_ws(self, websocket: Any) -> None:
        """Handle a WebSocket connection."""
        self.ws_clients.add(websocket)
        logger.info(f"[DAEMON] Dashboard connected ({len(self.ws_clients)} clients)")

        try:
            state = self._get_state()
            await websocket.send(json.dumps(state, default=str))

            async for message in websocket:
                logger.debug(f"[DAEMON] Received: {message[:200]}")
                try:
                    cmd = json.loads(message)
                    await self._handle_command(cmd, websocket)
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.debug(f"[DAEMON] WebSocket error: {e}")
        finally:
            self.ws_clients.discard(websocket)
            logger.info(f"[DAEMON] Dashboard disconnected ({len(self.ws_clients)} clients)")

    async def _handle_command(self, cmd: dict, websocket: Any) -> None:
        """Handle a command from the dashboard."""
        action = cmd.get("action")

        if action == "get_state":
            await websocket.send(json.dumps(self._get_state(), default=str))

        elif action == "get_reports":
            await websocket.send(json.dumps({
                "type": "reports",
                "reports": self._get_reports(),
            }, default=str))

        elif action == "get_ledger":
            await websocket.send(json.dumps({
                "type": "ledger",
                "entries": read_ledger(self.repo_path),
            }, default=str))

        elif action in ("scan", "simulate", "harden", "deep"):
            if self._running_command:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": f"Already running: {self._running_command}",
                }))
                return

            self._running_command = action
            self._broadcast({"type": "command_started", "action": action})

            thread = threading.Thread(
                target=self._run_command,
                args=(action, cmd.get("options", {})),
                daemon=True,
            )
            thread.start()

    def _run_command(self, action: str, options: dict) -> None:
        """Run a honeymoon command in a background thread, streaming output."""
        honeymoon_bin = Path(sys.executable).parent / "honeymoon"
        if not honeymoon_bin.exists():
            cmd = [sys.executable, "-m", "honeymoon", action]
        else:
            cmd = [str(honeymoon_bin), action]

        cmd.extend(["--repo", str(self.repo_path), "--no-open", "--verbose"])

        if action == "simulate" and options.get("scenario"):
            cmd.extend(["--scenario", options["scenario"]])

        logger.info(f"[DAEMON] Executing: {' '.join(cmd)}")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.repo_path,
            )

            # Stream stdout lines as events
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()
                if not line:
                    continue

                # Parse structured info from verbose output
                event: dict[str, Any] = {"type": "output", "line": line}

                if "| DEBUG" in line or "| INFO" in line or "| WARNING" in line or "| ERROR" in line:
                    # Extract agent/module from loguru format
                    if "[ROUTER]" in line and "→" in line:
                        event["type"] = "agent_call"
                        parts = line.split("→")
                        if len(parts) >= 2:
                            event["agent"] = parts[0].split("[ROUTER]")[1].strip()
                            event["detail"] = parts[1].strip()
                    elif "[PATCH]" in line and "Tool call:" in line:
                        event["type"] = "tool_call"
                        event["tool"] = line.split("Tool call:")[1].strip()
                    elif "[FRANKIE]" in line and "Tool call:" in line:
                        event["type"] = "tool_call"
                        event["agent"] = "security"
                        event["tool"] = line.split("Tool call:")[1].strip()
                    elif "[QUEEN]" in line:
                        event["type"] = "planner"
                        event["agent"] = "planner"
                    elif "[EVENT]" in line:
                        event["type"] = "pipeline_event"
                        # Extract event type
                        if ":" in line.split("[EVENT]")[1]:
                            event["event_name"] = line.split("[EVENT]")[1].split(":")[0].strip()
                    elif "Plan ready" in line:
                        event["type"] = "plan_ready"
                    elif "Investigation complete" in line or "Simulation complete" in line or "Scan complete" in line:
                        event["type"] = "complete"
                    elif "LEDGER" in line:
                        event["type"] = "ledger_update"

                self._broadcast(event)

            proc.wait()

            self._broadcast({
                "type": "command_completed",
                "action": action,
                "returncode": proc.returncode,
            })

            # Send refreshed state
            self._broadcast(self._get_state())

        except Exception as e:
            logger.error(f"[DAEMON] Command {action} failed: {e}")
            self._broadcast({
                "type": "command_error",
                "action": action,
                "error": str(e),
            })
        finally:
            self._running_command = None

    def _start_http_server(self) -> None:
        """Start an HTTP server for serving reports and API endpoints."""
        from http.server import HTTPServer, BaseHTTPRequestHandler

        repo = self.repo_path

        class ReportHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/api/report/"):
                    report_id = self.path.split("/api/report/")[1].rstrip("/")
                    html_file = repo / ".honeymoon" / "reports" / f"{report_id}.html"
                    if html_file.exists():
                        content = html_file.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(content)))
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(content)
                    else:
                        self.send_response(404)
                        self.end_headers()
                        self.wfile.write(b"Report not found")
                elif self.path == "/api/reports":
                    reports_json = json.dumps(self._get_reports()).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(reports_json)
                else:
                    self.send_response(404)
                    self.end_headers()

            def _get_reports(self):
                reports_dir = repo / ".honeymoon" / "reports"
                result = []
                if not reports_dir.exists():
                    return result
                for f in sorted(reports_dir.glob("*.json"), reverse=True):
                    if f.stem.startswith("SPEC"):
                        continue
                    try:
                        json.loads(f.read_text())  # validate JSON
                        result.append({"id": f.stem, "has_html": (reports_dir / f"{f.stem}.html").exists()})
                    except Exception:
                        pass
                return result

            def log_message(self, format, *args):
                pass  # Suppress HTTP logs

        http_port = self.port + 1
        server = HTTPServer(("127.0.0.1", http_port), ReportHandler)
        logger.info(f"[DAEMON] HTTP server on http://127.0.0.1:{http_port}")
        server.serve_forever()

    def run(self) -> None:
        """Start the WebSocket + HTTP servers."""
        try:
            import websockets
        except ImportError:
            print("Install websockets: pip install websockets")
            return

        # Start HTTP server in background thread for serving reports
        http_thread = threading.Thread(target=self._start_http_server, daemon=True)
        http_thread.start()

        async def serve():
            self._loop = asyncio.get_event_loop()
            async with websockets.serve(self._handle_ws, "127.0.0.1", self.port):
                logger.info(f"[DAEMON] WebSocket server on ws://127.0.0.1:{self.port}")
                print("\n\U0001f36f HONEYMOON Dashboard Daemon")
                print(f"   Repo:      {self.repo_path}")
                print(f"   WebSocket: ws://127.0.0.1:{self.port}")
                print(f"   Reports:   http://127.0.0.1:{self.port + 1}")
                print("   Dashboard: cd dashboard && pnpm dev")
                print("   Press Ctrl+C to stop.\n")
                await asyncio.Future()

        try:
            asyncio.run(serve())
        except KeyboardInterrupt:
            print("\nShutting down.")
