from __future__ import annotations

import json
import re
from pathlib import Path

from lc_editor.models import CC0_SFX_KINDS, USER_SFX_EXTS

ATTRIBUTION_NAME = "ATTRIBUTION.json"
CC0_LICENSE = "CC0"
# CapCut labels / ids from the reel-SFX reference issue. Never import those rips.
_BANNED_NAME_RE = re.compile(
    r"(capcut|222764|1184192|money[\s_-]?chakin|computer[\s_-]?mouse[\s_-]?click|pirone)",
    re.IGNORECASE,
)
def attribution_path(user_sfx_dir: Path) -> Path:
    return user_sfx_dir / ATTRIBUTION_NAME


def load_attribution(user_sfx_dir: Path) -> dict:
    path = attribution_path(user_sfx_dir)
    if not path.exists():
        return {"items": [], "note": _attribution_note()}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": [], "note": _attribution_note()}
    if not isinstance(data, dict):
        return {"items": [], "note": _attribution_note()}
    items = data.get("items")
    if not isinstance(items, list):
        items = []
    return {
        "items": [i for i in items if isinstance(i, dict)],
        "note": str(data.get("note") or _attribution_note()),
    }


def save_attribution(user_sfx_dir: Path, data: dict) -> Path:
    user_sfx_dir.mkdir(parents=True, exist_ok=True)
    path = attribution_path(user_sfx_dir)
    payload = {
        "note": str(data.get("note") or _attribution_note()),
        "items": list(data.get("items") or []),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _attribution_note() -> str:
    return (
        "Owner-imported CC0 SFX only (Mixkit / Pixabay / Freesound). "
        "Do not ship CapCut rips or Python-synth generators. "
        "Third-party audio is never vendored inside the pip package."
    )


def find_user_sfx(user_sfx_dir: Path, kind: str) -> Path | None:
    if not kind or not user_sfx_dir.exists():
        return None
    for ext in (".wav", ".mp3", ".aiff"):
        candidate = user_sfx_dir / f"{kind}{ext}"
        if candidate.is_file():
            return candidate
    return None


def user_sfx_kinds(user_sfx_dir: Path) -> set[str]:
    if not user_sfx_dir.exists():
        return set()
    kinds: set[str] = set()
    for path in user_sfx_dir.iterdir():
        if path.is_file() and path.suffix.lower() in USER_SFX_EXTS:
            kinds.add(path.stem)
    return kinds


def attribution_by_kind(user_sfx_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in load_attribution(user_sfx_dir).get("items", []):
        kind = str(item.get("kind") or "").strip()
        if kind:
            out[kind] = item
    return out


def reject_banned_source(path: Path) -> str | None:
    blob = f"{path.name} {path.as_posix()}"
    if _BANNED_NAME_RE.search(blob):
        return "SPEC-SND-18: CapCut rips are rejected; use Mixkit / Pixabay / Freesound CC0"
    return None


def normalize_cc0_license(license: str) -> str | None:
    text = (license or "").strip()
    if text.upper() == CC0_LICENSE:
        return CC0_LICENSE
    return None


def clear_kind_files(user_sfx_dir: Path, kind: str, keep: Path | None = None) -> None:
    if not user_sfx_dir.exists():
        return
    keep_resolved = keep.resolve() if keep is not None else None
    for path in user_sfx_dir.iterdir():
        if not path.is_file():
            continue
        if path.stem != kind or path.suffix.lower() not in USER_SFX_EXTS:
            continue
        if keep_resolved is not None and path.resolve() == keep_resolved:
            continue
        path.unlink(missing_ok=True)


def upsert_attribution_item(
    user_sfx_dir: Path,
    *,
    kind: str,
    file_name: str,
    license: str,
    source_name: str,
    source_url: str,
    imported_from: str,
) -> dict:
    data = load_attribution(user_sfx_dir)
    items = [i for i in data["items"] if str(i.get("kind") or "") != kind]
    entry = {
        "kind": kind,
        "key": kind,
        "file": file_name,
        "license": license,
        "source_name": source_name,
        "source_url": source_url,
        "imported_from": imported_from,
    }
    items.append(entry)
    data["items"] = sorted(items, key=lambda i: str(i.get("kind") or ""))
    save_attribution(user_sfx_dir, data)
    return entry


def import_user_sfx_file(
    user_sfx_dir: Path,
    path: Path,
    *,
    kind: str,
    source_name: str = "",
    license: str = CC0_LICENSE,
    source_url: str = "",
) -> tuple[dict | None, list[str]]:
    """Copy one wav/mp3 into user-sfx/ and record ATTRIBUTION.json. Returns (entry, errors)."""
    errors: list[str] = []
    if kind not in CC0_SFX_KINDS:
        errors.append(f"SPEC-SND-18: kind must be one of {', '.join(CC0_SFX_KINDS)}")
        return None, errors
    if not path.is_file():
        errors.append(f"SPEC-SND-18: file not found: {path}")
        return None, errors
    suffix = path.suffix.lower()
    if suffix not in USER_SFX_EXTS:
        errors.append("SPEC-SND-18: only .wav / .mp3 / .aiff are accepted")
        return None, errors
    banned = reject_banned_source(path)
    if banned:
        errors.append(banned)
        return None, errors
    license_norm = normalize_cc0_license(license)
    if license_norm is None:
        errors.append("SPEC-SND-18: license must be CC0 (Mixkit / Pixabay / Freesound)")
        return None, errors
    name = (source_name or "").strip()
    if not name:
        errors.append("SPEC-SND-18: source_name required (Mixkit / Pixabay / Freesound CC0)")
        return None, errors
    user_sfx_dir.mkdir(parents=True, exist_ok=True)
    dest = user_sfx_dir / f"{kind}{suffix}"
    if path.resolve() != dest.resolve():
        dest.write_bytes(path.read_bytes())
    clear_kind_files(user_sfx_dir, kind, keep=dest)
    entry = upsert_attribution_item(
        user_sfx_dir,
        kind=kind,
        file_name=dest.name,
        license=license_norm,
        source_name=name,
        source_url=(source_url or "").strip(),
        imported_from=str(path),
    )
    return entry, errors


def import_user_sfx_pack(
    user_sfx_dir: Path,
    pack_path: Path,
    *,
    kind: str = "",
    source_name: str = "",
    license: str = CC0_LICENSE,
    source_url: str = "",
) -> tuple[list[dict], list[str]]:
    """Import a single file (kind required) or a folder of `{kind}.wav|mp3` plus optional ATTRIBUTION.json."""
    if pack_path.is_file():
        if not kind:
            return [], ["SPEC-SND-18: kind is required when importing a single file"]
        entry, errors = import_user_sfx_file(
            user_sfx_dir,
            pack_path,
            kind=kind,
            source_name=source_name,
            license=license,
            source_url=source_url,
        )
        return ([entry] if entry else []), errors
    if not pack_path.is_dir():
        return [], [f"SPEC-SND-18: pack not found: {pack_path}"]

    pack_attr = attribution_by_kind(pack_path)
    imported: list[dict] = []
    errors: list[str] = []
    for path in sorted(pack_path.iterdir()):
        if not path.is_file() or path.suffix.lower() not in USER_SFX_EXTS:
            continue
        stem = path.stem
        if stem not in CC0_SFX_KINDS:
            continue
        meta = pack_attr.get(stem, {})
        entry, errs = import_user_sfx_file(
            user_sfx_dir,
            path,
            kind=stem,
            source_name=str(meta.get("source_name") or source_name or path.name),
            license=str(meta.get("license") or license or CC0_LICENSE),
            source_url=str(meta.get("source_url") or source_url or ""),
        )
        if errs:
            errors.extend(errs)
        elif entry:
            imported.append(entry)
    if not imported and not errors:
        errors.append("SPEC-SND-18: pack has no wav/mp3 named for a CC0 kind tag")
    return imported, errors


def list_user_sfx_items(user_sfx_dir: Path) -> list[dict]:
    attrs = attribution_by_kind(user_sfx_dir)
    items: list[dict] = []
    seen: set[str] = set()
    if not user_sfx_dir.exists():
        return items
    for path in sorted(user_sfx_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in USER_SFX_EXTS:
            continue
        kind = path.stem
        if kind in seen:
            continue
        seen.add(kind)
        meta = attrs.get(kind, {})
        items.append(
            {
                "kind": kind,
                "key": kind,
                "file": str(path),
                "user": True,
                "imported": True,
                "license": str(meta.get("license") or "").strip(),
                "source_name": str(meta.get("source_name") or "").strip(),
                "source_url": str(meta.get("source_url") or "").strip(),
            }
        )
    return items
