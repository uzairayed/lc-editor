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

## SPEC-SES-05: media_list / media_remove / probe / thumbnail / contact_sheet / proxy_build

- `media_list` returns imported items with duration, size, kind, burst_cover hint
- `media_remove` unregisters; clips using that media become `ok: false` to remove-media if still referenced, or those clips are listed in warnings and the call is rejected
- `probe` returns ffprobe-derived width, height, duration, fps, has_audio
- `thumbnail` writes a JPEG
- `contact_sheet` writes a tiled JPEG of imported media
- `proxy_build` builds a per-media low-res proxy

## SPEC-SES-06: burst-COVER

Sequential stills or near-timestamp bursts mark the sharpest (or first, when no analysis extra) as `burst_cover: true`.

## SPEC-SES-07: unimplemented stubs

Until a tool is implemented it returns `ok: false` and `warnings: ["not implemented"]`.

## SPEC-SES-08: eleven-call session

A real session, in order:

1. `project_create` 9:16
2. `import_folder`
3. `contact_sheet`
4. `clip_add` 12 to 18 shots
5. `clip_refocus` on faces / subjects
6. `motion_kenburns` on wides
7. 5 to 7 `caption_add`
8. `audio_bed` wind, `sfx_caption_auto`, two whooshes (`sfx_place` or `sfx_transition_auto`)
9. `grade_preset` winter_trip
10. `overlay_preview` IG
11. `preview_stills`, `preview_proxy`, recut (`clip_trim` or remove), `review_report`, `export`

## SPEC-SES-09: web is read-only

Optional localhost page reads timeline JSON and stills. It has no POST that mutates the store.
