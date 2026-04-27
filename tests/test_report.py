"""Tests for the signed report writer."""

import json
from pathlib import Path

from honeymoon.report import write_report
from honeymoon.signing import HiveSigner, HiveVerifier


def test_write_report_creates_files(tmp_path: Path):
    report_path = write_report(
        repo_path=tmp_path,
        run_id="test-run-12345678",
        mission_name="investigate",
        objective="Find all external API calls",
        findings={
            "summary": "Found 3 external calls.",
            "findings": [
                {
                    "title": "HTTP call to stripe",
                    "evidence": "payments.py:42 — requests.post('https://api.stripe.com')",
                    "analysis": "Direct Stripe API call without retry logic",
                    "severity": "medium",
                    "confidence": "high",
                },
            ],
            "recommendations": ["Add retry logic to payments.py"],
        },
    )
    assert report_path.exists()
    content = report_path.read_text()
    assert "# Investigation Report" in content
    assert "Find all external API calls" in content
    assert "HTTP call to stripe" in content
    assert "payments.py:42" in content
    assert "Add retry logic" in content

    # JSON sidecar should also exist
    json_path = report_path.with_suffix(".json")
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert data["mission"] == "investigate"


def test_write_report_signed_when_keys_exist(tmp_path: Path):
    signer = HiveSigner.generate(tmp_path)

    report_path = write_report(
        repo_path=tmp_path,
        run_id="signed-run-12345678",
        mission_name="investigate",
        objective="Check for secrets",
        findings={"summary": "No secrets found.", "findings": []},
    )
    content = report_path.read_text()
    assert "Ed25519" in content
    assert "Signature:" in content

    # Verify the signature
    parts = content.split("\n---\n\n## Attestation")
    report_body = parts[0]

    json_path = report_path.with_suffix(".json")
    data = json.loads(json_path.read_text())
    assert "signature" in data

    verifier = HiveVerifier.from_hex(data["public_key"])
    assert verifier.verify(report_body.encode("utf-8"), data["signature"])


def test_write_report_unsigned_without_keys(tmp_path: Path):
    report_path = write_report(
        repo_path=tmp_path,
        run_id="unsigned-run-123",
        mission_name="investigate",
        objective="Quick check",
        findings={"summary": "All clear.", "findings": []},
    )
    content = report_path.read_text()
    assert "Unsigned" in content


def test_write_report_with_verification(tmp_path: Path):
    report_path = write_report(
        repo_path=tmp_path,
        run_id="verified-run-123",
        mission_name="investigate",
        objective="Dependency audit",
        findings={"summary": "2 issues.", "findings": []},
        verification={"verdict": "confirmed", "notes": "All findings verified."},
    )
    content = report_path.read_text()
    assert "confirmed" in content.upper() or "CONFIRMED" in content
    assert "All findings verified" in content


def test_write_report_with_budget(tmp_path: Path):
    report_path = write_report(
        repo_path=tmp_path,
        run_id="budget-run-1234",
        mission_name="investigate",
        objective="Cost test",
        findings={"summary": "Done.", "findings": []},
        budget={"total_tokens": 5000, "estimated_cost": 0.0123, "call_count": 3},
    )
    content = report_path.read_text()
    assert "5,000" in content
    assert "$0.0123" in content


def test_write_report_severity_icons(tmp_path: Path):
    report_path = write_report(
        repo_path=tmp_path,
        run_id="severity-run-12",
        mission_name="investigate",
        objective="Icon test",
        findings={
            "summary": "Multiple severities.",
            "findings": [
                {"title": "Critical issue", "evidence": "x.py:1", "analysis": "bad",
                 "severity": "critical", "confidence": "high"},
                {"title": "Info note", "evidence": "y.py:2", "analysis": "ok",
                 "severity": "info", "confidence": "low"},
            ],
        },
    )
    content = report_path.read_text()
    assert "🔴" in content  # critical
    assert "⚪" in content  # info
