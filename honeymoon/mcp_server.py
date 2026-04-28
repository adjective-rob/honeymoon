"""
HONEYMOON MCP Server — Expose security intelligence as MCP tools.

Tools that run pipelines (scan, simulate, harden, deep) invoke honeymoon
via subprocess, same pattern as daemon.py.  Tools that read state
(posture, get_report, get_ledger, audit) call Python functions directly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("honeymoon")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _honeymoon_cmd() -> list[str]:
    """Return the base command to invoke the honeymoon CLI."""
    honeymoon_bin = Path(sys.executable).parent / "honeymoon"
    if honeymoon_bin.exists():
        return [str(honeymoon_bin)]
    return [sys.executable, "-m", "honeymoon"]


def _run_pipeline(action: str, repo_path: str, extra_args: list[str] | None = None) -> dict:
    """Run a honeymoon pipeline command and capture structured output."""
    repo = Path(repo_path).resolve()
    if not repo.exists():
        return {"error": f"Repository not found: {repo}"}

    cmd = _honeymoon_cmd() + [action, "--repo", str(repo), "--no-open", "--verbose"]
    if extra_args:
        cmd.extend(extra_args)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo,
            timeout=600,
        )

        # Parse the report if one was written
        reports_dir = repo / ".honeymoon" / "reports"
        report = _get_latest_report(reports_dir)

        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "report": report,
            "stdout_tail": _tail(proc.stdout, 40),
            "stderr_tail": _tail(proc.stderr, 10) if proc.returncode != 0 else None,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out after 600 seconds"}
    except Exception as e:
        return {"error": str(e)}


def _get_latest_report(reports_dir: Path) -> dict | None:
    """Read the most recent JSON report from the reports directory."""
    if not reports_dir.exists():
        return None

    json_files = sorted(
        (f for f in reports_dir.glob("*.json") if not f.stem.startswith("SPEC")),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not json_files:
        return None

    try:
        data = json.loads(json_files[0].read_text())
        return {
            "id": json_files[0].stem,
            "run_id": data.get("run_id", ""),
            "mission": data.get("mission", ""),
            "objective": data.get("objective", ""),
            "timestamp": data.get("timestamp", ""),
            "finding_count": len(data.get("findings", {}).get("findings", [])),
            "findings": data.get("findings", {}).get("findings", []),
            "summary": data.get("findings", {}).get("summary", ""),
            "verification": data.get("verification", {}),
            "budget": data.get("budget", {}),
        }
    except Exception:
        return None


def _tail(text: str, n: int) -> str:
    """Return the last n lines of text."""
    lines = text.strip().splitlines()
    return "\n".join(lines[-n:]) if lines else ""


# ---------------------------------------------------------------------------
# Pipeline tools (subprocess)
# ---------------------------------------------------------------------------

@mcp.tool()
def honeymoon_scan(repo_path: str, objective: str = "") -> dict[str, Any]:
    """Quick security investigation of a repository.

    Runs the honeymoon investigate pipeline against the target repo.
    Auto-detects an investigation objective if none is provided.

    Args:
        repo_path: Absolute path to the repository to scan.
        objective: What to investigate (auto-detected if omitted).

    Returns:
        Structured findings with severity, evidence, and analysis.
    """
    extra: list[str] = []
    if objective:
        extra.extend(["--objective", objective])
    return _run_pipeline("scan", repo_path, extra)


@mcp.tool()
def honeymoon_simulate(repo_path: str, scenario: str = "") -> dict[str, Any]:
    """Red/Blue adversarial attack simulation.

    Traces exploitation chains against the target repository and returns
    attack chains with exploitability ratings and blue-team verification.

    Args:
        repo_path: Absolute path to the repository to simulate against.
        scenario: Attack scenario to simulate (auto-detected if omitted).

    Returns:
        Attack chains with exploitability ratings and blue-team verdict.
    """
    extra: list[str] = []
    if scenario:
        extra.extend(["--scenario", scenario])
    return _run_pipeline("simulate", repo_path, extra)


@mcp.tool()
def honeymoon_harden(repo_path: str) -> dict[str, Any]:
    """Run adversarial hardening and return a posture diff.

    Simulates attacks, records findings in the signed ledger, and computes
    the delta against the previous hardening run.

    Args:
        repo_path: Absolute path to the repository to harden.

    Returns:
        Posture score, trend, new findings, and resolved findings.
    """
    result = _run_pipeline("harden", repo_path)

    # Enrich with ledger data
    repo = Path(repo_path).resolve()
    from honeymoon.ledger import read_ledger
    entries = read_ledger(repo)
    if entries:
        latest = entries[-1]
        result["posture"] = {
            "score": latest.get("posture_score"),
            "trend": latest.get("trend"),
            "new_count": latest.get("new_count", 0),
            "resolved_count": latest.get("resolved_count", 0),
            "finding_count": latest.get("finding_count", 0),
            "severity_counts": latest.get("severity_counts", {}),
            "run_number": latest.get("total_runs", len(entries)),
        }

    return result


@mcp.tool()
def honeymoon_deep(repo_path: str) -> dict[str, Any]:
    """Full deep scan: audit + parallel investigation + SPEC remediation plan.

    Runs static analysis, then launches parallel investigation lanes, merges
    findings, and generates a remediation SPEC.

    Args:
        repo_path: Absolute path to the repository to deep-scan.

    Returns:
        Merged findings, SPEC path, and static finding count.
    """
    result = _run_pipeline("deep", repo_path)

    # Check for SPEC file
    repo = Path(repo_path).resolve()
    reports_dir = repo / ".honeymoon" / "reports"
    if reports_dir.exists():
        specs = list(reports_dir.glob("SPEC*.md"))
        if specs:
            latest_spec = max(specs, key=lambda f: f.stat().st_mtime)
            result["spec_path"] = str(latest_spec)

    # Add static audit count
    from honeymoon.auditor import Scanner
    scanner = Scanner(repo)
    scan_result = scanner.scan()
    result["static_finding_count"] = len(scan_result.findings)

    return result


# ---------------------------------------------------------------------------
# Read-only tools (direct Python calls — fast, no LLM)
# ---------------------------------------------------------------------------

@mcp.tool()
def honeymoon_posture(repo_path: str) -> dict[str, Any]:
    """Get current security posture score without running a new scan.

    Reads the hardening ledger to show the current posture score, trend,
    active issue count, and total run count.

    Args:
        repo_path: Absolute path to the repository.

    Returns:
        Posture score, trend, active issues, and run count.
    """
    repo = Path(repo_path).resolve()
    if not repo.exists():
        return {"error": f"Repository not found: {repo}"}

    from honeymoon.ledger import read_ledger, posture_summary

    entries = read_ledger(repo)
    if not entries:
        return {
            "posture_score": None,
            "trend": None,
            "active_issues": 0,
            "run_count": 0,
            "message": "No hardening history. Run honeymoon_harden first.",
        }

    latest = entries[-1]
    return {
        "posture_score": latest.get("posture_score"),
        "trend": latest.get("trend"),
        "active_issues": latest.get("finding_count", 0),
        "severity_counts": latest.get("severity_counts", {}),
        "run_count": latest.get("total_runs", len(entries)),
        "prev_score": latest.get("prev_score"),
        "new_count": latest.get("new_count", 0),
        "resolved_count": latest.get("resolved_count", 0),
        "summary": posture_summary(repo),
    }


@mcp.tool()
def honeymoon_audit(repo_path: str) -> dict[str, Any]:
    """Static analysis only — fast, free, no LLM calls.

    Scans the repository using tree-sitter and regex patterns for TODOs,
    missing docs, complex functions, hardcoded secrets, large files, and
    dependency vulnerabilities.

    Args:
        repo_path: Absolute path to the repository to audit.

    Returns:
        Finding count by kind and severity breakdown.
    """
    repo = Path(repo_path).resolve()
    if not repo.exists():
        return {"error": f"Repository not found: {repo}"}

    from honeymoon.auditor import Scanner

    scanner = Scanner(repo)
    result = scanner.scan()
    summary = result.summary()

    # Severity breakdown
    severity_counts: dict[str, int] = {}
    for f in result.findings:
        severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

    # Sample findings per kind (up to 3 each)
    samples: dict[str, list[dict]] = {}
    for f in result.findings:
        if f.kind not in samples:
            samples[f.kind] = []
        if len(samples[f.kind]) < 3:
            samples[f.kind].append({
                "file": f.file,
                "line": f.line,
                "symbol": f.symbol,
                "description": f.description,
                "severity": f.severity,
            })

    return {
        "files_scanned": summary["files_scanned"],
        "total_findings": summary["total"],
        "by_kind": summary["by_kind"],
        "severity_counts": severity_counts,
        "samples": samples,
    }


@mcp.tool()
def honeymoon_get_report(repo_path: str, report_id: str = "") -> dict[str, Any]:
    """Get a specific investigation report, or the latest if no ID given.

    Args:
        repo_path: Absolute path to the repository.
        report_id: Report ID (filename stem). Defaults to latest report.

    Returns:
        Full report contents including findings, verification, and budget.
    """
    repo = Path(repo_path).resolve()
    if not repo.exists():
        return {"error": f"Repository not found: {repo}"}

    reports_dir = repo / ".honeymoon" / "reports"
    if not reports_dir.exists():
        return {"error": "No reports directory found. Run a scan first."}

    if report_id:
        report_file = reports_dir / f"{report_id}.json"
        if not report_file.exists():
            # List available reports
            available = [
                f.stem for f in sorted(reports_dir.glob("*.json"), reverse=True)
                if not f.stem.startswith("SPEC")
            ]
            return {
                "error": f"Report '{report_id}' not found.",
                "available_reports": available[:20],
            }
    else:
        # Get latest
        json_files = sorted(
            (f for f in reports_dir.glob("*.json") if not f.stem.startswith("SPEC")),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not json_files:
            return {"error": "No reports found."}
        report_file = json_files[0]

    try:
        data = json.loads(report_file.read_text())
        return {
            "id": report_file.stem,
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
        }
    except Exception as e:
        return {"error": f"Failed to read report: {e}"}


@mcp.tool()
def honeymoon_get_ledger(repo_path: str) -> dict[str, Any]:
    """Get the full hardening ledger — all entries with posture scores over time.

    Args:
        repo_path: Absolute path to the repository.

    Returns:
        All ledger entries with posture scores, trends, and finding diffs.
    """
    repo = Path(repo_path).resolve()
    if not repo.exists():
        return {"error": f"Repository not found: {repo}"}

    from honeymoon.ledger import read_ledger, posture_summary

    entries = read_ledger(repo)
    if not entries:
        return {
            "entry_count": 0,
            "entries": [],
            "message": "No hardening history.",
        }

    # Summarize each entry (strip bulky fingerprint lists)
    summarized = []
    for e in entries:
        summarized.append({
            "timestamp": e.get("timestamp"),
            "run_id": e.get("run_id"),
            "mission": e.get("mission"),
            "posture_score": e.get("posture_score"),
            "trend": e.get("trend"),
            "finding_count": e.get("finding_count"),
            "severity_counts": e.get("severity_counts"),
            "new_count": e.get("new_count"),
            "resolved_count": e.get("resolved_count"),
            "total_runs": e.get("total_runs"),
            "cost": e.get("cost"),
        })

    return {
        "entry_count": len(entries),
        "entries": summarized,
        "summary": posture_summary(repo),
    }


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------

def run_server() -> None:
    """Start the MCP server on stdio transport."""
    mcp.run(transport="stdio")
