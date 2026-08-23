from __future__ import annotations

import json
import re
from pathlib import Path

from lc_editor.models import LayerItem, TextStyle, Timeline, Transform
from lc_editor.ops.timeline import Reject
from lc_editor.presets import PRESET_DIR


SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


def load_template(name: str, extra_dir: Path | None = None) -> dict:
    if extra_dir:
        local = extra_dir / f"{name}.json"
        if local.exists():
            return json.loads(local.read_text(encoding="utf-8"))
    path = PRESET_DIR / f"{name}.json"
    if not path.exists():
        raise Reject(f"unknown template {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_templates(extra_dir: Path | None = None) -> list[str]:
    names = {p.stem for p in PRESET_DIR.glob("*.json")}
    if extra_dir and extra_dir.exists():
        names.update(p.stem for p in extra_dir.glob("*.json"))
    return sorted(names)


def apply_template(timeline: Timeline, data: dict, bindings: dict[str, str] | None = None) -> tuple[Timeline, list[str]]:
    if data.get("allow_music"):
        raise Reject("SPEC-TPL-04: a template cannot set allow_music")
    bindings = bindings or {}
    warnings: list[str] = []
    layers = list(timeline.layers)
    for spec in data.get("layers") or []:
        text = spec.get("text") or ""
        placeholder = spec.get("placeholder")
        if placeholder:
            if placeholder not in bindings:
                warnings.append(f"SPEC-TPL-04: missing binding {placeholder}")
            text = bindings.get(placeholder, text)
        if spec.get("kind", "text") == "text" and not text.strip():
            continue
        if spec.get("box"):
            raise Reject("SPEC-TPL-04: template cannot add a caption box")
        style = spec.get("style") or {}
        layers.append(
            LayerItem(
                id=spec.get("id") or f"tpl_{len(layers)}",
                kind=spec.get("kind") or "text",
                z=int(spec.get("z") or 20),
                start_s=float(spec.get("start_s") or 0.0),
                duration_s=float(spec.get("duration_s") or 2.0),
                text=text,
                role=spec.get("role") or "body",
                y_pct=float(spec.get("y_pct") or 0.36),
                style=TextStyle(
                    role=spec.get("role") or "body",
                    motion=style.get("motion") or "fade",
                ),
                transform=Transform(**(spec.get("transform") or {})),
            )
        )
    return timeline.model_copy(update={"layers": layers, "template_id": data.get("id")}), warnings


def save_template(name: str, timeline: Timeline, dest_dir: Path, look: dict | None = None) -> Path:
    if not SLUG.match(name):
        raise Reject("SPEC-TPL-03: name must be a simple slug")
    dest_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": name,
        "schema_version": 2,
        "layers": [
            {
                "id": layer.id,
                "kind": layer.kind,
                "z": layer.z,
                "start_s": layer.start_s,
                "duration_s": layer.duration_s,
                "text": layer.text,
                "role": layer.role,
                "y_pct": layer.y_pct,
                "style": layer.style.model_dump(),
                "transform": layer.transform.model_dump(),
            }
            for layer in timeline.layers
        ],
        "look": look or {},
    }
    path = dest_dir / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
