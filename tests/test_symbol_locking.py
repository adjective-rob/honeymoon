"""Tests for symbol-level pheromone locking in SymbolIndex."""

from pathlib import Path

from glitchlab.pheromone import PheromoneTrail
from glitchlab.symbols import SymbolIndex


def test_check_lock_without_pheromone_returns_none(tmp_path: Path):
    idx = SymbolIndex(tmp_path)
    assert idx.check_lock("any_file.py") is None


def test_check_lock_unclaimed_returns_none(tmp_path: Path):
    idx = SymbolIndex(tmp_path)
    trail = PheromoneTrail(tmp_path, "run-1", subscribe=False)
    idx.attach_pheromone(trail, "ant-0")

    assert idx.check_lock("src/main.py") is None


def test_check_lock_claimed_by_other_returns_holder(tmp_path: Path):
    idx = SymbolIndex(tmp_path)
    trail = PheromoneTrail(tmp_path, "run-1", subscribe=False)
    idx.attach_pheromone(trail, "ant-1")

    # ant-0 claims the file
    trail.claim("ant-0", "src/main.py")

    # ant-1 checks — should see ant-0 as holder
    assert idx.check_lock("src/main.py") == "ant-0"


def test_check_lock_claimed_by_self_returns_none(tmp_path: Path):
    idx = SymbolIndex(tmp_path)
    trail = PheromoneTrail(tmp_path, "run-1", subscribe=False)
    idx.attach_pheromone(trail, "ant-0")

    trail.claim("ant-0", "src/main.py")

    # Own claim should not block
    assert idx.check_lock("src/main.py") is None


def test_check_lock_after_release_returns_none(tmp_path: Path):
    idx = SymbolIndex(tmp_path)
    trail = PheromoneTrail(tmp_path, "run-1", subscribe=False)
    idx.attach_pheromone(trail, "ant-1")

    trail.claim("ant-0", "src/main.py")
    trail.release("ant-0", "src/main.py")

    assert idx.check_lock("src/main.py") is None
