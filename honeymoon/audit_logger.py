"""
HONEYMOON Audit Logger — Signed Event Trail

Every event emitted by the pipeline gets:
  1. Signed with Ed25519 (if keys exist)
  2. Appended to .honeymoon/logs/audit.jsonl

The signing key is generated at `honeymoon init` time.
Verification needs only the public key (verify.pub).

Falls back to unsigned JSONL if:
  - PyNaCl is not installed
  - No keypair exists (pre-init repos)

Zephyr hardware signing is still supported as an optional
upgrade — if `zephyr` is in PATH, it takes priority.
"""

import shutil
import subprocess
from pathlib import Path

from loguru import logger

from honeymoon.event_bus import bus, HiveEvent
from honeymoon.signing import HiveSigner


class AuditLogger:
    """Append-only signed audit trail.

    Priority:
      1. Zephyr hardware signing (if binary in PATH)
      2. Ed25519 software signing (if keys exist)
      3. Unsigned JSONL fallback
    """

    def __init__(self, log_file: str | Path = "audit.jsonl", repo_path: Path | None = None):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Try Zephyr first (hardware signing)
        self.zephyr_enabled = shutil.which("zephyr") is not None

        # Try Ed25519 (software signing)
        self.signer: HiveSigner | None = None
        if not self.zephyr_enabled and repo_path is not None:
            self.signer = HiveSigner.load(repo_path)
        elif not self.zephyr_enabled:
            # Infer repo_path from log_file location
            candidate = self.log_file.parent.parent.parent
            self.signer = HiveSigner.load(candidate)

        if self.zephyr_enabled:
            logger.info("[AUDIT] Zephyr hardware signing enabled")
        elif self.signer is not None:
            logger.info("[AUDIT] Ed25519 software signing enabled")
        else:
            logger.warning("[AUDIT] No signing available — unsigned JSONL fallback")

        bus.subscribe(self.log_event)

    def log_event(self, event: HiveEvent) -> None:
        """Sign and append an event to the audit trail."""
        event_json = event.model_dump_json()

        # --- Priority 1: Zephyr hardware signing ---
        if self.zephyr_enabled:
            label = event.action_id if event.action_id else event.event_id
            try:
                subprocess.run(
                    [
                        "zephyr", "sign-payload",
                        "--label", label,
                        "--inline", event_json,
                        "--output", str(self.log_file),
                        "--append",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                return
            except subprocess.CalledProcessError as e:
                logger.error(f"[AUDIT] Zephyr signing failed: {e.stderr.strip()}")
            except Exception as e:
                logger.error(f"[AUDIT] Zephyr execution error: {e}")
            # Fall through to Ed25519

        # --- Priority 2: Ed25519 software signing ---
        if self.signer is not None:
            signature = self.signer.sign(event_json.encode("utf-8"))
            event.metadata["ed25519_signature"] = signature
            event.metadata["ed25519_public_key"] = self.signer.public_key_hex
            event_json = event.model_dump_json()

        # --- Priority 3 (or signed write): Append to file ---
        if self.signer is None and not self.zephyr_enabled:
            event.metadata["attestation"] = "unsigned"
            event_json = event.model_dump_json()

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(event_json + "\n")
