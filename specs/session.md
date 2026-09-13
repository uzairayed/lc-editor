# SPEC-SES: Session, media, MCP contract

Source: product spec Session / Media / MCP surface.

## SPEC-SES-01: mutation envelope

Every mutation returns exactly:

```
{ ok: bool, timeline_summary: object, warnings: string[] }
```

`timeline_summary` includes `version`, `clip_count`, `duration_s`, `caption_count`, `transition_count`.

Illegal operations set `ok: false`, leave the timeline unchanged, and put the reason in `warnings`. They never silently coerce (no dropping a box to "fix" a caption, no enabling music as a default).

## SPEC-SES-02: project_create canvas

`project_create` defaults to aspect `9:16` at 1080x1920, 30fps, `allow_music: false`. Aspect `16:9` makes 1920x1080. Optional `width` and `height` set a free even canvas. Unknown aspect is `ok: false`. The owner may later set `allow_music: true`. `project_get` exposes `aspect`, `width`, and `height`.

## SPEC-SES-03: project_open / get / set / list

`project_open` loads a project directory. `project_get` returns project + summary. `project_set` updates allowed fields (name, overlay flags, `allow_music`, `min_video_duration_s`, `duration_cap_s`, `caption_font`, `caption_contrast`). Setting `allow_music` false while music tracks exist is `ok: false`. `min_video_duration_s` of `0` means the default 5.0s video hold (SPEC-EDIT-25). `duration_cap_s` of `0` means the default 60.0s hard cap (SPEC-EDIT-14). `project_list` lists project dirs under the workspace root.

## SPEC-SES-04: import_file / import_folder

`import_file` registers one file (copy or hardlink into project media). `import_folder` registers every video/image in a folder (Drive stays outside; this is a local folder). Both probe and can request thumbnails. A visual source whose short side is below 720 adds a `SPEC-QLT-01` warning; import still succeeds.

On import, LC persists `captured_at` (ISO datetime) and `captured_at_source` (`probe` | `exif` | `mtime`). Source order: ffprobe `creation_time`, then EXIF `DateTimeOriginal` for stills, then file mtime. Photos/Drive export stays a local folder; there is no Drive API.

Pixel bursts named `PXL_*BURST*` are an exception: see SPEC-SES-06.

## SPEC-SES-05: media_list / media_remove / probe / thumbnail / contact_sheet / proxy_build

- `media_list` returns imported items with duration, size, kind, burst_cover, `captured_at`, `shoot_day`, `role`, plus additive `resolution` (`"1920x1080"`) and `sub_720`. Default order is `captured_at` ascending (missing dates last). Optional `shoot_day` / `role` filters; `sort="import"` keeps import order.
- `media_remove` unregisters; clips using that media become `ok: false` to remove-media if still referenced, or those clips are listed in warnings and the call is rejected
- `probe` returns ffprobe-derived width, height, duration, fps, has_audio, `captured_at` when known, and the same additive `resolution` / `sub_720` keys
- `thumbnail` writes a JPEG
- `contact_sheet` writes a tiled JPEG of imported media
- `proxy_build` / `media_proxy` writes a cached 360x640 source proxy (H.264 + AAC). No LUT, captions, or denoise. A second call with the same bytes is a no-op.
- `preview_proxy`, `preview_stills`, and `caption_lint` read the source proxy. `export` conforms the same in/out onto the originals.

## SPEC-SES-06: burst-COVER

Pixel files matching `PXL_*BURST*` are one burst. `import_folder` keeps the `COVER` frame only and skips the siblings. The response includes `imported`, `skipped`, `deduped`, and source names. Non-burst files are imported as usual.

Older `IMG_####` sequences still mark a cover hint but do not drop siblings.

## SPEC-SES-07: unimplemented stubs

Until a tool is implemented it returns `ok: false` and `warnings: ["not implemented"]`.

## SPEC-SES-08: eleven-call session

A real session, in order:

1. `project_create` 9:16
2. `import_folder` (indexes shots; optional `media_analyze` is a cache no-op)
3. Optional `media_tag` for `shoot_day` / process `role`
4. `shots_rank` per section (`hook`, `journey`, `site_wide`, `closer`, or process roles like `before` / `wash` / `after`); optional scoped sheet. Prefer `media_understand` then `understand_timeline` / `highlights_suggest` for detailing albums before ranking.
5. `contact_sheet` of candidates, then `clip_add` enough shots to fill 15 to 28s without exceeding `ceil(duration_s * 16 / 60)` clips
6. `clip_refocus` on faces / subjects (prefer soft `focus_hint` from `media_understand_spatial` when present; warn-only)
7. `motion_kenburns` on wides
8. 5 to 7 `caption_add`
9. `audio_bed` wind, `sfx_caption_auto`, two whooshes (`sfx_place` or `sfx_transition_auto`)
10. `grade_preset` winter_trip
11. `overlay_preview` IG
12. `preview_stills`, `preview_proxy`, recut (`clip_trim` or remove), `review_report`, `export`

