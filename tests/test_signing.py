"""Tests for Ed25519 event signing."""

import json
from pathlib import Path

from honeymoon.signing import HiveSigner, HiveVerifier, SIGNING_AVAILABLE


def test_generate_creates_keypair(tmp_path: Path):
    signer = HiveSigner.generate(tmp_path)
    assert (tmp_path / ".honeymoon" / "keys" / "signing.key").exists()
    assert (tmp_path / ".honeymoon" / "keys" / "verify.pub").exists()
    assert signer.public_key_hex  # non-empty hex string


def test_signing_key_is_private(tmp_path: Path):
    HiveSigner.generate(tmp_path)
    key_path = tmp_path / ".honeymoon" / "keys" / "signing.key"
    # Owner-only read/write
    assert oct(key_path.stat().st_mode)[-3:] == "600"


def test_load_roundtrip(tmp_path: Path):
    original = HiveSigner.generate(tmp_path)
    loaded = HiveSigner.load(tmp_path)
    assert loaded is not None
    assert loaded.public_key_hex == original.public_key_hex


def test_load_returns_none_when_no_keys(tmp_path: Path):
    assert HiveSigner.load(tmp_path) is None


def test_load_or_generate_creates_if_missing(tmp_path: Path):
    signer = HiveSigner.load_or_generate(tmp_path)
    assert signer is not None
    assert (tmp_path / ".honeymoon" / "keys" / "signing.key").exists()


def test_load_or_generate_loads_if_exists(tmp_path: Path):
    original = HiveSigner.generate(tmp_path)
    loaded = HiveSigner.load_or_generate(tmp_path)
    assert loaded.public_key_hex == original.public_key_hex


def test_sign_and_verify(tmp_path: Path):
    signer = HiveSigner.generate(tmp_path)
    data = b'{"event_type": "test", "payload": {}}'
    sig = signer.sign(data)
    assert isinstance(sig, str)
    assert len(sig) == 128  # 64 bytes hex-encoded
    assert signer.verify(data, sig)


def test_verify_rejects_tampered_data(tmp_path: Path):
    signer = HiveSigner.generate(tmp_path)
    data = b'original data'
    sig = signer.sign(data)
    assert not signer.verify(b'tampered data', sig)


def test_verify_rejects_wrong_signature(tmp_path: Path):
    signer = HiveSigner.generate(tmp_path)
    data = b'some data'
    fake_sig = "00" * 64
    assert not signer.verify(data, fake_sig)


def test_verifier_from_file(tmp_path: Path):
    signer = HiveSigner.generate(tmp_path)
    data = b'event payload'
    sig = signer.sign(data)

    pub_path = tmp_path / ".honeymoon" / "keys" / "verify.pub"
    verifier = HiveVerifier.from_file(pub_path)
    assert verifier is not None
    assert verifier.verify(data, sig)


def test_verifier_from_hex(tmp_path: Path):
    signer = HiveSigner.generate(tmp_path)
    data = b'hello hive'
    sig = signer.sign(data)

    verifier = HiveVerifier.from_hex(signer.public_key_hex)
    assert verifier is not None
    assert verifier.verify(data, sig)


def test_verifier_rejects_tampered(tmp_path: Path):
    signer = HiveSigner.generate(tmp_path)
    sig = signer.sign(b'real data')

    verifier = HiveVerifier.from_hex(signer.public_key_hex)
    assert not verifier.verify(b'fake data', sig)


def test_different_signers_cannot_cross_verify(tmp_path: Path):
    signer_a = HiveSigner.generate(tmp_path / "repo_a")
    signer_b = HiveSigner.generate(tmp_path / "repo_b")

    data = b'some event'
    sig_a = signer_a.sign(data)

    # B's verifier should reject A's signature
    verifier_b = HiveVerifier.from_hex(signer_b.public_key_hex)
    assert not verifier_b.verify(data, sig_a)


def test_audit_event_signing_integration(tmp_path: Path):
    """End-to-end: sign a JSON event, verify with standalone verifier."""
    signer = HiveSigner.generate(tmp_path)

    event = {"event_type": "test.completed", "run_id": "abc", "payload": {"status": "ok"}}
    event_bytes = json.dumps(event, sort_keys=True).encode("utf-8")

    sig = signer.sign(event_bytes)

    # Standalone verification with only the public key
    pub_path = tmp_path / ".honeymoon" / "keys" / "verify.pub"
    verifier = HiveVerifier.from_file(pub_path)
    assert verifier.verify(event_bytes, sig)
