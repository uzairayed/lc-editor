# SPEC-ANA: Media intelligence (shot index)

Source: index once at import, query at edit time. Analysis runs on the 360x640 source proxy and writes a shot manifest the agent can list, search, and rank without watching footage. No full-video VLM. Face / plate hints are out of scope for v1.

Agent workflow: **index → rank → story lock → timeline**.

1. `import_folder` / `import_file` (indexes automatically; re-run `media_analyze` is a cache no-op)
2. Optional `media_tag(shoot_day=…, role=before|wash|after|…)`
3. `shots_rank` / `shots_search` / `media_list` to pick candidates from thumbs + scores
4. Story lock: choose day/role order, then `clip_add(media_id, in_s, out_s)`

## SPEC-ANA-01: shot manifest

`Shot` fields:

- `id`: `{proxy_hash}_{index}` (zero-based, deterministic)
- `media_id`
- `in_s`, `out_s`, `duration_s` (source seconds, four decimal places)
- `keyframe`: absolute JPEG path, never base64 (SPEC-SES-13)
- `metrics`: `motion`, `sharpness`, `blur`, `luma_mean`, `luma_spread`, `shake` in `[0, 1]`; `audio_rms_db` (nullable float); `audio_class` one of `engine`, `ambient`, `speech`, `silent`
- `tags`: string list, default empty (reserved for a later embedder)

`blur` is `1 - sharpness` from the keyframe. Older manifests without `blur` derive it on load.

Manifest JSON lives at `cache/analysis/{proxy_hash}.json`. Writes are atomic (tmp + rename). A crash mid-write leaves the previous file intact or no file, never a truncated JSON.

`in_s` / `out_s` are source seconds. They feed `clip_add(media_id, in_s, out_s)` directly.

## SPEC-ANA-02: analyze the source proxy, cache by content

`media_analyze(media_id=None)` builds the source proxy if missing (`ensure_source_proxy`) and keys the manifest by `source_proxy_hash` (path + size + mtime). Re-analyzing unchanged bytes is a no-op: `cached: [true]`, no new ffmpeg. A changed size or mtime re-analyzes.

`import_file` / `import_folder` run the same cheap index automatically (SPEC-ANA-11). A later `media_analyze` on unchanged bytes stays cached.

One decode pass per video. No LUT, no denoise, no captions (same cheap rule as SPEC-SES-05). Images skip the decode pass: one still shot of `DEFAULT_STILL_S`.

## SPEC-ANA-03: segmentation invariants

scdet events split each video. Shots exactly partition `[0, duration_s]`: first starts at 0, last ends at duration, no gaps, no overlaps, no zero-length shots.

- Shots shorter than `SHOT_MIN_S` (0.5s) merge into a neighbor (previous if any, else next).
- Shots longer than `SHOT_MAX_S` (8.0s) split into equal parts of at most `SHOT_MAX_S`.
- No detected cuts: one shot, then the max-length split if needed.
- Events at `t=0` or `t=duration` are ignored.
- A video shorter than `SHOT_MIN_S` is one shot of that duration.
- Images are exactly one shot of `DEFAULT_STILL_S`.

## SPEC-ANA-04: metrics

Video, from the analysis pass plus the keyframe:

- `motion`: mean YDIF in the shot, scaled into `[0, 1]`
- `luma_mean`: mean YAVG / 255
- `luma_spread`: (YMAX - YMIN) / 255 over frames in the shot
- `shake`: YDIF variance, scaled into `[0, 1]`
- `sharpness`: Pillow FIND_EDGES variance on the keyframe, scaled into `[0, 1]`
- `blur`: `1 - sharpness`
- `audio_rms_db`: mean astats RMS in the shot, or `null` when silent / no audio
- `audio_class`: from level and crest. `has_audio: false` is always `silent` with `audio_rms_db: null`, never an error.

Malformed metadata lines are skipped. Empty metadata on a video (zero signalstats frames after parse, including the real ffmpeg `[Parsed_metadata @ ...] frame:` stderr form) fails that file with `SPEC-ANA-08: empty metadata` and writes no manifest. Images are unaffected.

## SPEC-ANA-05: keyframes

One JPEG per shot at source-proxy resolution under `cache/analysis/keyframes/{shot_id}.jpg`. Seek is the shot midpoint. Path is deterministic.

## SPEC-ANA-06: query tools

`shots_list(media_id?)` returns manifest rows for current media only. Missing analysis: `ok: true`, `shots: []`, warning `not analyzed`.

`shots_search` filters: `min_duration_s`, `max_duration_s`, `min_motion`, `max_motion`, `audio_class`, `kind`, `shoot_day`, `role`, `sort`, `limit`. Empty match is `ok: true` with `shots: []`. Contradictory bounds (`min > max`) are `ok: false` with a warning. Order is media capture order, then `in_s`. `sort` may be `in_s`, `motion`, or `duration_s`. `shoot_day` / `role` match media tags (`media_tag`).

`media_list` filters: `shoot_day`, `role`, `min_motion`. `min_motion` uses the per-media rollup max motion from the shot index (unanalyzed media are excluded). Each row includes index fields when analyzed: `motion`, `blur`, `audio_class`, `keyframe`, `shot_count`, plus `size_bytes`, `duration_s`, `captured_at`, `shoot_day`, `role`.

## SPEC-ANA-07: role ranking