## SPEC-SES-09: web is a localhost labeling desk

Optional `lc-editor serve --web` opens a localhost labeling desk. Timeline edits stay MCP-only. HTTP POST is allowed only for the label tools already on `Editor` (`media_card_confirm`, `shot_card_confirm`, `labels_bulk_confirm`, `labels_clear`, `labels_undo`). The HTTP layer is a thin adapter: no labeling, queue, or readiness logic of its own. Bind `127.0.0.1`. Reject cross-origin mutations. Serve only project-relative media.

## SPEC-SES-10: typed MCP schemas

Each MCP tool is bound to the real `Editor` method. The input schema lists named fields (`media_id`, `in_s`, `text`, `op_id`). A wrapper of `**kwargs` only is illegal.

## SPEC-SES-11: Python 3.11

The package installs and the unit suite runs on Python 3.11 and 3.12.

## SPEC-SES-12: optional series / process preset

`project_create(preset="karachi"|"process")` and `project_set(preset=…)` attach the matching file under `lc_editor/presets/`. `project_get` exposes `preset`. Default is `null` (short-form: 60s hard / 28s soft). A preset cannot set `allow_music` true or weaken SPEC-CRAFT rules. `preset="process"` also writes agent defaults (`duration_cap_s=180`, `caption_contrast=lenient`, `min_video_duration_s=5.0`, `loudnorm=cinema`, `allow_music=false`). `template_apply("editorial"|"karachi")` expands into ordinary layers and look; it does not hide runtime behavior.

## SPEC-SES-13: preview files are paths

`preview_stills` and `contact_sheet` write JPEGs under the project directory and return absolute paths. The payload has no base64 image blob.

## SPEC-SES-14: Unexpected Murree acceptance

When `LC_EDITOR_MURREE_DIR` points at a folder of exactly 117 readable stills, `pytest -m murree` imports that folder (COVER-only for bursts), builds a contact sheet, cuts a winter reel, writes preview stills, reviews, and exports. Proxy must be `<= 14 MB`. Target wall time for a cold proxy is about 30s on the machine that set the variable. Private stills are never committed.

## SPEC-SES-15: CLI version and doctor

`lc-editor version` prints the package version.

`lc-editor doctor` reports Python, the resolved `lc-editor` binary on PATH (`lc_editor_bin`), ffmpeg, ffprobe, MCP tool count from `TOOLS`, and whether `project_create` / `import_file` / `import_folder` / `clip_add` / `export` exist (MCP tools-registered smoke). Optional `--project` is a dry smoke: it reports whether the project exists or can be created. It does not encode or export. Exit `0` when the report is ok, else `1`. Missing `lc-editor` on PATH does not fail `ok` by itself; stdout still warns that tools will be invisible until AddMcpServer / PATH fix.

Stdout always prints copy-paste MCP JSON for Grok Bot (`command` + `args: ["serve"]` + `env`) and Cursor (`mcpServers`). This is the attach path for #29 / #32. After `pip install -U lc-editor`, restart MCP in the client (Cursor: RestartMcpServers; Grok Bot: re-attach). There is no RestartMcpServers CLI.

`lc-editor serve --project …` is unchanged. MCP clients attach stdio with command `lc-editor` (or the resolved binary from doctor) and args `serve` (optional `--project <absolute path>`). Plugin `mcp.json` pins that serve command so a package upgrade does not drop the connector.

## SPEC-SES-16: shoot day / role tags

`media_tag(media_id, shoot_day=..., role=...)` sets additive inventory fields. `shoot_day` is an int or a `day1`-style label. `role` is a free hint (`before` | `wash` | `machine` | `after` | other). Old projects without these fields still load (defaults). `review_report` warns `media missing captured_at` when any imported item has no capture date; that is not an error and does not block export.

Multi-day albums: inventory (`import_folder` + `media_list`) → tag days/roles (`media_tag`) → lock the timeline → `review_report` → `export`.
