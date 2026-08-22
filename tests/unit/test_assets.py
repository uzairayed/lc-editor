from __future__ import annotations

import hashlib
from pathlib import Path

from lc_editor.assets.pack import LUT_SIZE, _map_rgb, cube_path, ensure_assets, sfx_path


def test_spec_snd_02_snow_and_gravel_differ() -> None:
    ensure_assets()
    snow = sfx_path("steps_snow").read_bytes()
    gravel = sfx_path("steps_gravel").read_bytes()
    assert snow != gravel
    assert hashlib.sha256(snow).hexdigest() != hashlib.sha256(gravel).hexdigest()
    assert len(snow) != len(gravel)


def test_spec_rnd_14_cubes_are_17() -> None:
    ensure_assets()
    for name in ("neutral", "winter_trip", "motovlog"):
        text = cube_path(name).read_text(encoding="utf-8")
        assert f"LUT_3D_SIZE {LUT_SIZE}" in text
        assert text.count("\n") > 4000
    shadow = (0.15, 0.15, 0.18)
    assert _map_rgb(*shadow, "winter_trip") != _map_rgb(*shadow, "neutral")
    assert _map_rgb(*shadow, "motovlog") != _map_rgb(*shadow, "winter_trip")
    assert _map_rgb(0.5, 0.5, 0.5, "neutral") == (0.5, 0.5, 0.5)
