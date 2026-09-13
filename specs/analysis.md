# SPEC-ANA: Media intelligence (shot index)

Source: index once at import, query at edit time. Analysis runs on the 360x640 source proxy and writes a shot manifest the agent can list, search, and rank without watching footage. No full-video VLM. Face / plate **hints in the shot index** remain out of scope for analysis v1; privacy blur on the timeline is SPEC-FX-11 (`clip_blur_*`).

Agent workflow: **index → understand (optional) → understand_timeline → highlights_suggest (optional) → rank → story lock → timeline**.

1. `import_folder` / `import_file` (indexes automatically; re-run `media_analyze` is a cache no-op)
2. Optional `media_understand` for process/album span cards (then `media_understand_refine` on uncertain spans)
3. Optional `understand_timeline` for Director role-labeled beats; optional `media_tag(shoot_day=…, role=before|wash|after|…)`
4. Optional `highlights_suggest(target_s, style=process|reel)` for ranked candidate beat sheets (suggest only; agent locks story)
5. `shots_rank` / `shots_search` / `media_list` to pick candidates from thumbs + scores (prefer understand-tagged spans)
6. Story lock: choose day/role order, then `clip_add(media_id, in_s, out_s)`

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
- `site_detail` / `detail`: high sharpness + low motion.
- `before`: sharp-enough still + low motion + lower luma (dusty / dull).
- `wash`: motion + usable sharpness + wet-work audio.
- `after` / polish: high sharpness + high luma + low motion (clean payoff).
- `machine`: motion + sharpness + engine-ish audio.
- `wheel` / `interior`: high sharpness + low motion + low blur (`interior` also prefers tighter luma spread).
- `closer`: low motion + longer duration.

Tag-filter roles (`before`, `wash`, `after`, `machine`, `detail`, `wheel`, `interior`, `engine`, `hero`, `skip_face`): understand-tagged spans for that role win the pool first; else when any media is tagged with that role, rank only those; otherwise fall back to the full pool with the same scorer.

Unknown role: `ok: false`. `top_k` larger than the pool returns the whole pool, still `ok`. Equal-content HD ranks above SD (source short-side boost; SPEC-QLT-01). A sub-720 candidate whose media is role-tagged (`before` / `wash` / `machine` / `after`) yields to an HD take with the same media `role` (and the same `shoot_day` if both are tagged), even when the soft clip would win on other scores. Remaining ties break by `id` ascending.

Each ranked row includes `score`, `thumb` (same as `keyframe`), `media_id`, `in_s`, `out_s`. `sheet: true` writes a contact sheet of only those keyframes under `output/rank_{role}.jpg` and returns `path`. Optional `shoot_day` limits the pool to media tagged with that day.

## SPEC-ANA-08: failure and mutation

ffmpeg failure on one file: that file gets `ok: false` treatment (warning, no manifest written). Other files in a batch still complete (per-file isolation). A single-id call that fails is `ok: false`. A batch with any failure is `ok: false` with per-file warnings, successful files kept.

`media_analyze` returns the SPEC-SES-01 envelope. Import index failures append warnings but leave import `ok: true` (media is still usable). None of these tools mutate the timeline (version unchanged). `media_remove` drops that media from later queries. `op_id` replay is supported on `media_analyze` and import. Empty project analyze is `ok: true` with `shots: 0`.

## SPEC-ANA-09: MCP surface

`media_analyze`, `media_understand`, `media_understand_refine`, `media_understand_spatial`, `understand_timeline`, `highlights_suggest`, `shots_list`, `shots_search`, `shots_rank`, `media_list` are registered in `TOOLS` with named fields (SPEC-SES-10). No `**kwargs` wrapper. `media_list` exposes `shoot_day`, `role`, `min_motion`. `shots_search` exposes the same day/role/motion filters (role also matches `understand:{role}` shot tags; default sort prefers understand-tagged). `shots_rank` exposes `role`, `top_k`, `sheet`, `shoot_day` (understand-tagged pool preferred). `media_understand` exposes `media_id`, `query`, `budget_frames`, `roles`, `shared_budget`, `selection`. `media_understand_refine` exposes `media_id`, `in_s`, `out_s`, `reason`, `budget_frames`, `spatial`. `media_understand_spatial` exposes `media_id`, `in_s`, `out_s`, `budget_frames`, `reason`. `understand_timeline` exposes `media_id`, `top_per_role`, `roles`, `refresh`. `highlights_suggest` exposes `target_s`, `style`, `media_id`, `refresh`.

