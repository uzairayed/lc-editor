# SPEC-SES: Session, media, MCP contract

Source: product spec Session / Media / MCP surface.

## SPEC-SES-01: mutation envelope

Every mutation returns exactly:

```
{ ok: bool, timeline_summary: object, warnings: string[] }
```

`timeline_summary` includes `version`, `clip_count`, `duration_s`, `caption_count`, `transition_count`.

Illegal operations set `ok: false`, leave the timeline unchanged, and put the reason in `warnings`. They never silently coerce (no dropping a box to "fix" a caption, no enabling music as a default).

## SPEC-SES-02: project_create 9:16

`project_create` with aspect `9:16` makes a project at 1080x1920, 30fps, `allow_music: false`. The owner may later set `allow_music: true`.

## SPEC-SES-03: project_open / get / set / list

`project_open` loads a project directory. `project_get` returns project + summary. `project_set` updates allowed fields (name, overlay flags, `allow_music`, `subject`, `target_duration_s`, `caption_mode`). Setting `allow_music` false while music tracks exist is `ok: false`. `project_list` lists project dirs under the workspace root.

## SPEC-SES-04: import_file / import_folder

`import_file` registers one file (copy or hardlink into project media). `import_folder` registers every video/image in a folder (Drive stays outside; this is a local folder). Both probe and can request thumbnails.

Pixel bursts named `PXL_*BURST*` are an exception: see SPEC-SES-06.

## SPEC-SES-05: media_list / media_remove / probe / thumbnail / contact_sheet / proxy_build

- `media_list` returns imported items with duration, size, kind, burst_cover hint
- `media_remove` unregisters; clips using that media become `ok: false` to remove-media if still referenced, or those clips are listed in warnings and the call is rejected
- `probe` returns ffprobe-derived width, height, duration, fps, has_audio
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
2. Ask the owner (SPEC-SES-15) and `project_set` the brief
3. `import_folder`
4. `media_analyze`
5. `shots_rank` per need (`hook`, `wide` / `site_wide`, `detail` / `site_detail`, `closer`); optional scoped sheet
6. `contact_sheet` of candidates, then `clip_add` enough shots to fill the owner's target (or 15 to 28s) without exceeding `ceil(duration_s * 16 / 60)` clips
7. `clip_refocus` on faces / subjects
8. Motion only where the shot needs it (`kenburns` on stills, `punch` / `zoom_in` as punctuation)
9. Captions only if the owner asked for them (sparse or caption-must)
10. Sound from the owner's answer: natural bed, or `project_set(allow_music=true)` then music
11. `grade_preset` `neutral` unless the owner asked for another look
12. `preview_stills`, `preview_proxy`, recut (`clip_trim` or remove), `review_report`, `export`

## SPEC-SES-15: ask before the first cut

An agent must ask the owner these four things before the first `clip_add`, unless the owner already answered in the prompt:

1. Subject (what the reel is about)
2. Duration (a number; default 15 to 28s; hard cap 60s)
3. Sound (music, or natural audio only)
4. Captions (`sparse` or `caption_must`)

Store the answers with `project_set(subject=..., target_duration_s=..., caption_mode=...)`. `allow_music` stays false until they ask for music. Do not assume a series structure, a ride, or a grade. `target_duration_s` must be in `(0, 60]`. `caption_mode` is `sparse` or `caption_must`.

## SPEC-SES-09: web is read-only

Optional localhost page reads timeline JSON and stills. It has no POST that mutates the store.

## SPEC-SES-10: typed MCP schemas

Each MCP tool is bound to the real `Editor` method. The input schema lists named fields (`media_id`, `in_s`, `text`, `op_id`). A wrapper of `**kwargs` only is illegal.

## SPEC-SES-11: Python 3.11

The package installs and the unit suite runs on Python 3.11 and 3.12.

## SPEC-SES-12: optional series preset

`project_create(preset="karachi")` and `project_set(preset="karachi")` attach the Karachi series file. `project_get` exposes `preset`. Default is `null`. A preset cannot set `allow_music` true or weaken SPEC-CRAFT rules. `template_apply("editorial"|"karachi")` expands into ordinary layers and look; it does not hide runtime behavior.

## SPEC-SES-13: preview files are paths

`preview_stills` and `contact_sheet` write JPEGs under the project directory and return absolute paths. The payload has no base64 image blob.

## SPEC-SES-14: Unexpected Murree acceptance

When `LC_EDITOR_MURREE_DIR` points at a folder of exactly 117 readable stills, `pytest -m murree` imports that folder (COVER-only for bursts), builds a contact sheet, cuts a winter reel, writes preview stills, reviews, and exports. Proxy must be `<= 14 MB`. Target wall time for a cold proxy is about 30s on the machine that set the variable. Private stills are never committed.
