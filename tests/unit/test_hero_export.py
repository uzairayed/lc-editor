from __future__ import annotations

import threading
from pathlib import Path

from lc_editor.app import Editor
from lc_editor.render import graph as graph_mod
from lc_editor.render.graph import hero_encode_args, hero_encode_legal, proxy_encode_args, share_encode_args
from lc_editor.render.runner import FakeRunner, RunResult


def _ready(editor: Editor, media_file: Path) -> None:
    editor.import_file(str(media_file))
    editor.clip_add(media_id=editor.media[-1].id, duration_s=5.0)
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


def test_spec_export_10_share_args_are_720p_not_hero(tmp_path: Path) -> None:
    args = share_encode_args(tmp_path / "reel_share.mp4")
    assert args[args.index("-s") + 1] == "720x1280"
    assert int(args[args.index("-crf") + 1]) == 22
    assert args[args.index("-b:a") + 1] == "128k"
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"
    assert args[args.index("-color_range") + 1] == "tv"
    assert "+faststart" in args
    assert "libx264" in args
    assert "aac" in args
    assert hero_encode_legal(args) is False
    wide = share_encode_args(tmp_path / "wide.mp4", 1920, 1080)
    assert wide[wide.index("-s") + 1] == "1280x720"
    assert hero_encode_legal(wide) is False


def test_spec_export_10_share_writes_sibling(editor: Editor, media_file: Path) -> None:
    _ready(editor, media_file)
    hero_out = editor.export()
    assert hero_out["ok"] is True
    hero = Path(hero_out["hero"])
    assert hero.name == "reel.mp4"
    hero_bytes = hero.read_bytes()
    out = editor.export(preset="share")
    assert out["ok"] is True
    share = Path(out["share"])
    assert share.name == "reel_share.mp4"
    assert share.exists()
    assert share != hero
    assert hero.exists()
    assert hero.read_bytes() == hero_bytes
    assert out["encode"]["crf"] == 22
    assert out["encode"]["width"] == 720
    assert out["encode"]["height"] == 1280
    assert hero_encode_legal(share_encode_args(share)) is False
    assemble = None
    for args in editor.runner.calls:
        out_path = (args[-1] if args else "").replace("\\", "/")
        if out_path.endswith("/reel_share.mp4") and "-filter_complex" in args:
            assemble = args
    assert assemble is not None
    assert assemble[assemble.index("-s") + 1] == "720x1280"
    assert assemble[assemble.index("-crf") + 1] == "22"
    assert assemble[assemble.index("-b:a") + 1] == "128k"
    assert "+faststart" in assemble
    assert hero_encode_legal(assemble) is False


def test_spec_export_10_rejects_unknown_preset(editor: Editor, media_file: Path) -> None:
    _ready(editor, media_file)
    out = editor.export(preset="proxy")
    assert out["ok"] is False
    assert any("SPEC-EXPORT-10" in w for w in out["warnings"])


def test_spec_export_10_phone_alias_skips_hero_file(editor: Editor, media_file: Path) -> None:
    _ready(editor, media_file)
    out = editor.export(preset="phone")
    assert out["ok"] is True
    share = Path(out["share"])
    assert share.name == "reel_share.mp4"
    assert share.exists()
    assert "hero" not in out
    assert not (editor.store.output_dir / "reel.mp4").exists()


def test_spec_export_10_share_uses_lock(tmp_path: Path, media_file: Path) -> None:
    runner = _HoldHero()
    editor = Editor(workspace=tmp_path, runner=runner)
    editor.project_create(name="reel", project_dir=str(tmp_path / "reel"))
    _ready(editor, media_file)
    results: list[dict] = []

    def first() -> None:
        results.append(editor.export(op_id="hero"))

    t = threading.Thread(target=first)
    t.start()
    assert runner.hero_entered.wait(timeout=3)
    busy = editor.export(preset="share", wait=False, op_id="share")
    assert busy["ok"] is False
    assert any("hero_export_busy" in w for w in busy["warnings"])
    runner.release.set()
    t.join(timeout=5)
    assert results and results[0]["ok"] is True
    assert runner.max_hero == 1
