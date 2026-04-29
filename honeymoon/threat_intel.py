"""
HONEYMOON Threat Intelligence — Cross-repo attack pattern sharing.

Maintains a global JSONL database at ~/.honeymoon/threat_intel.jsonl.
Findings from any repo are normalized into ThreatPattern records,
deduplicated by a deterministic hash, and queryable for cross-repo learning.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

THREAT_INTEL_PATH = Path.home() / ".honeymoon" / "threat_intel.jsonl"

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# Keyword-based classification for attack surface
_SURFACE_RULES: list[tuple[list[str], str]] = [
    (["subprocess", "shell", "command", "exec"], "shell_execution"),
    (["auth", "credential", "token", "bypass"], "authentication"),
    (["serializ", "json", "persist", "inject"], "serialization"),
    (["file", "path", "traversal", "read", "write"], "file_access"),
    (["url", "href", "src", "xss", "innerhtml"], "web_rendering"),
    (["network", "fetch", "api", "endpoint"], "network"),
]


@dataclass
class ThreatPattern:
    """Normalized threat pattern for cross-repo intelligence sharing."""

    pattern_id: str
    attack_surface: str
    technique: str
    entry_point: str
    impact: str
    exploitability: str
    severity: str
    description: str
    evidence_sample: str

    # Cross-repo tracking
    repos_seen: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    times_seen: int = 1
    resolved_count: int = 0

    # Provenance
    signed_by: str | None = None


def pattern_id_from(attack_surface: str, technique: str, entry_point: str) -> str:
    """Deterministic hash for dedup from the triple that defines a pattern."""
    key = f"{attack_surface}|{technique}|{entry_point}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _classify_attack_surface(text: str) -> str:
    """Classify attack surface from finding text using keyword heuristics."""
    lower = text.lower()
    for keywords, surface in _SURFACE_RULES:
        if any(kw in lower for kw in keywords):
            return surface
    return "other"


def _extract_technique(title: str) -> str:
    """Extract a slug technique name from a finding title."""
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug[:50]


def _extract_impact(finding: dict[str, Any]) -> str:
    """Derive impact string from finding analysis or severity."""
    analysis = finding.get("analysis", "") or ""
    title = finding.get("title", "") or ""
    combined = (analysis + " " + title).lower()

    if any(w in combined for w in ["command execution", "rce", "code execution", "shell"]):
        return "arbitrary_command_execution"
    if any(w in combined for w in ["exfiltrat", "data leak", "sensitive data"]):
        return "data_exfiltration"
    if any(w in combined for w in ["auth bypass", "authentication", "privilege"]):
        return "auth_bypass"
    if any(w in combined for w in ["denial", "dos", "crash", "hang"]):
        return "denial_of_service"
    if any(w in combined for w in ["traversal", "arbitrary file", "path"]):
        return "arbitrary_file_access"
    return "security_weakness"


def _extract_entry_point(finding: dict[str, Any]) -> str:
    """Build an entry_point string from finding evidence and file references."""
    evidence = finding.get("evidence", "") or ""
    file_ref = finding.get("file", "") or ""
    title = finding.get("title", "") or ""

    parts = []
    if file_ref:
        parts.append(file_ref)
    if evidence:
        # Take first line as the entry point trace
        first_line = evidence.strip().split("\n")[0][:120]
        parts.append(first_line)
    if not parts:
        parts.append(title[:120])
    return " -> ".join(parts)


def _map_exploitability(finding: dict[str, Any]) -> str:
    """Map finding confidence/exploitability to our scale."""
    confidence = (finding.get("confidence", "") or "").lower()
    if confidence == "high":
        return "trivial"
    if confidence == "medium":
        return "moderate"
    return "difficult"


def extract_patterns(
    findings: list[dict[str, Any]],
    repo_name: str,
    signer_key: str | None = None,
) -> list[ThreatPattern]:
    """Convert investigation findings into normalized threat patterns.

    Uses heuristics to classify attack_surface and technique from each
    finding's title and analysis text.
    """
    now = datetime.now(timezone.utc).isoformat()
    patterns: list[ThreatPattern] = []

    for finding in findings:
        title = finding.get("title", "") or ""
        analysis = finding.get("analysis", "") or ""
        evidence = finding.get("evidence", "") or ""
        severity = (finding.get("severity", "low") or "low").lower()
        combined_text = f"{title} {analysis} {evidence}"

        attack_surface = _classify_attack_surface(combined_text)
        technique = _extract_technique(title)
        entry_point = _extract_entry_point(finding)
        pid = pattern_id_from(attack_surface, technique, entry_point)

        pattern = ThreatPattern(
            pattern_id=pid,
            attack_surface=attack_surface,
            technique=technique,
            entry_point=entry_point,
            impact=_extract_impact(finding),
            exploitability=_map_exploitability(finding),
            severity=severity,
            description=f"{title}. {analysis[:200]}" if analysis else title,
            evidence_sample=evidence[:300],
            repos_seen=[repo_name],
            first_seen=now,
            last_seen=now,
            times_seen=1,
            resolved_count=0,
            signed_by=signer_key,
        )
        patterns.append(pattern)

    return patterns


def _load_db() -> dict[str, ThreatPattern]:
    """Load the JSONL database into a dict keyed by pattern_id."""
    db: dict[str, ThreatPattern] = {}
    if not THREAT_INTEL_PATH.exists():
        return db

    for line in THREAT_INTEL_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            pid = data.get("pattern_id", "")
            if pid:
                db[pid] = ThreatPattern(**data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"Skipping malformed threat intel line: {e}")
    return db


def _save_db(db: dict[str, ThreatPattern]) -> None:
    """Write the full database back to the JSONL file."""
    THREAT_INTEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(asdict(p), default=str) for p in db.values()]
    THREAT_INTEL_PATH.write_text("\n".join(lines) + "\n" if lines else "")


def ingest_patterns(patterns: list[ThreatPattern]) -> int:
    """Merge patterns into the global JSONL.

    If a pattern_id already exists, update repos_seen, times_seen, last_seen.
    Returns count of genuinely new patterns.
    """
    if not patterns:
        return 0

    db = _load_db()
    new_count = 0

    for p in patterns:
        if p.pattern_id in db:
            existing = db[p.pattern_id]
            # Merge repos_seen
            for repo in p.repos_seen:
                if repo not in existing.repos_seen:
                    existing.repos_seen.append(repo)
            existing.times_seen += 1
            existing.last_seen = p.last_seen
        else:
            db[p.pattern_id] = p
            new_count += 1

    _save_db(db)
    logger.debug(f"Threat intel: ingested {len(patterns)} patterns, {new_count} new")
    return new_count


def query_patterns(
    attack_surface: str | None = None,
    min_severity: str | None = None,
    repo: str | None = None,
    limit: int = 50,
) -> list[ThreatPattern]:
    """Query the database with optional filters."""
    db = _load_db()
    results = list(db.values())

    if attack_surface:
        results = [p for p in results if p.attack_surface == attack_surface]

    if min_severity and min_severity in SEVERITY_ORDER:
        threshold = SEVERITY_ORDER[min_severity]
        results = [p for p in results if SEVERITY_ORDER.get(p.severity, 0) >= threshold]

    if repo:
        results = [p for p in results if repo in p.repos_seen]

    # Sort by severity desc, then times_seen desc
    results.sort(
        key=lambda p: (SEVERITY_ORDER.get(p.severity, 0), p.times_seen),
        reverse=True,
    )
    return results[:limit]


def get_patterns_for_simulation(repo_name: str) -> list[ThreatPattern]:
    """Get patterns from OTHER repos that this repo should check for.

    This is the 'learn from the network' query: patterns seen elsewhere
    but not yet in this repo.
    """
    db = _load_db()
    results = [p for p in db.values() if repo_name not in p.repos_seen]

    # Prioritize: high severity, frequently seen
    results.sort(
        key=lambda p: (SEVERITY_ORDER.get(p.severity, 0), p.times_seen),
        reverse=True,
    )
    return results


def get_stats() -> dict[str, Any]:
    """Return aggregate stats about the threat intelligence database."""
    db = _load_db()
    patterns = list(db.values())

    if not patterns:
        return {
            "total_patterns": 0,
            "by_attack_surface": {},
            "by_severity": {},
            "repos_contributing": [],
            "most_common": [],
        }

    by_surface: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    all_repos: set[str] = set()

    for p in patterns:
        by_surface[p.attack_surface] = by_surface.get(p.attack_surface, 0) + 1
        by_severity[p.severity] = by_severity.get(p.severity, 0) + 1
        all_repos.update(p.repos_seen)

    # Most common patterns by times_seen
    most_common = sorted(patterns, key=lambda p: p.times_seen, reverse=True)[:5]

    return {
        "total_patterns": len(patterns),
        "by_attack_surface": by_surface,
        "by_severity": by_severity,
        "repos_contributing": sorted(all_repos),
        "most_common": [
            {
                "pattern_id": p.pattern_id,
                "technique": p.technique,
                "attack_surface": p.attack_surface,
                "severity": p.severity,
                "times_seen": p.times_seen,
                "repos_seen": p.repos_seen,
            }
            for p in most_common
        ],
    }
