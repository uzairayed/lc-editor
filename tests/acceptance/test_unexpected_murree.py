from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from lc_editor.app import Editor
from lc_editor.render.runner import FfmpegRunner

pytestmark = pytest.mark.murree


def _stills(folder: Path) -> list[Path]:
    from lc_editor.analysis.media import kind_for

    return sorted(p for p in folder.iterdir() if p.is_file() and kind_for(p) == "image")


@pytest.fixture
def murree_dir() -> Path:
    raw = os.environ.get("LC_EDITOR_MURREE_DIR")
    if not raw:
        pytest.skip("LC_EDITOR_MURREE_DIR is not set")
    folder = Path(raw)
    stills = _stills(folder)
    if len(stills) != 117:
        pytest.skip(f"expected 117 stills, found {len(stills)} in {folder}")
    return folder


def test_spec_ses_14_unexpected_murree(tmp_path: Path, murree_dir: Path) -> None:
    editor = Editor(workspace=tmp_path, runner=FfmpegRunner())
    created = editor.project_create(name="murree", project_dir=str(tmp_path / "murree"))
    assert created["ok"]
    assert created["timeline_summary"]
    assert editor.project_get()["project"]["preset"] is None

    imported = editor.import_folder(str(murree_dir))
    assert imported["ok"]
    assert imported["media"]
    t_ana = time.perf_counter()
    analyzed = editor.media_analyze()
    ranked = editor.shots_rank("closer", top_k=5, sheet=True)
    ana_s = time.perf_counter() - t_ana
    assert analyzed["ok"], analyzed
    assert analyzed["shots"] == len(imported["media"])
    assert ranked["ok"], ranked
    assert ranked["shots"]
    assert Path(ranked["path"]).is_file()
    print(f"murree analyze+rank {ana_s:.2f}s")
    assert ana_s <= 30.0
    sheet = editor.contact_sheet()
    assert Path(sheet["path"]).is_file()
    assert Path(sheet["path"]).stat().st_size > 100
    assert "base64" not in sheet

    picks = editor.media_list()["media"][:14]
    ids = []
    for item in picks:
        add = editor.clip_add(media_id=item["id"], duration_s=2.0)
        assert add["ok"], add
        ids.append(editor.timeline_get()["timeline"]["clips"][-1]["id"])
    for clip_id in ids[:4]:
        editor.motion_kenburns(clip_id)
    editor.caption_add(ids[0], "Unexpected Murree")
    editor.audio_bed("wind")
    editor.sfx_caption_auto()
    editor.grade_preset("winter_trip")

    stills = editor.preview_stills()
    assert stills["ok"]
    for path in stills["paths"]:
        p = Path(path)
        assert p.is_file()
        assert p.stat().st_size > 0
        assert p.suffix.lower() in {".jpg", ".jpeg"}

    review = editor.review_report()
    assert review["ok"], review

    cold_dest = Path(editor.store.output_dir / "preview_proxy.mp4")
    if cold_dest.exists():
        cold_dest.unlink()
    t0 = time.perf_counter()
    proxy = editor.preview_proxy()
    cold_s = time.perf_counter() - t0
    path = Path(proxy["path"])
    assert path.exists()
    size = path.stat().st_size
    assert size <= 14 * 1024 * 1024
    print(f"murree cold proxy {cold_s:.2f}s {size} bytes")
    t1 = time.perf_counter()
    editor.preview_proxy()
    warm_s = time.perf_counter() - t1
    print(f"murree warm proxy {warm_s:.2f}s")
    assert cold_s <= 30.0

    exported = editor.export()
    assert exported["ok"]
    assert Path(exported["sidecar"]).exists()
