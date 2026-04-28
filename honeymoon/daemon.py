"""
HONEYMOON Daemon — WebSocket server for the live dashboard.

Streams pipeline events by tailing the audit log in real-time.
Also serves REST-like commands via WebSocket for triggering runs.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import yaml

from loguru import logger

from honeymoon.ledger import read_ledger
from honeymoon.signing import HiveSigner, HiveVerifier, SIGNING_AVAILABLE


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

    def _get_trust(self) -> dict:
        """Trust and signing status for the dashboard."""
        signer = HiveSigner.load(self.repo_path) if SIGNING_AVAILABLE else None
        pub_key = signer.public_key_hex if signer else None
        key_path = self.repo_path / ".honeymoon" / "keys" / "verify.pub"

        # Count signed vs unsigned events in audit log
        audit_log = self.repo_path / ".honeymoon" / "logs" / "audit.jsonl"
        signed_events = 0
        unsigned_events = 0
        if audit_log.exists():
            try:
                for line in audit_log.read_text().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("signature"):
                            signed_events += 1
                        else:
                            unsigned_events += 1
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass

        # Count signed reports
        reports_dir = self.repo_path / ".honeymoon" / "reports"
        signed_reports = 0
        total_reports = 0
        latest_signature = None
        if reports_dir.exists():
            for json_file in sorted(reports_dir.glob("*.json")):
                if json_file.stem.startswith("SPEC"):
                    continue
                try:
                    data = json.loads(json_file.read_text())
                    total_reports += 1
                    sig = data.get("signature")
                    if sig:
                        signed_reports += 1
                        latest_signature = sig
                except Exception:
                    pass

        return {
            "type": "trust",
            "signing_available": signer is not None,
            "public_key": pub_key,
            "public_key_short": f"{pub_key[:4]}...{pub_key[-4:]}" if pub_key and len(pub_key) >= 8 else pub_key,
            "key_algorithm": "Ed25519" if signer else None,
            "key_path": str(key_path) if key_path.exists() else None,
            "zephyr_available": shutil.which("zephyr") is not None,
            "signed_events": signed_events,
            "unsigned_events": unsigned_events,
            "signed_reports": signed_reports,
            "latest_signature": latest_signature[:16] + "..." if latest_signature and len(latest_signature) > 16 else latest_signature,
        }

    def _verify_report(self, report_id: str) -> dict:
        """Verify the cryptographic signature on a report."""
        reports_dir = self.repo_path / ".honeymoon" / "reports"
        json_path = reports_dir / f"{report_id}.json"
        md_path = reports_dir / f"{report_id}.md"

        if not json_path.exists():
            return {"type": "verification", "report_id": report_id, "valid": False, "error": "Report not found"}

        try:
            report_data = json.loads(json_path.read_text())
            signature = report_data.get("signature")
            if not signature:
                return {"type": "verification", "report_id": report_id, "valid": False, "error": "Report is not signed"}

            # Try to get the report body from the markdown file
            if md_path.exists():
                md_content = md_path.read_text()
                # Split on the attestation separator
                parts = md_content.split("\n---\n")
                report_body = parts[0] if parts else md_content
            else:
                # Fall back to the JSON body (everything except the signature field)
                body = {k: v for k, v in report_data.items() if k != "signature"}
                report_body = json.dumps(body, sort_keys=True, default=str)

            signer = HiveSigner.load(self.repo_path)
            if not signer:
                # Try with just the public key
                pub_path = self.repo_path / ".honeymoon" / "keys" / "verify.pub"
                verifier = HiveVerifier.from_file(pub_path)
                if not verifier:
                    return {"type": "verification", "report_id": report_id, "valid": False, "error": "No keys available"}
                valid = verifier.verify(report_body.encode(), signature)
                pub_key = pub_path.read_text().strip() if pub_path.exists() else None
            else:
                valid = signer.verify(report_body.encode(), signature)
                pub_key = signer.public_key_hex

            return {
                "type": "verification",
                "report_id": report_id,
                "valid": valid,
                "public_key": f"{pub_key[:4]}...{pub_key[-4:]}" if pub_key and len(pub_key) >= 8 else pub_key,
            }
        except Exception as e:
            return {"type": "verification", "report_id": report_id, "valid": False, "error": str(e)}

    def _create_fix_task(self, opts: dict) -> Path:
        """Write a remediation task YAML from a finding."""
        title = opts.get("title", "unknown")
        severity = opts.get("severity", "medium")
        evidence = opts.get("evidence", "")
        analysis = opts.get("analysis", "")

        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
        task_id = f"fix-{severity}-{slug}"

        task_data = {
            "id": task_id,
            "objective": f"Fix: {title}",
            "constraints": [
                "Do not break existing functionality",
                "Run tests after changes",
                f"Evidence: {evidence[:300]}",
                f"Analysis: {analysis[:300]}",
            ],
            "acceptance": [
                "The security finding is addressed",
                "All existing tests still pass",
            ],
            "risk": "medium",
        }

        queue_dir = self.repo_path / ".honeymoon" / "tasks" / "queue"
        queue_dir.mkdir(parents=True, exist_ok=True)
        task_path = queue_dir / f"{task_id}.yaml"
        task_path.write_text(yaml.dump(task_data, default_flow_style=False, sort_keys=False))
        logger.info(f"[DAEMON] Fix task created: {task_path}")
        return task_path

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

        elif action == "get_trust":
            await websocket.send(json.dumps(self._get_trust(), default=str))

        elif action == "verify_report":
            report_id = cmd.get("options", {}).get("report_id", "")
            await websocket.send(json.dumps(self._verify_report(report_id), default=str))

        elif action == "fix_finding":
            opts = cmd.get("options", {})
            task_path = self._create_fix_task(opts)
            await websocket.send(json.dumps({"type": "fix_created", "path": str(task_path)}))

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
