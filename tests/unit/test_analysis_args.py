from __future__ import annotations

from pathlib import Path

from lc_editor.analysis.shots import (
    analysis_pass_args,
    parse_astats,
    parse_scdet,
    parse_signalstats,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_analysis_pass_args_read_proxy_and_stay_cheap() -> None:
    args = analysis_pass_args(
        "ffmpeg",
        "cache/proxies/abcd.mp4",
        "cache/analysis/v.meta",
        "cache/analysis/a.meta",
        has_audio=True,
    )
    blob = " ".join(args)
    assert args[args.index("-i") + 1] == "cache/proxies/abcd.mp4"
    assert "scdet" in blob
    assert "signalstats" in blob
    assert "astats" in blob
    assert "metadata=print" in blob
    assert "lut3d" not in blob
    assert "afftdn" not in blob
    assert args.count("-i") == 1
    assert "-f" in args and args[args.index("-f") + 1] == "null"


def test_analysis_pass_args_skip_audio_when_silent() -> None:
    args = analysis_pass_args(
        "ffmpeg",
        "proxy.mp4",
        "v.meta",
        None,
        has_audio=False,
    )
    blob = " ".join(args)
    assert "astats" not in blob
    assert "-an" in args
    assert blob.count("-i ") == 1 or args.count("-i") == 1


def test_parse_scdet_skips_malformed() -> None:
    text = (FIXTURES / "scdet_signalstats.txt").read_text(encoding="utf-8")
    cuts = parse_scdet(text)
    assert cuts == [2.0]
    assert parse_scdet("") == []
    assert parse_scdet("lavfi.scd.time=\nnot a frame") == []


def test_parse_signalstats_per_frame() -> None:
    text = (FIXTURES / "scdet_signalstats.txt").read_text(encoding="utf-8")
    frames = parse_signalstats(text)
    assert len(frames) == 4
    assert frames[0]["t"] == 0.0
    assert frames[0]["yavg"] == 128.0
    assert frames[2]["ydif"] == 12.0
    assert frames[2]["ymin"] == 4.0
    assert parse_signalstats("") == []


def test_parse_astats_skips_malformed() -> None:
    text = (FIXTURES / "astats.txt").read_text(encoding="utf-8")
    frames = parse_astats(text)
    assert len(frames) == 3
    assert frames[0]["rms_db"] == -18.5
    assert frames[2]["crest"] == 12.0
    assert parse_astats("") == []


def test_parse_prefixed_ffmpeg_stderr_matches_plain() -> None:
    real = (FIXTURES / "metadata_print_real.txt").read_text(encoding="utf-8")
    assert parse_scdet(real) == [2.0]
    frames = parse_signalstats(real)
    assert len(frames) == 4
    assert frames[0]["t"] == 0.0
    assert frames[0]["yavg"] == 128.0
    assert frames[2]["ydif"] == 12.0
    assert frames[2]["ymin"] == 4.0
    audio = parse_astats(real)
    assert len(audio) == 3
    assert audio[0]["rms_db"] == -18.5
    assert audio[2]["crest"] == 12.0
    assert audio[0].get("yavg") is None
    assert frames[0].get("rms_db") is None
