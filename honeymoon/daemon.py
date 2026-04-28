"""
HONEYMOON Daemon — WebSocket server for the live dashboard.

Bridges the EventBus to connected browsers in real-time.
Also serves REST endpoints for triggering commands and reading state.

Usage:
    honeymoon serve --repo ~/my-project --port 4200
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from honeymoon.event_bus import bus
from honeymoon.ledger import read_ledger, posture_summary


class HoneymoonDaemon:
    """WebSocket + REST server that streams pipeline events to the dashboard."""

    def __init__(self, repo_path: Path, port: int = 4200):
        self.repo_path = repo_path.resolve()
        self.port = port
        self.ws_clients: set[Any] = set()
        self._event_buffer: list[dict] = []

        # Subscribe to the global EventBus
        bus.subscribe(self._on_event)

    def _on_event(self, event: Any) -> None:
        """Called by EventBus for every event. Buffer + broadcast."""
        try:
            if hasattr(event, "model_dump"):
                data = event.model_dump()
            elif hasattr(event, "__dict__"):
                data = {k: v for k, v in event.__dict__.items() if not k.startswith("_")}
            else:
                data = {"raw": str(event)}

            data["_daemon_ts"] = datetime.now(timezone.utc).isoformat()
            self._event_buffer.append(data)

            # Broadcast to connected WebSocket clients
            for ws in list(self.ws_clients):
                try:
                    asyncio.run_coroutine_threadsafe(
                        ws.send(json.dumps(data, default=str)),
                        self._loop
                    )
                except Exception:
                    self.ws_clients.discard(ws)
        except Exception as e:
            logger.debug(f"[DAEMON] Event broadcast error: {e}")

    def _get_state(self) -> dict:
        """Current state snapshot for new WebSocket connections."""
        ledger = read_ledger(self.repo_path)
        latest = ledger[-1] if ledger else None

        # Count reports
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
            "event_buffer": self._event_buffer[-100:],  # Last 100 events
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

    async def _handle_ws(self, websocket: Any) -> None:
        """Handle a WebSocket connection."""
        self.ws_clients.add(websocket)
        logger.info(f"[DAEMON] Dashboard connected ({len(self.ws_clients)} clients)")

        try:
            # Send initial state
            await websocket.send(json.dumps(self._get_state(), default=str))

            # Listen for commands from the dashboard
            async for message in websocket:
                try:
                    cmd = json.loads(message)
                    await self._handle_command(cmd, websocket)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
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

        elif action == "get_posture":
            await websocket.send(json.dumps({
                "type": "posture",
                "summary": posture_summary(self.repo_path),
            }, default=str))

        elif action in ("scan", "simulate", "harden", "deep"):
            # Run command in a background thread
            await websocket.send(json.dumps({
                "type": "command_started",
                "action": action,
            }))
            thread = threading.Thread(
                target=self._run_command,
                args=(action, cmd.get("options", {})),
                daemon=True,
            )
            thread.start()

    def _run_command(self, action: str, options: dict) -> None:
        """Run a honeymoon command in a background thread."""
        import subprocess
        import sys
        # Use the same Python/venv that's running the daemon
        honeymoon_bin = Path(sys.executable).parent / "honeymoon"
        if not honeymoon_bin.exists():
            honeymoon_bin = Path(sys.executable).parent / "python"
            cmd = [str(honeymoon_bin), "-m", "honeymoon", action]
        else:
            cmd = [str(honeymoon_bin), action]
        cmd.extend([
            "--repo", str(self.repo_path),
            "--no-open",
            "--verbose",
        ])
        if action == "simulate" and options.get("scenario"):
            cmd.extend(["--scenario", options["scenario"]])

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                cwd=self.repo_path,
            )
            # Broadcast completion
            for ws in list(self.ws_clients):
                try:
                    asyncio.run_coroutine_threadsafe(
                        ws.send(json.dumps({
                            "type": "command_completed",
                            "action": action,
                            "returncode": proc.returncode,
                            "stdout": proc.stdout[-2000:] if proc.stdout else "",
                            "stderr": proc.stderr[-1000:] if proc.stderr else "",
                        })),
                        self._loop
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[DAEMON] Command {action} failed: {e}")

    def run(self) -> None:
        """Start the WebSocket server."""
        try:
            import websockets
        except ImportError:
            print("Install websockets: pip install websockets")
            return

        async def serve():
            self._loop = asyncio.get_event_loop()
            async with websockets.serve(self._handle_ws, "127.0.0.1", self.port):
                logger.info(f"[DAEMON] WebSocket server on ws://127.0.0.1:{self.port}")
                print("\n🍯 HONEYMOON Dashboard Daemon")
                print(f"   Repo:      {self.repo_path}")
                print(f"   WebSocket: ws://127.0.0.1:{self.port}")
                print("   Dashboard: cd dashboard && pnpm dev")
                print("   Press Ctrl+C to stop.\n")
                await asyncio.Future()  # Run forever

        try:
            asyncio.run(serve())
        except KeyboardInterrupt:
            print("\nShutting down.")
