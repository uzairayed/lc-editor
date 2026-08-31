# SPEC-ANA: Shot index

Source: index once at import, query at edit time. Analysis runs on the 360x640 source proxy and writes a shot manifest the agent can list, search, and rank without watching footage.

## SPEC-ANA-01: shot manifest

`Shot` fields:

- `id`: `{proxy_hash}_{index}` (zero-based, deterministic)
- `media_id`
- `in_s`, `out_s`, `duration_s` (source seconds, four decimal places)
- `keyframe`: absolute JPEG path, never base64 (SPEC-SES-13)
- `metrics`: `motion`, `sharpness`, `luma_mean`, `luma_spread`, `shake` in `[0, 1]`; `audio_rms_db` (nullable float); `audio_class` one of `engine`, `ambient`, `speech`, `silent`
- `tags`: string list, default empty (reserved for a later embedder)

Manifest JSON lives at `cache/analysis/{proxy_hash}.json`. Writes are atomic (tmp + rename). A crash mid-write leaves the previous file intact or no file, never a truncated JSON.

`in_s` / `out_s` are source seconds. They feed `clip_add(media_id, in_s, out_s)` directly.

## SPEC-ANA-02: analyze the source proxy, cache by content

`media_analyze(media_id=None)` builds the source proxy if missing (`ensure_source_proxy`) and keys the manifest by `source_proxy_hash` (path + size + mtime). Re-analyzing unchanged bytes is a no-op: `cached: [true]`, no new ffmpeg. A changed size or mtime re-analyzes.

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
- `audio_rms_db`: mean astats RMS in the shot, or `null` when silent / no audio
- `audio_class`: from level and crest. `has_audio: false` is always `silent` with `audio_rms_db: null`, never an error.

Malformed metadata lines are skipped. Empty metadata on a video (zero signalstats frames after parse, including the real ffmpeg `[Parsed_metadata @ ...] frame:` stderr form) fails that file with `SPEC-ANA-08: empty metadata` and writes no manifest. Images are unaffected.

## SPEC-ANA-05: keyframes

One JPEG per shot at source-proxy resolution under `cache/analysis/keyframes/{shot_id}.jpg`. Seek is the shot midpoint. Path is deterministic.

## SPEC-ANA-06: query tools

`shots_list(media_id?)` returns manifest rows for current media only. Missing analysis: `ok: true`, `shots: []`, warning `not analyzed`.

`shots_search` filters: `min_duration_s`, `max_duration_s`, `min_motion`, `max_motion`, `audio_class`, `kind`, `sort`, `limit`. Empty match is `ok: true` with `shots: []`. Contradictory bounds (`min > max`) are `ok: false` with a warning. Order is media capture order, then `in_s`. `sort` may be `in_s`, `motion`, or `duration_s`.

## SPEC-ANA-07: role ranking

`shots_rank(role, top_k=5, sheet=false)` with roles `hook`, `journey`, `site_wide`, `site_detail`, `closer`. Aliases: `motion` / `body` → `journey`, `wide` → `site_wide`, `detail` → `site_detail`. Prefer the aliases in new cuts. Old names stay valid.

Scoring (higher wins):

- `hook`: sharpness + mid-range luma energy. High-motion shots on the first imported file are penalized.
- `journey` / `motion`: motion only. No engine-audio bonus.
- `site_wide` / `wide`: low motion + high luma spread.
- `site_detail` / `detail`: high sharpness + low motion.
- `closer`: low motion + longer duration.

Unknown role: `ok: false`. `top_k` larger than the pool returns the whole pool, still `ok`. Ties break by `id` ascending. Response includes keyframe paths. `sheet: true` writes a contact sheet of only those keyframes under `output/rank_{role}.jpg` and returns `path`.

## SPEC-ANA-08: failure and mutation

ffmpeg failure on one file: that file gets `ok: false` treatment (warning, no manifest written). Other files in a batch still complete (per-file isolation). A single-id call that fails is `ok: false`. A batch with any failure is `ok: false` with per-file warnings, successful files kept.

All four tools return the SPEC-SES-01 envelope. None mutate the timeline (version unchanged). `media_remove` drops that media from later queries. `op_id` replay is supported on `media_analyze`. Empty project analyze is `ok: true` with `shots: 0`.

## SPEC-ANA-09: MCP surface

`media_analyze`, `shots_list`, `shots_search`, `shots_rank` are registered in `TOOLS` with named fields (SPEC-SES-10). No `**kwargs` wrapper.

## SPEC-ANA-10: performance budget

One ffmpeg decode pass per video for metrics, plus one keyframe grab per shot. Batch analysis may run files concurrently (thread pool; ffmpeg is a subprocess). Murree stills (images) analyze without a decode pass. Target: analyze + rank of the 117-still Murree folder stays inside the SPEC-SES-14 wall-time envelope when that marker runs.

## Future work

A pluggable image embedder may fill `tags` behind the `analysis` extra. The manifest shape does not change.
