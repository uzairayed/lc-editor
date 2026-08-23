from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from lc_editor.analysis.manifest import Shot, ShotMetrics, load_manifest, shot_id, write_manifest
from lc_editor.models import SHOT_MAX_S, SHOT_MIN_S


def _shot(**overrides) -> Shot:
    base = {
        "id": "deadbeefdeadbeef_0",
        "media_id": "m1",
        "in_s": 0.0,
        "out_s": 2.0,
        "duration_s": 2.0,
        "keyframe": "/tmp/deadbeefdeadbeef_0.jpg",
        "metrics": ShotMetrics(),
    }
    base.update(overrides)
    return Shot.model_validate(base)


def test_shot_min_max_constants() -> None:
    assert SHOT_MIN_S == 0.5
    assert SHOT_MAX_S == 8.0


def test_shot_rejects_out_before_in() -> None:
    with pytest.raises(ValidationError):
        _shot(in_s=2.0, out_s=1.0, duration_s=1.0)


def test_shot_rejects_metric_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ShotMetrics(motion=1.5)
    with pytest.raises(ValidationError):
        ShotMetrics(sharpness=-0.1)


def test_shot_id_is_deterministic() -> None:
    assert shot_id("deadbeefdeadbeef", 0) == "deadbeefdeadbeef_0"
    assert shot_id("deadbeefdeadbeef", 3) == "deadbeefdeadbeef_3"
    assert shot_id("deadbeefdeadbeef", 0) == shot_id("deadbeefdeadbeef", 0)


def test_write_manifest_is_atomic_and_round_trips(tmp_path: Path) -> None:
    dest = tmp_path / "deadbeefdeadbeef.json"
    shots = [_shot()]
    write_manifest(dest, shots)
    assert dest.exists()
    assert not dest.with_suffix(dest.suffix + ".tmp").exists()
    loaded = load_manifest(dest)
    assert loaded[0].id == shots[0].id
    assert loaded[0].in_s == 0.0
    assert loaded[0].out_s == 2.0


def test_write_manifest_same_input_is_byte_identical(tmp_path: Path) -> None:
    dest_a = tmp_path / "a.json"
    dest_b = tmp_path / "b.json"
    shots = [_shot(), _shot(id="deadbeefdeadbeef_1", in_s=2.0, out_s=4.0, duration_s=2.0)]
    write_manifest(dest_a, shots)
    write_manifest(dest_b, shots)
    assert dest_a.read_bytes() == dest_b.read_bytes()


def test_failed_tmp_write_leaves_existing_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "keep.json"
    write_manifest(dest, [_shot()])
    before = dest.read_bytes()

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", boom)
    with pytest.raises(OSError):
        write_manifest(dest, [_shot(id="other_0")])
    assert dest.read_bytes() == before
    assert not dest.with_suffix(dest.suffix + ".tmp").exists()
