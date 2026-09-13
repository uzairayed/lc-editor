# lc-editor

Use this skill when asked to cut reels from raw video clips. The `lc-editor` MCP server gives you tool calls to build a timeline; ffmpeg does the rendering. Default canvas is 9:16; 16:9 product demos use `project_create(aspect="16:9")`.

## When to use

- User asks you to edit video clips into a short reel
- User asks for 9:16 vertical or 16:9 landscape video editing
- User mentions cutting, trimming, or assembling footage

## Quick start

The MCP server is `lc-editor`. Call its tools to build and export your reel.

## If MCP tools are missing

Do **not** fall back to raw ffmpeg while `lc-editor doctor` is green. This is the #29 / #32 attach path.

1. Run `lc-editor doctor` (and `lc-editor doctor --project <abs path>` if you have a project). Confirm `lc_editor_bin`, ffmpeg/ffprobe, `mcp_tools` ~100, and `project_create` / `import_file` / `import_folder` / `clip_add` / `export` read `ok`. Doctor prints copy-paste Grok Bot / Cursor MCP JSON (`command` + `args: ["serve"]` + `env`).
2. Attach with that JSON. Pin **command** to the resolved `lc_editor_bin` (or `lc-editor` on PATH) and **args** `serve`. Plugin `mcp.json` already pins this so upgrades do not drop the connector. On Windows use `C:/Users/you/my-reel` or escaped backslashes if you add `--project`.
3. After `pip install -U lc-editor`, restart MCP: Cursor **RestartMcpServers** (or a new agent session); Grok Bot: re-attach (`AddMcpServer`). There is no RestartMcpServers CLI. Then confirm `project_create` is callable.
4. Fall back to ffmpeg only if doctor is **red** (missing ffmpeg, no MCP entrypoints) and you have told the owner LC is not attached. If only `lc_editor_bin` is missing, tools stay invisible until PATH / AddMcpServer — do not invent ffmpeg graphs yet; paste doctor's JSON.

## Workflow

1. **Inventory / index on import.** Use `import_folder` or `import_file`. Import probes duration / size / capture date, builds the source proxy, and runs the cheap shot index (keyframes, shot bounds, motion / blur / audio-class) cached by content hash. Response includes `shots`, `sheet` (`output/index_sheet.jpg`), and per-file `cached`. Call `media_list` (sorted by capture date; filter `shoot_day` / `role` / `min_motion`) before you cut. Re-run `media_analyze` only to refresh; unchanged bytes are a no-op.

2. **Rank, then lock the story.** For multi-day albums (detailing, travel), `media_tag(media_id, shoot_day=1, role="before")` so Day 1 dusty → wash → machine → after stays inside LC. Then `shots_rank(role=…)` / `shots_search` to pick shots without opening every file. Narrative roles: `hook`, `journey`, `site_wide`, `site_detail`, `closer`. Process roles: `before`, `wash`, `detail`, `after`, `hero`, `skip_face`, `engine`, `wheel`, `interior`, `machine`. Ranked rows include `media_id`, `in_s` / `out_s`, `score`, `thumb`. Look at keyframes with `thumbnail` or `contact_sheet`. `clip_add` in tagged day/role order.

3. **Ask about sound before touching the timeline.** Sound is the owner's call, not yours. Ask: "Do you want music or natural audio only?" Do not assume either way.
   - If music: call `project_set(allow_music=true)`, import the track, `music_add`, `beat_analyze`, show `beat_sync_preview`, then `beat_sync_apply` only after the user confirms.
   - If natural audio: proceed without music tools.
   - For reel UI SFX: prefer owner CC0 files via `sfx_import` / `sfx_pack_add` (Mixkit / Pixabay / Freesound only). Never CapCut rips. Imported keys show in `sfx_list` and win over built-ins in `sfx_place`.

4. **Match subjects to scene cards.** When you look at keyframes or set clip durations/roles, consult `context/INDEX.md` and read only the matching scene cards. The process is in `context/HOW.md`.