## SPEC-ANA-10: performance budget

One ffmpeg decode pass per video for metrics, plus one keyframe grab per shot. Batch analysis may run files concurrently (thread pool; ffmpeg is a subprocess). Murree stills (images) analyze without a decode pass. Target: analyze + rank of the 117-still Murree folder stays inside the SPEC-SES-14 wall-time envelope when that marker runs. ~50-file albums stay inside the same cheap index (no full-video VLM).

`media_understand` scores at most `budget_frames` candidate keyframes per media by default (default 48, clamped 8–64). With `shared_budget=true` on an album batch, one pool (default 64, clamped 8–256) is split across imported video by duration. It does not re-decode the whole video. `media_understand_refine` extracts at most `budget_frames` extra keyframes inside one span (default 16). Adaptive selection targets `frames_scored / duration_s` far below a uniform 1fps baseline; responses expose that cost under `metrics`.

## SPEC-ANA-11: index on import

`import_file` / `import_folder` run the shot index after probe + source proxy. Response adds:

- `indexed: true`
- `shots`: total shot count written
- `cached`: per-file cache flags (same meaning as `media_analyze`)
- `sheet`: path to `output/index_sheet.jpg` (one cover keyframe per indexed item) when any keyframes exist

Media rows include `size_bytes` (source file size) and capture fields. `shoot_day` / `role` remain agent tags via `media_tag` (not inferred).

## SPEC-ANA-12: hierarchical understand (Train A)

Cheap timeline cards on top of the import index. No full-video VLM. No required large weights (CLIP/BLIP stay optional extras).

Pipeline: indexed shots → candidate spans → heuristic role scorer on candidates only → structured spans + keyframes → optional dense refine inside one span.

### `media_understand(media_id?, query?, budget_frames?, roles?, shared_budget?, selection?)`

- Default `query` is process/album understanding (`before`, `wash`, `wheel`, `interior`, `engine`, `machine`, `after`, `hero`, `skip_face`).
- `roles` overrides the query-derived role list when provided.
- Returns `spans`: list of `{media_id, in_s, out_s, role_hint, score, keyframe_path, reason, role_scores}` sorted by score desc.
- Also returns `budget_frames`, `frames_scored`, `roles`, `query`, plus Train B fields `selection`, `shared_budget`, `metrics`, `embedder`.
- Stamps matching shot `tags` with `understand:{role_hint}` and writes `cache/analysis/{proxy_hash}.understand.json`.
- Missing analysis triggers the same cheap index path as `media_analyze` for that file.
- Does not mutate the timeline.

### `media_understand_refine(media_id, in_s, out_s, reason?, budget_frames?)`

- Dense local re-sample only inside `[in_s, out_s]` when the agent is uncertain.
- Splits the span into ≤ `budget_frames` windows, extracts a midpoint keyframe per window, re-scores with parent-shot metrics + new sharpness.
- Updates understand tags on the overlapping parent shot from the best window.
- Returns the same span card shape under `spans`, plus `metrics` / `embedder`.

### Preference wiring

- `shots_rank` adds a strong score boost when a shot carries `understand:{role}` (polish ↔ after); Train C also restricts the pool to those spans when any exist.
- `shots_search(role=…)` matches media `role` tags **or** `understand:{role}` on the shot.

## SPEC-ANA-13: adaptive selection (Train B)

