from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

AudioClass = Literal["engine", "ambient", "speech", "silent"]


class ShotMetrics(BaseModel):
    motion: float = Field(default=0.0, ge=0.0, le=1.0)
    sharpness: float = Field(default=0.0, ge=0.0, le=1.0)
    luma_mean: float = Field(default=0.0, ge=0.0, le=1.0)
    luma_spread: float = Field(default=0.0, ge=0.0, le=1.0)
    shake: float = Field(default=0.0, ge=0.0, le=1.0)
    audio_rms_db: float | None = None
    audio_class: AudioClass = "silent"


class Shot(BaseModel):
    id: str
    media_id: str
    in_s: float
    out_s: float
    duration_s: float
    keyframe: str
    metrics: ShotMetrics = Field(default_factory=ShotMetrics)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _span_ok(self) -> Shot:
        if self.out_s <= self.in_s:
            raise ValueError("out_s must be greater than in_s")
        return self


def shot_id(proxy_hash: str, index: int) -> str:
    return f"{proxy_hash}_{index}"


def manifest_path(analysis_dir: Path, proxy_hash: str) -> Path:
    return analysis_dir / f"{proxy_hash}.json"


def _round_shot(shot: Shot) -> dict:
    data = shot.model_dump()
    for key in ("in_s", "out_s", "duration_s"):
        data[key] = round(float(data[key]), 4)
    metrics = data["metrics"]
    for key, value in list(metrics.items()):
        if isinstance(value, float):
            metrics[key] = round(value, 4)
    return data


def write_manifest(path: Path, shots: list[Shot]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [_round_shot(shot) for shot in shots]
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def load_manifest(path: Path) -> list[Shot]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Shot.model_validate(item) for item in raw]
