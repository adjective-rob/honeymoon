"""
HONEYMOON Hardening Ledger — Append-only signed security posture record.

Tracks simulation results over time. Each entry captures:
  - What was found (findings by severity)
  - What's new (findings not seen in previous run)
  - What was resolved (findings from previous run no longer present)
  - Security posture score (trending up or down)

Every entry is Ed25519 signed. The ledger is append-only.
Auditors can verify the entire hardening history with the public key.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from honeymoon.signing import HiveSigner


def _fingerprint(finding: dict) -> str:
    """Create a stable fingerprint for a finding to track across runs."""
    # Use title + severity as the identity — evidence changes but the issue is the same
    title = finding.get("title", "").strip().lower()
    severity = finding.get("severity", "info").lower()
    return f"{severity}::{title}"


def append_ledger(
    repo_path: Path,
    run_id: str,
    mission: str,
    findings: list[dict[str, Any]],
    verification: dict[str, Any] | None = None,
    budget: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a new entry to the hardening ledger. Returns the entry with diff stats."""
    ledger_path = repo_path / ".honeymoon" / "ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    # Load previous entries to compute diff
    previous_fingerprints: set[str] = set()
    previous_entry: dict[str, Any] | None = None
    if ledger_path.exists():
        lines = ledger_path.read_text().strip().splitlines()
        for line in lines:
            try:
                entry = json.loads(line)
                previous_fingerprints = set(entry.get("fingerprints", []))
                previous_entry = entry
            except json.JSONDecodeError:
                continue

    # Current fingerprints
    current_fingerprints = {_fingerprint(f) for f in findings}

    # Diff
    new_findings = current_fingerprints - previous_fingerprints
    resolved_findings = previous_fingerprints - current_fingerprints
    persistent_findings = current_fingerprints & previous_fingerprints

    # Severity counts
    sev_counts: dict[str, int] = {}
    for f in findings:
        s = f.get("severity", "info").lower()
        sev_counts[s] = sev_counts.get(s, 0) + 1

    # Posture score: 100 - weighted severity penalties
    # Critical=25, High=15, Medium=5, Low=1
    weights = {"critical": 25, "high": 15, "medium": 5, "low": 1, "info": 0}
    penalty = sum(weights.get(s, 0) * c for s, c in sev_counts.items())
    posture_score = max(0, 100 - penalty)

    # Trend
    prev_score = previous_entry.get("posture_score", 100) if previous_entry else 100
    if posture_score > prev_score:
        trend = "improving"
    elif posture_score < prev_score:
        trend = "degrading"
    else:
        trend = "stable"

    timestamp = datetime.now(timezone.utc).isoformat()

    entry: dict[str, Any] = {
        "timestamp": timestamp,
        "run_id": run_id,
        "mission": mission,
        "finding_count": len(findings),
        "severity_counts": sev_counts,
        "new_count": len(new_findings),
        "resolved_count": len(resolved_findings),
        "persistent_count": len(persistent_findings),
        "posture_score": posture_score,
        "trend": trend,
        "prev_score": prev_score,
        "fingerprints": sorted(current_fingerprints),
        "new_findings": sorted(new_findings),
        "resolved_findings": sorted(resolved_findings),
        "verification_verdict": verification.get("verdict") if verification else None,
        "cost": budget.get("estimated_cost", 0) if budget else 0,
        "total_runs": (previous_entry.get("total_runs", 0) if previous_entry else 0) + 1,
    }

    # Sign the entry
    signer = HiveSigner.load(repo_path)
    if signer:
        entry_json = json.dumps(entry, sort_keys=True)
        entry["signature"] = signer.sign(entry_json.encode("utf-8"))

    # Append to ledger
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    logger.info(
        f"[LEDGER] Entry #{entry['total_runs']}: "
        f"score={posture_score} ({trend}), "
        f"{len(new_findings)} new, {len(resolved_findings)} resolved"
    )

    return entry


def read_ledger(repo_path: Path) -> list[dict[str, Any]]:
    """Read all ledger entries."""
    ledger_path = repo_path / ".honeymoon" / "ledger.jsonl"
    if not ledger_path.exists():
        return []

    entries = []
    for line in ledger_path.read_text().strip().splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def posture_summary(repo_path: Path) -> str:
    """Human-readable posture summary from the ledger."""
    entries = read_ledger(repo_path)
    if not entries:
        return "No hardening history. Run: honeymoon harden --repo ."

    latest = entries[-1]
    total = latest.get("total_runs", len(entries))
    score = latest.get("posture_score", "?")
    trend = latest.get("trend", "?")
    trend_icon = {"improving": "\u2191", "degrading": "\u2193", "stable": "\u2192"}.get(trend, "?")

    lines = [
        f"Hardening runs: {total}",
        f"Posture score:  {score}/100 {trend_icon} {trend}",
        f"Active issues:  {latest.get('finding_count', 0)}",
    ]

    sev = latest.get("severity_counts", {})
    if sev:
        parts = []
        for s in ["critical", "high", "medium", "low"]:
            if sev.get(s):
                parts.append(f"{sev[s]} {s}")
        if parts:
            lines.append(f"Breakdown:      {', '.join(parts)}")

    if total > 1:
        first = entries[0]
        first_score = first.get("posture_score", 100)
        delta = score - first_score
        lines.append(f"Since first run: {'+' if delta >= 0 else ''}{delta} points")

    return "\n".join(lines)