Training-free FOCUS/AKS-inspired picker on top of SPEC-ANA-12. Still no required large weights.

### Selection modes (`selection`)

- `adaptive` (default): FOCUS-style explore/exploit over temporal chunks (coarse pulls → fine exploit of high UCB chunks). When `query` is a concrete non-default string (not blank / `process` / `album` / `detailing` / `default`), switch to AKS-style greedy **relevance + temporal coverage**.
- `legacy`: Train A coverage grid + motion/audio peaks (`select_candidate_shots`).
- `uniform`: evenly spaced index samples (benchmark baseline).

### Album shared budget

- `shared_budget=true` with `media_id` omitted: one `budget_frames` pool (clamp 8–256) split across imported video proportional to indexed duration (small per-file floor).
- Default remains per-media budgets (Train A compatible) when `shared_budget` is false / omitted.

### Cost metrics

Every `media_understand` response includes `metrics`:

- `frames_scored`, `duration_s`, `frames_per_s`
- `uniform_1fps_frames` (ceil duration × 1fps)
- `cost_ratio_vs_uniform` (`frames_scored / uniform_1fps_frames`, target ≪ 1)
- `selection`, `shared_budget`

### Optional CLIP / BLIP

- Soft import only. Never required in the package.
- Opt-in with env `LC_EDITOR_VISION=1` (or `clip` / `blip`). Uses open_clip or transformers **only if already installable** and weights resolve with `local_files_only` (offline OK; no forced Hub download).
- When active, blends into AKS relevance; otherwise heuristics alone.
- Response `embedder`: `{enabled, clip, blip, active}`.

Out of scope for Train B: LENS spatial densify, `highlights_suggest`, PROCESS_ROLES Director feed expansion beyond Train A wiring.

## SPEC-ANA-14: process role labeling + Director feed (Train C)

Map understand spans onto PROCESS_ROLES and feed Director/agents a structured beat list. Keeps Train A/B APIs (`media_understand`, `media_understand_refine`, adaptive `selection` / `shared_budget`) intact.

### Role mapping

Default `media_understand` roles are process Director roles: `before`, `wash`, `wheel`, `interior`, `engine`, `machine`, `after`, `hero`, `skip_face`. `detail` and `polish` remain valid (`polish` ↔ `after`). Each span card includes:

- `role_hint`, `score`, `reason` (metrics + role hint + margin vs runner-up)
- `role_scores`: per-role score map used to pick the hint

Scoring is role-specific (not a single `site_detail` alias): dusty/low-luma for `before`, wet-work motion for `wash`, bright sharp payoff for `after`/`polish`, tool motion for `machine`, engine audio for `engine`, sharp stills for `wheel`/`interior`/`detail`, calm wides for `skip_face`, mid-luma hero energy for `hero`.

### Strong preference wiring

- `shots_rank`: when any shot carries `understand:{role}` (or `polish`↔`after`), the pool is those spans only; same-role understand boost is `0.45` (any-understand soft boost `0.08`).
- `shots_search(role=…)` still matches media `role` **or** `understand:{role}`. With default sort, understand-tagged matches list first.

### `understand_timeline(media_id?, top_per_role=2, roles?, refresh=false)`

Director story cards from the album/project:

- Prefers `cache/analysis/{proxy_hash}.understand.json` cards; falls back to `understand:{role}` shot tags.
- Returns `beats` (role-labeled list in process story order), `by_role`, `roles_present`, `order`, plus `spans` / `from_cache`.
- Process story order: `before` → `wash` → `engine` → `machine` → `wheel` → `interior` → `detail` → `after` → `hero` → `skip_face`.
- `refresh=true` runs `media_understand` first. Does not mutate the timeline. No separate frame-watching bot.

### MCP surface

`understand_timeline` is registered in `TOOLS` with named fields `media_id`, `top_per_role`, `roles`, `refresh`.

Out of scope for Train C: LENS spatial densify (D), `highlights_suggest` auto-edit (E).

## SPEC-ANA-15: spatial densify / LENS-lite (Train D)

