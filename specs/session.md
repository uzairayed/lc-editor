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

`project_create` with aspect `9:16` makes a project at 1080x1920, 30fps, `allow_music: false`.

## SPEC-SES-03: project_open / get / set / list

`project_open` loads a project directory. `project_get` returns project + summary. `project_set` updates allowed fields (name, overlay flags). Setting `allow_music` to true is `ok: false`. `project_list` lists project dirs under the workspace root.

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
2. `import_folder`
3. `media_analyze`
4. `shots_rank` per section (hook, journey, site_wide, closer); optional scoped sheet
5. `contact_sheet` of candidates, then `clip_add` enough shots to fill 15 to 28s without exceeding `ceil(duration_s * 16 / 60)` clips
6. `clip_refocus` on faces / subjects
7. `motion_kenburns` on wides
8. 5 to 7 `caption_add`
9. `audio_bed` wind, `sfx_caption_auto`, two whooshes (`sfx_place` or `sfx_transition_auto`)
10. `grade_preset` winter_trip
11. `overlay_preview` IG
12. `preview_stills`, `preview_proxy`, recut (`clip_trim` or remove), `review_report`, `export`

## SPEC-SES-09: web is read-only

Optional localhost page reads timeline JSON and stills. It has no POST that mutates the store.

## SPEC-SES-10: typed MCP schemas

Each MCP tool is bound to the real `Editor` method. The input schema lists named fields (`media_id`, `in_s`, `text`, `op_id`). A wrapper of `**kwargs` only is illegal.

## SPEC-SES-11: Python 3.11

The package installs and the unit suite runs on Python 3.11 and 3.12.

## SPEC-SES-12: optional series preset

`project_create(preset="karachi")` and `project_set(preset="karachi")` attach the Karachi series file. `project_get` exposes `preset`. Default is `null`. A preset cannot set `allow_music` true or weaken SPEC-CRAFT rules.

## SPEC-SES-13: preview files are paths

`preview_stills` and `contact_sheet` write JPEGs under the project directory and return absolute paths. The payload has no base64 image blob.

## SPEC-SES-14: Unexpected Murree acceptance

When `LC_EDITOR_MURREE_DIR` points at a folder of exactly 117 readable stills, `pytest -m murree` imports that folder (COVER-only for bursts), builds a contact sheet, cuts a winter reel, writes preview stills, reviews, and exports. Proxy must be `<= 14 MB`. Target wall time for a cold proxy is about 30s on the machine that set the variable. Private stills are never committed.