5. **Build the timeline.** Use `clip_add`, trim, split, reorder, motion, and transitions. An occasional two-up is `context/scenes/pair.md`. A reel that is mostly stacks is `context/scenes/collage.md`. Two ride POVs is `context/scenes/ride-pair.md`. Add layers or apply a template if needed.

6. **Privacy blur after story lock.** Scan keyframes or use `shots_rank(role="skip_face")` / tagged skip. If a kept clip still shows a face or plate, call `clip_blur_add` (`kind=face|plate|region`) before review. Prefer an explicit `region` box from the frame you inspected. Never invent boxes: if unsure, ask or skip. Auto-detect is local Haar only (no cloud VLM); missing detections warn and apply nothing.

7. **Run `review_report` before export.** Fix every warning it returns. `media missing captured_at` is a warning only - backfill from `probe` if you still need day order.

8. **Show preview stills at each pass.** Use `preview_stills` so the user can see progress.

## Key constraints

- Canvas: project aspect, 30fps. Default 9:16 (1080×1920). `project_create(aspect="16:9")` is 1920×1080. Landscape sources use `clip_set_fit` (`cover` / `fit` / `fit_pad` / `fit_blur`); do not hand-build ffmpeg letterbox.
- Captions: stroke-and-shadow text only, never a box / banner / scrim
- Product, process, or ambient reels: `caption_add(..., style="card")` — 2–3 line scene cards, Clash Display. Do not use `pop` or `karaoke` unless the clip is spoken-word
- Clash Display: `font="clash"` on `caption_add` / `caption_edit` / `text_style`, or `project_set(caption_font="clash")`. Packaged fallback is Anton. Never raw ffmpeg drawtext
- Templates: `editorial` and `karachi` (apply expands to ordinary layers)
- Music is opt-in only via `project_set(allow_music=true)`
- Engine rules in `specs/craft.md` are floors; scene-card judgment can raise them but never lower them

## Tools overview

Every edit returns `{ ok, timeline_summary, warnings }`. Illegal requests fail out loud. Same `op_id` twice does not duplicate.

**Media:** `import_file`, `import_folder`, `media_list`, `media_tag`, `probe`

**Timeline:** `clip_add`, `clip_remove`, `clip_reorder`, `clip_trim`, `clip_split`, `clip_set_duration`, `clip_fit` (duration hold), `clip_set_fit` (visual cover/letterbox), `clip_refocus`

**Privacy blur:** `clip_blur_add` (`face`|`plate`|`region`), `clip_blur_update`, `clip_blur_remove`, `clip_blur_list` (soft-mask after fit; SPEC-FX-11)

**Motion:** `motion_kenburns`, `motion_punch`, `motion_zoom_in`, `motion_zoom_out`, `motion_none`, `motion_hold`

**Layouts:** `layout_add("stack_v"|"stack_h"|"stack_v3"|"grid_2x2", panes=[...])`, `layout_pane`, `layout_clear`

**Layers:** `layer_add`, `layer_update`, `layer_remove`, `layer_reorder`, `layer_transform`, `layer_keyframe`

**Effects:** `effect_add`, `effect_update`, `effect_remove` (blur, sharpen, glow, grain, vignette, lut, color)

**Text:** `caption_add` (`style="card"` for process/product; `phrase` same card filters; `pop`/`karaoke` spoken-word only; `font="clash"`), `caption_edit`, `caption_move`, `caption_remove`, `caption_lint`, `text_style` (fade, pop, slide, type-on; `font="clash"`)

**Music:** `music_add`, `beat_analyze`, `beat_edit`, `beat_sync_preview`, `beat_sync_apply`

**SFX:** `sfx_list`, `sfx_import` / `sfx_pack_add` (CC0 wav/mp3 into project `user-sfx/` + `ATTRIBUTION.json`), `sfx_place`, `sfx_caption_auto`, `sfx_transition_auto`, `sfx_zoom_auto`

**Templates:** `template_list`, `template_apply`, `template_save`

**Review & Export:** `review_report`, `export`