When a span is high-value but spatially ambiguous (busy frame, low subject dominance), densify keyframes inside that span and soft-suggest cover `focus_x` / `focus_y`. Keeps Train A–C APIs intact. No required VLM weights (PIL edge-energy tiles only; offline OK).

### Ambiguity + high-value

- Tile the keyframe into a 3×3 edge-energy grid.
- **Dominance** = peak tile share of total energy. **Entropy** = normalized Shannon entropy of tile energies.
- Spatially ambiguous when dominance is low and entropy is high (busy / multi-subject).
- High-value spans: understand `score` ≥ floor, or top fraction of peers.

### `media_understand_spatial(media_id?, in_s?, out_s?, budget_frames?, reason?)`

- Without `in_s`/`out_s`: pick high-value ambiguous spans from understand cache (runs `media_understand` if cache empty), then densify each.
- With a span: densify only that window.
- Dense sample ≤ `budget_frames` (default 12, clamp 4–32) midpoint keyframes inside the span (same windowing as refine).
- Each densified card includes `focus_hint: {focus_x, focus_y, confidence, dominance, entropy, ambiguous, reason}`, plus `spatial_ambiguous` / `spatial_densified`.
- Writes `spatial` onto `cache/analysis/{proxy_hash}.understand.json`.
- Does not mutate the timeline. Soft suggestions only.

### Refine spatial path

`media_understand_refine(..., spatial=true)` keeps temporal densify and also annotates windows with `focus_hint`, storing the same `spatial` cache block. Default `spatial=false` preserves Train A refine behavior.

### Soft wiring (never block export)

- `clip_refocus`: when a spatial hint exists for the clip's media span, response may include `focus_hint` and a `SPEC-ANA-15` warning if cover focus drifts from the hint. Mutation still succeeds.
- `review_report`: warns when a cover clip keeps a focus that drifts from a confident spatial hint. Warnings only; export stays allowed (same soft posture as SPEC-QLT-01).

### MCP surface

`media_understand_spatial` is registered in `TOOLS` with named fields `media_id`, `in_s`, `out_s`, `budget_frames`, `reason`. `media_understand_refine` adds optional `spatial`.

Out of scope for Train D: `highlights_suggest` auto-edit (E / SPEC-ANA-16).

## SPEC-ANA-16: auto-edit assist beat sheets (Train E)

LC-native ranked candidate beat sheets from understand spans. Agent still locks the story. The tool **suggests**; it does **not** auto-export alone, does not force music, and does not require cloud or heavy VLM weights.

### `highlights_suggest(target_s, style=process|reel, media_id?, refresh=false)`

- Builds ranked `candidates[]` packed toward `target_s` (clamp ~8–180s; process default sense ~60s, reel ~28s when target omitted/invalid).
- Prefers **transformation arcs**: `before` → process ASMR middle (`wash` / `engine` / `machine` / `wheel` / `interior` / `detail`) → `after` (optional `hero`). Rank complete arcs above thin or incomplete ones.
- Prefer understand cache cards (Train A–C). Fall back to `understand:{role}` shot tags; if still empty, run `media_understand` once. `refresh=true` re-runs understand first.
- Attach soft Train D `focus_hint` when spatial cache overlaps a suggested beat.
- Detailing is often silent: speech / transcript peaks are a soft penalty for `style=process`, never a requirement. No virality / CapCut / transcript-first podcast clipping heuristics.
- Response flags: `suggest_only: true`, `auto_export: false`. Does not mutate the timeline (version unchanged).

Each candidate includes `rank`, `score`, `duration_s`, `arc`, `arc_complete`, `reason`, and `beats[]` with `role`, `section`, `media_id`, `in_s`, `out_s`, `duration_s`, `score`, `keyframe_path`, optional `focus_hint`.

### MCP surface

`highlights_suggest` is registered in `TOOLS` with named fields `target_s`, `style`, `media_id`, `refresh`.

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