`shots_rank(role, top_k=5, sheet=false, shoot_day=None)` with narrative roles `hook`, `journey`, `site_wide`, `site_detail`, `closer` and process / album roles `before`, `wash`, `detail`, `after`, `hero`, `skip_face`, `engine`, `wheel`, `interior`, `machine`.

Scoring (higher wins):

- `hook` / `hero`: sharpness + mid-range luma energy. High-motion shots on the first imported file are penalized (highway openers).
- `journey` / `engine`: motion, plus a bonus when `audio_class` is `engine` (stronger for `engine`).
- `site_wide` / `skip_face`: low motion + high luma spread (`skip_face` also prefers low blur; no face VLM).
- `site_detail` / `detail` / `before` / `wash` / `after` / `machine` / `wheel` / `interior`: high sharpness + low motion (wheel/interior also prefer low blur).
- `closer`: low motion + longer duration.

Tag-filter roles (`before`, `wash`, `after`, `machine`, `detail`, `wheel`, `interior`): when any media is tagged with that role, rank only those; otherwise fall back to the full pool with the same scorer.

Unknown role: `ok: false`. `top_k` larger than the pool returns the whole pool, still `ok`. Equal-content HD ranks above SD (source short-side boost; SPEC-QLT-01). A sub-720 candidate whose media is role-tagged (`before` / `wash` / `machine` / `after`) yields to an HD take with the same media `role` (and the same `shoot_day` if both are tagged), even when the soft clip would win on other scores. Remaining ties break by `id` ascending.

Each ranked row includes `score`, `thumb` (same as `keyframe`), `media_id`, `in_s`, `out_s`. `sheet: true` writes a contact sheet of only those keyframes under `output/rank_{role}.jpg` and returns `path`. Optional `shoot_day` limits the pool to media tagged with that day.

## SPEC-ANA-08: failure and mutation

ffmpeg failure on one file: that file gets `ok: false` treatment (warning, no manifest written). Other files in a batch still complete (per-file isolation). A single-id call that fails is `ok: false`. A batch with any failure is `ok: false` with per-file warnings, successful files kept.

`media_analyze` returns the SPEC-SES-01 envelope. Import index failures append warnings but leave import `ok: true` (media is still usable). None of these tools mutate the timeline (version unchanged). `media_remove` drops that media from later queries. `op_id` replay is supported on `media_analyze` and import. Empty project analyze is `ok: true` with `shots: 0`.

## SPEC-ANA-09: MCP surface

`media_analyze`, `shots_list`, `shots_search`, `shots_rank`, `media_list` are registered in `TOOLS` with named fields (SPEC-SES-10). No `**kwargs` wrapper. `media_list` exposes `shoot_day`, `role`, `min_motion`. `shots_search` exposes the same day/role/motion filters. `shots_rank` exposes `role`, `top_k`, `sheet`, `shoot_day`.

## SPEC-ANA-10: performance budget

One ffmpeg decode pass per video for metrics, plus one keyframe grab per shot. Batch analysis may run files concurrently (thread pool; ffmpeg is a subprocess). Murree stills (images) analyze without a decode pass. Target: analyze + rank of the 117-still Murree folder stays inside the SPEC-SES-14 wall-time envelope when that marker runs. ~50-file albums stay inside the same cheap index (no full-video VLM).

## SPEC-ANA-11: index on import

`import_file` / `import_folder` run the shot index after probe + source proxy. Response adds:

- `indexed: true`
- `shots`: total shot count written
- `cached`: per-file cache flags (same meaning as `media_analyze`)
- `sheet`: path to `output/index_sheet.jpg` (one cover keyframe per indexed item) when any keyframes exist

Media rows include `size_bytes` (source file size) and capture fields. `shoot_day` / `role` remain agent tags via `media_tag` (not inferred).

## SPEC-QLT-01: source quality floor

Cover-upscaling a sub-720 source into a 1080-class hero destroys picture. Floor is **min short side 720**. A 512×288 Day-1 phone clip fails; 1280×720 and 1080×1920 pass.

- `is_sub_720`: `0 < min(width, height) < 720`. Unknown 0×0 is not a fail.
- Canvas is 1080-class when `min(project.width, project.height) >= 1080` (default 1080×1920).
- Default clip framing is **cover**. Fit / letterbox / `fit_blur` / `fit_pad` (when present) are not cover.
- `import_file` / `import_folder` / `probe` / `media_list` / `media_analyze` warn `SPEC-QLT-01: media {id} is {W}x{H} (short side below 720); soft source` on visual sub-720 items. Import and analyze still succeed (`ok: true`).
- `media_list` and `probe` keep `width` / `height` and add `resolution` (`"1920x1080"`) and `sub_720`.
- `review_report` / export lint **warn** (never hard-block) when a clip uses cover (or default cover) AND a visual source short side is below 720 AND the canvas is 1080-class: `SPEC-QLT-01: clip {id} cover-upscales {W}x{H} into 1080 canvas (short side below 720)`. Soft sources stay exportable; agents should prefer HD or switch to fit / fit_blur.
- Sub-720 on a smaller canvas, or framed with fit / letterbox / fit_blur / fit_pad, is also a warning only. Do not block letterbox of a small source.
- `shots_rank` prefers higher-resolution sources when content scores tie, with a visible HD boost. When a candidate is sub-720 and media-role-tagged, prefer an HD take with the same media `role` (and the same `shoot_day` if both are tagged).

## Future work

A pluggable image embedder may fill `tags` behind the `analysis` extra. Optional keyframe-only face/plate hints. The manifest shape does not change for those later fields.
