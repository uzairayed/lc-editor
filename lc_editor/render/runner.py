from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    def run(self, args: list[str]) -> RunResult: ...


class FfmpegRunner:
    def run(self, args: list[str]) -> RunResult:
        argv = list(args)
        if argv and "ffmpeg" in Path(argv[0]).name.lower() and "-nostdin" not in argv:
            argv.insert(1, "-nostdin")
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=90,
            )
        except subprocess.TimeoutExpired as exc:
            return RunResult(1, exc.stdout or "", exc.stderr or "ffmpeg timed out")
        return RunResult(proc.returncode, proc.stdout, proc.stderr)


@dataclass
class FakeRunner:
    calls: list[list[str]] = field(default_factory=list)
    duration_s: float = 5.0
    width: int = 1920
    height: int = 1080
    has_audio: bool = True
    fail: bool = False
    scene_cuts: list[float] = field(default_factory=lambda: [2.0])
    fail_inputs: list[str] = field(default_factory=list)

    def run(self, args: list[str]) -> RunResult:
        self.calls.append(list(args))
        joined = " ".join(args)
        if self.fail or any(token and token in joined for token in self.fail_inputs):
            return RunResult(1, "", "fake fail")
        tool = Path(args[0]).name.lower()
        if "ffprobe" in tool:
            payload = {
                "streams": [
                    {
                        "codec_type": "video",
                        "width": self.width,
                        "height": self.height,
                        "r_frame_rate": "30/1",
                        "avg_frame_rate": "30/1",
                    },
                    *([{ "codec_type": "audio" }] if self.has_audio else []),
                ],
                "format": {"duration": str(self.duration_s)},
            }
            return RunResult(0, json.dumps(payload), "")
        stderr = ""
        if "scdet" in joined or "metadata=print" in joined:
            stderr = self._analysis_meta_text(has_audio="-af" in args or "astats" in joined)
        out = _output_path(args)
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                out.write_bytes(b"\xff\xd8\xff\xd9")
            else:
                out.write_bytes(b"fake-media")
        return RunResult(0, "", stderr)

    def _analysis_meta_text(self, *, has_audio: bool) -> str:
        times = sorted({0.0, *self.scene_cuts, float(self.duration_s)})
        lines = []
        for i, t in enumerate(times):
            lines.append(f"frame:{i}    pts:{i}       pts_time:{t}")
            if t in self.scene_cuts:
                lines.append(f"lavfi.scd.time={t}")
                lines.append("lavfi.scd.score=15.0")
            lines.append("lavfi.signalstats.YAVG=120.0")
            lines.append("lavfi.signalstats.YDIF=6.0")
            lines.append("lavfi.signalstats.YMIN=10")
            lines.append("lavfi.signalstats.YMAX=220")
            if has_audio:
                lines.append("lavfi.astats.Overall.RMS_level=-16.0")
                lines.append("lavfi.astats.Overall.Crest_factor=6.0")
        return "\n".join(lines)


def _output_path(args: list[str]) -> Path | None:
    skip_next = False
    candidates: list[str] = []
    flags_with_value = {
        "-i",
        "-ss",
        "-t",
        "-vf",
        "-af",
        "-filter_complex",
        "-c:v",
        "-c:a",
        "-preset",
        "-crf",
        "-pix_fmt",
        "-r",
        "-s",
        "-map",
        "-b:a",
        "-frames:v",
        "-update",
        "-f",
        "-filter:v",
        "-movflags",
        "-shortest",
    }
    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg in flags_with_value:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        if i == 0:
            continue
        candidates.append(arg)
    if not candidates:
        return None
    return Path(candidates[-1])


def find_tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise FileNotFoundError(name)
    return found
