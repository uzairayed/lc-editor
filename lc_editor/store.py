from __future__ import annotations

import json
import os
from pathlib import Path

from lc_editor.migrate import migrate_timeline_data
from lc_editor.models import Project, Timeline


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.history_dir = root / "history"
        self.media_dir = root / "media"
        self.cache_dir = root / "cache"
        self.caption_dir = root / "captions"
        self.output_dir = root / "output"
        self.user_sfx_dir = root / "user-sfx"
        self.thumbs_dir = self.cache_dir / "thumbs"
        self.proxies_dir = self.cache_dir / "proxies"
        self.clip_cache_dir = self.cache_dir / "clips"
        self.stills_dir = self.cache_dir / "stills"
        self.analysis_dir = self.cache_dir / "analysis"
        self.keyframes_dir = self.analysis_dir / "keyframes"
        self.beats_dir = self.analysis_dir / "beats"
        self.templates_dir = root / "templates"
        self.project_path = root / "project.json"
        self.state_path = root / "state.json"
        self.pointer = 0
        self.max_pointer = 0
        self.ledger: dict[str, dict] = {}
        self.project: Project | None = None
        self.timeline = Timeline()

    def ensure_dirs(self) -> None:
        for d in (
            self.history_dir,
            self.media_dir,
            self.cache_dir,
            self.caption_dir,
            self.output_dir,
            self.user_sfx_dir,
            self.thumbs_dir,
            self.proxies_dir,
            self.clip_cache_dir,
            self.stills_dir,
            self.analysis_dir,
            self.keyframes_dir,
            self.beats_dir,
            self.templates_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def snapshot_path(self, n: int) -> Path:
        return self.history_dir / f"{n:04d}.json"

    def persist(self) -> None:
        self.ensure_dirs()
        if self.project is None:
            raise RuntimeError("no project")
        atomic_write(self.project_path, self.project.model_dump_json(indent=2))
        atomic_write(
            self.state_path,
            json.dumps(
                {
                    "pointer": self.pointer,
                    "max_pointer": self.max_pointer,
                    "ledger": self.ledger,
                },
                indent=2,
            ),
        )
        atomic_write(
            self.snapshot_path(self.pointer),
            self.timeline.model_dump_json(indent=2),
        )

    def load(self) -> None:
        self.project = Project.model_validate_json(self.project_path.read_text(encoding="utf-8"))
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.pointer = int(state["pointer"])
        self.max_pointer = int(state["max_pointer"])
        self.ledger = dict(state.get("ledger") or {})
        self.timeline = migrate_timeline_data(
            json.loads(self.snapshot_path(self.pointer).read_text(encoding="utf-8"))
        )

    def init_project(self, project: Project) -> None:
        self.ensure_dirs()
        self.project = project
        self.timeline = Timeline(version=0)
        self.pointer = 0
        self.max_pointer = 0
        self.ledger = {}
        self.persist()

    def commit(self, timeline: Timeline, op_id: str | None, result: dict) -> Timeline:
        next_ptr = self.pointer + 1
        timeline = timeline.model_copy(update={"version": next_ptr})
        self.timeline = timeline
        self.pointer = next_ptr
        self.max_pointer = next_ptr
        result = dict(result)
        result["timeline_summary"] = {
            **result["timeline_summary"],
            "version": next_ptr,
        }
        if op_id:
            self.ledger[op_id] = result
        self.persist()
        return timeline

    def replay(self, op_id: str | None) -> dict | None:
        if not op_id:
            return None
        return self.ledger.get(op_id)

    def undo(self) -> bool:
        if self.pointer <= 0:
            return False
        self.pointer -= 1
        self.timeline = migrate_timeline_data(
            json.loads(self.snapshot_path(self.pointer).read_text(encoding="utf-8"))
        )
        self.persist()
        return True

    def redo(self) -> bool:
        if self.pointer >= self.max_pointer:
            return False
        self.pointer += 1
        self.timeline = migrate_timeline_data(
            json.loads(self.snapshot_path(self.pointer).read_text(encoding="utf-8"))
        )
        self.persist()
        return True
