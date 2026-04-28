#!/usr/bin/env python3
"""
HONEYMOON Dashboard Server

Serves the attestation dashboard and auto-loads audit.jsonl from the repo's
.honeymoon/logs/ directory. No drag-and-drop needed.

Usage:
    python3 honeymoon/reporting/serve.py --repo ~/Desktop/honeymoon
    # Opens http://localhost:8080
"""

import argparse
import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serves dashboard files + injects audit.jsonl and reports as API endpoints."""

    repo_path: Path = Path(".")
    dashboard_dir: Path = Path(".")

    def do_GET(self):
        if self.path == "/api/audit":
            self.serve_audit()
        elif self.path == "/api/reports":
            self.serve_reports()
        elif self.path.startswith("/api/report/"):
            self.serve_single_report(self.path.split("/api/report/")[1])
        elif self.path == "/" or self.path == "/index.html":
            self.serve_dashboard()
        else:
            # Serve static files from dashboard dir
            os.chdir(self.dashboard_dir)
            super().do_GET()

    def serve_audit(self):
        audit_file = self.repo_path / ".honeymoon" / "logs" / "audit.jsonl"
        if not audit_file.exists():
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"error": "audit.jsonl not found"}')
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(audit_file.read_bytes())

    def serve_reports(self):
        """Return list of all investigation reports as JSON."""
        reports_dir = self.repo_path / ".honeymoon" / "reports"
        reports = []
        if reports_dir.exists():
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

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(reports).encode())

    def serve_single_report(self, report_id: str):
        """Serve an HTML report file directly."""
        html_file = self.repo_path / ".honeymoon" / "reports" / f"{report_id}.html"
        if html_file.exists():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html_file.read_bytes())
        else:
            self.send_response(404)
            self.end_headers()

    def serve_dashboard(self):
        dashboard_file = self.dashboard_dir / "index.html"
        if not dashboard_file.exists():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Dashboard not found")
            return

        content = dashboard_file.read_text()

        # Inject auto-load script that fetches from /api/audit on page load
        inject = """
<script>
window.addEventListener('load', async () => {
    try {
        const resp = await fetch('/api/audit');
        if (resp.ok) {
            const text = await resp.text();
            const lines = [];
            let buffer = '';
            let depth = 0;
            for (const ch of text) {
                buffer += ch;
                if (ch === '{') depth++;
                if (ch === '}') depth--;
                if (depth === 0 && buffer.trim()) {
                    lines.push(buffer.trim());
                    buffer = '';
                }
            }
            if (buffer.trim()) lines.push(buffer.trim());
            if (lines.length > 0 && window.__setAuditData) {
                window.__setAuditData(lines);
            }
        }
    } catch(e) { console.log('No audit data available:', e); }
});
</script>
"""
        # Inject the auto-load script and a hook in the React app
        content = content.replace(
            "const [rawLines,setRawLines]=useState(null);",
            "const [rawLines,setRawLines]=useState(null);\n"
            "  React.useEffect(()=>{ window.__setAuditData = setRawLines; "
            "return ()=>{ delete window.__setAuditData; }; },[]);"
        )
        content = content.replace("</body>", inject + "</body>")

        encoded = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main():
    parser = argparse.ArgumentParser(description="HONEYMOON Dashboard Server")
    parser.add_argument("--repo", type=str, default=".", help="Path to the HONEYMOON repository")
    parser.add_argument("--port", type=int, default=8080, help="Port to serve on")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    dashboard_dir = Path(__file__).parent.resolve()

    DashboardHandler.repo_path = repo_path
    DashboardHandler.dashboard_dir = dashboard_dir

    audit_file = repo_path / ".honeymoon" / "logs" / "audit.jsonl"
    print("⚡ HONEYMOON Attestation Dashboard")
    print(f"   Repo:      {repo_path}")
    print(f"   Audit log: {audit_file} ({'found' if audit_file.exists() else 'not found'})")
    print(f"   Dashboard: http://localhost:{args.port}")
    print("   Refresh the browser to reload latest audit data.\n")

    server = HTTPServer(("0.0.0.0", args.port), DashboardHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()