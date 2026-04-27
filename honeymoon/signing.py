"""
HONEYMOON Ed25519 Event Signing

Pure-Python cryptographic attestation for the audit trail.
Every event gets signed with an Ed25519 private key generated
at `honeymoon init` time. Anyone can verify the trail with
just the public key.

Key storage:
  .honeymoon/keys/signing.key   — 32-byte Ed25519 seed (SECRET)
  .honeymoon/keys/verify.pub    — 32-byte Ed25519 public key (shareable)

Design:
  - Keys generated once per repo, reused across runs
  - Signing is synchronous and fast (~10k signs/sec on weak hardware)
  - Signatures are hex-encoded and embedded in event metadata
  - Verification needs only the public key + the event JSON
  - Graceful degradation if PyNaCl is not installed
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.encoding import HexEncoder
    SIGNING_AVAILABLE = True
except ImportError:
    SIGNING_AVAILABLE = False


class HiveSigner:
    """Ed25519 event signer for the audit trail.

    Usage:
        signer = HiveSigner.load(repo_path)  # or .generate(repo_path)
        sig = signer.sign(event_json_bytes)
        assert signer.verify(event_json_bytes, sig)
    """

    def __init__(self, signing_key: "SigningKey"):
        self._key = signing_key
        self._verify_key = signing_key.verify_key

    @classmethod
    def generate(cls, repo_path: Path) -> "HiveSigner":
        """Generate a new Ed25519 keypair and save to .honeymoon/keys/."""
        if not SIGNING_AVAILABLE:
            raise RuntimeError("PyNaCl is required for signing. Install: pip install PyNaCl")

        keys_dir = repo_path / ".honeymoon" / "keys"
        keys_dir.mkdir(parents=True, exist_ok=True)

        key = SigningKey.generate()

        key_path = keys_dir / "signing.key"
        pub_path = keys_dir / "verify.pub"

        # Write seed (private key) — 32 bytes hex-encoded
        key_path.write_text(key.encode(encoder=HexEncoder).decode())
        key_path.chmod(0o600)

        # Write public key — 32 bytes hex-encoded
        pub_path.write_text(key.verify_key.encode(encoder=HexEncoder).decode())

        logger.info("[SIGNING] Ed25519 keypair generated")
        logger.info(f"[SIGNING]   Private: {key_path}")
        logger.info(f"[SIGNING]   Public:  {pub_path}")

        return cls(key)

    @classmethod
    def load(cls, repo_path: Path) -> "HiveSigner | None":
        """Load an existing keypair from .honeymoon/keys/.

        Returns None if keys don't exist or PyNaCl isn't installed.
        """
        if not SIGNING_AVAILABLE:
            return None

        key_path = repo_path / ".honeymoon" / "keys" / "signing.key"
        if not key_path.exists():
            return None

        seed_hex = key_path.read_text().strip()
        key = SigningKey(seed_hex, encoder=HexEncoder)

        logger.debug("[SIGNING] Ed25519 keypair loaded")
        return cls(key)

    @classmethod
    def load_or_generate(cls, repo_path: Path) -> "HiveSigner | None":
        """Load existing keys, or generate new ones if none exist.

        Returns None if PyNaCl isn't installed.
        """
        signer = cls.load(repo_path)
        if signer is not None:
            return signer

        if not SIGNING_AVAILABLE:
            return None

        return cls.generate(repo_path)

    def sign(self, data: bytes) -> str:
        """Sign data and return the hex-encoded signature."""
        signed = self._key.sign(data)
        return signed.signature.hex()

    def verify(self, data: bytes, signature_hex: str) -> bool:
        """Verify a signature against data. Returns True if valid."""
        try:
            sig_bytes = bytes.fromhex(signature_hex)
            self._verify_key.verify(data, sig_bytes)
            return True
        except Exception:
            return False

    @property
    def public_key_hex(self) -> str:
        """Return the hex-encoded public key for sharing."""
        return self._verify_key.encode(encoder=HexEncoder).decode()


class HiveVerifier:
    """Standalone verifier — only needs the public key.

    Usage:
        verifier = HiveVerifier.from_file(repo_path / ".honeymoon/keys/verify.pub")
        assert verifier.verify(event_json_bytes, signature_hex)
    """

    def __init__(self, verify_key: "VerifyKey"):
        self._key = verify_key

    @classmethod
    def from_file(cls, pub_path: Path) -> "HiveVerifier | None":
        """Load a verifier from a public key file."""
        if not SIGNING_AVAILABLE:
            return None
        if not pub_path.exists():
            return None

        pub_hex = pub_path.read_text().strip()
        key = VerifyKey(pub_hex, encoder=HexEncoder)
        return cls(key)

    @classmethod
    def from_hex(cls, pub_hex: str) -> "HiveVerifier | None":
        """Load a verifier from a hex-encoded public key string."""
        if not SIGNING_AVAILABLE:
            return None
        key = VerifyKey(pub_hex, encoder=HexEncoder)
        return cls(key)

    def verify(self, data: bytes, signature_hex: str) -> bool:
        """Verify a signature against data."""
        try:
            sig_bytes = bytes.fromhex(signature_hex)
            self._key.verify(data, sig_bytes)
            return True
        except Exception:
            return False
