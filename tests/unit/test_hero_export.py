from __future__ import annotations

import threading
from pathlib import Path

from lc_editor.app import Editor
from lc_editor.render import graph as graph_mod
from lc_editor.render.graph import hero_encode_args, proxy_encode_args
from lc_editor.render.runner import FakeRunner, RunResult


def _ready(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=2.5)
    assert editor.review_report()["ok"] is True


def test_spec_export_08_hero_args_are_medium_crf18(tmp_path: Path) -> None:
    args = hero_encode_args(tmp_path / "reel.mp4")
    legal = getattr(graph_mod, "hero_encode_legal", None)
    assert callable(legal)
    assert legal(args) is True
    assert args[args.index("-preset") + 1] == "medium"
    assert int(args[args.index("-crf") + 1]) <= 18
    assert "1080x1920" in args
    assert "libx264" in args
    assert "yuv420p" in args


def test_spec_export_08_proxy_and_fast_presets_are_not_hero(tmp_path: Path) -> None:
    legal = getattr(graph_mod, "hero_encode_legal", None)
    assert callable(legal)
    proxy = proxy_encode_args(tmp_path / "p.mp4")
    assert legal(proxy) is False
    fast = [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-s",
        "1080x1920",
        str(tmp_path / "reel.mp4"),
    ]
    assert legal(fast) is False
    small = [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-s",
        "540x960",
        str(tmp_path / "reel.mp4"),
    ]
    assert legal(small) is False


def test_spec_export_08_sidecar_records_encode(editor: Editor, media_file: Path) -> None:
    _ready(editor, media_file)
    out = editor.export()
    assert out["ok"] is True
    import json

    sidecar = json.loads(Path(out["sidecar"]).read_text(encoding="utf-8"))
    encode = sidecar["encode"]
    assert encode["preset"] == "medium"
    assert encode["crf"] <= 18
    assert encode["width"] == 1080
    assert encode["height"] == 1920
    assert encode["pix_fmt"] == "yuv420p"


def test_spec_export_08_failed_encode_is_not_success(editor: Editor, media_file: Path) -> None:
    _ready(editor, media_file)
    editor.runner.fail = True
    out = editor.export()
    assert out["ok"] is False
    hero = editor.store.output_dir / "reel.mp4"
    if hero.exists():
        assert hero.stat().st_size == 0 or out["ok"] is False
    assert any("hero" in w.lower() or "SPEC-EXPORT-08" in w or "timed out" in w.lower() for w in out["warnings"])


class _HoldHero(FakeRunner):
    def __init__(self) -> None:
        super().__init__()
        self.hero_entered = threading.Event()
        self.release = threading.Event()
        self.active_hero = 0
        self.max_hero = 0
        self._lock = threading.Lock()

    def run(self, args: list[str]) -> RunResult:
        joined = " ".join(args)
        is_hero = "reel.mp4" in joined and "-preset" in args and args[args.index("-preset") + 1] == "medium"
        if is_hero:
            with self._lock:
                self.active_hero += 1
                self.max_hero = max(self.max_hero, self.active_hero)
            self.hero_entered.set()
            self.release.wait(timeout=3)
            try:
                return super().run(args)
            finally:
                with self._lock:
                    self.active_hero -= 1
        return super().run(args)


def test_spec_export_09_second_export_busy_when_wait_false(tmp_path: Path, media_file: Path) -> None:
    runner = _HoldHero()
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    _ready(editor, media_file)
    results: list[dict] = []

    def first() -> None:
        results.append(editor.export(op_id="a"))

    t = threading.Thread(target=first)
    t.start()
    assert runner.hero_entered.wait(timeout=3)
    busy = editor.export(wait=False, op_id="b")
    assert busy["ok"] is False
    assert any("hero_export_busy" in w for w in busy["warnings"])
    runner.release.set()
    t.join(timeout=5)
    assert results and results[0]["ok"] is True
    assert runner.max_hero == 1
