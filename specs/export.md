# SPEC-EXPORT: Review, proxy, export

Source: `instructions.md` Export; product spec Out tools.

## SPEC-EXPORT-01: export geometry and codec

Hero export is:

- project canvas (1080x1920 for 9:16, 1920x1080 for 16:9)
- 30fps
- H.264
- yuv420p
- AAC audio
- `+faststart`

## SPEC-EXPORT-02: proxy budget

The timeline preview encode is half the project canvas (540x960 on 9:16, 960x540 on 16:9), `-preset veryfast`, `-crf 30`. Edit/lint reads a cached **360x640** source proxy (no LUT, no denoise). Hero export uses the project canvas.

## SPEC-EXPORT-03: export is gated

`export` is `ok: false` unless `review_report` has been called on the **current** timeline version. After any mutation, the gate re-closes.

## SPEC-EXPORT-04: review_report

`review_report` returns duration, the active `duration_cap_s`, clip count, caption lint summary, mix lint summary, transition count, grade name, whether length is in 15-28s, zoom `{pairs, punches, skipped}`, plus structured `errors` and `warnings`.

`ok` is false and `reviewed_version` is **not** set when any of these hold:

- a caption center is outside 22-50%
- a caption hold is shorter than required
- music is on the timeline while `allow_music` is false
- any SFX is less than 6 dB under the bed
- duration exceeds the project `duration_cap_s` (default 60.00s)
- a layer is missing its media or text, or sits fully off-canvas
- a layout has the wrong pane count or missing pane media
- an effect name is not in the registry
- a caption box or banned transition is present
- a video clip is shorter than the project `min_video_duration_s` floor (SPEC-EDIT-25), unless it holds its entire source
- sand underlay contrast (SPEC-CAP-06) when `caption_contrast="strict"` only

Warnings (do **not** block export): locked still over 1.40s (SPEC-CRAFT-05), CAP-06 under default `caption_contrast="lenient"`, SPEC-QLT-01 soft sources (cover-upscales into 1080, or sub-720 with fit / fit_blur / fit_pad / letterbox / non-1080 canvas), SPEC-ANA-15 spatial cover-focus hints, and SPEC-SND-12 short-source auto-hold.

Decorated transitions (`fade` / `whip` / …) render on `export` presets `reel`, `share`, and `phone`. Cap remains 3 decorated (`SPEC-EDIT-13`); excess fails review before export.

A duration between the soft target and the configured cap is a warning, not a failure. Soft target is 28s by default; when `duration_cap_s` is raised above the default 60s hard cap, that cap is the soft target (SPEC-EDIT-15). When the cap is above 60s, duration over 60s is still a SPEC-EDIT-15 warning until the configured cap. SPEC-QLT-01 never fails export. `export` re-checks SPEC-EDIT-25 even if `reviewed_version` matches, so older timelines fail closed.

## SPEC-EXPORT-05: export writes two files

A successful `export` writes the hero reel and a proxy alongside it. Both apply the adjustment layer after concat (SPEC-ADJ). Hero canvas matches the project.

## SPEC-EXPORT-06: same call twice

`export` with the same `op_id` does not spawn a second hero file (returns the original paths).

## SPEC-EXPORT-07: sidecar

A successful `export` writes `reel.json` next to the hero. The sidecar lists shots (source, in, out, duration, motion, crop, layout, panes), captions, layers, SFX (kind, at, gain), music (source name, gain, in/out), beat-grid BPM if present, total duration, grade, preset, template id, timeline version, and the hero/proxy paths. Replay of the same `op_id` returns the same sidecar path.

## SPEC-EXPORT-08: hero encode is fixed

Hero `export` is only valid if the ffmpeg graph contains:

- `-c:v libx264`
- `-preset medium` (or slower: `slow` / `veryslow`)
- `-crf` ≤ 18
- `-s` matching the project canvas (1080x1920 or 1920x1080)
- `-pix_fmt yuv420p`
- `-c:a aac` `-ar 48000` `-ac 2`

Banned as the delivered hero: `veryfast`, `ultrafast`, `superfast`, CRF > 18, 540×960 / 360×640 canvas, a source-proxy path written to `reel.mp4`, `-shortest` on a 1080 hero.

If the runner cannot hold that (timeout, OOM, killed), `export` is `ok: false` with a clear error. Do not substitute the preview proxy or a faster preset and return success.

The sidecar records `encode: {preset, crf, width, height, pix_fmt}`.

## SPEC-EXPORT-09: one hero encode per machine

`export` takes a process-wide lock (`/tmp/lc-editor-hero-export.lock`).

- A second `export` waits, or returns `ok: false` with `hero_export_busy` if `wait=false`.
- Default: wait.
- Source-proxy builds and 360p/540p previews do not take this lock. The 1080 hero does.

## SPEC-EXPORT-10: share / phone delivery preset

`export(preset=)` selects the encode:

| `preset` | File | Size | Notes |
|----------|------|------|-------|
| `reel` (default) | `reel.mp4` | project canvas (1080×1920 or 1920×1080) | Hero. SPEC-EXPORT-08. Also writes `reel_proxy.mp4`. |
| `share` / `phone` | `reel_share.mp4` | 720×1280 (9:16) or 1280×720 (16:9) | Delivery, not hero. CRF 22, AAC 128k, `+faststart`, `yuv420p`, tv-range. |

`share` and `phone` are aliases. They write a sibling file and never replace `reel.mp4`. Same assemble graph as hero; only the final encode args change. Share is not validated as hero (CRF 22 and 720p fail SPEC-EXPORT-08).

Share takes the same process-wide lock as hero, sequentially: `export(preset="share")` waits if a 1080 hero is running (or `hero_export_busy` when `wait=false`). Never run share in parallel with another 1080. Call `export()` for the hero, then `export(preset="share")` to attach a chat-sized file.

Target: about ≤40MB for a 60–90s reel. The review gate (SPEC-EXPORT-03) still applies.

## SPEC-EXPORT-11: YouTube SDR upload master

`export(preset="youtube")` writes `youtube.mp4` and `youtube.json` without
replacing reel/share outputs. The project canvas is preserved; a YouTube
project defaults to 1920×1080. The encode is MP4, H.264 High Profile,
progressive yuv420p, closed GOP with two B-frames, BT.709 limited range,
AAC-LC 48kHz stereo at 384kbps, and fast-start metadata.

YouTube export supports `caption_mode="burned"|"sidecar"|"both"|"none"`.
Sidecar captions are written as UTF-8 `youtube.srt`. Optional title,
description, and chapters are validated against YouTube limits and recorded
in `youtube.json`; export does not upload or publish.

The output is encoded to `youtube.tmp.mp4`, verified with ffprobe, and
atomically moved into place so failure cannot destroy a previous valid
upload master. Verification checks streams, geometry, progressive scan,
pixel/color format, 48kHz stereo audio, A/V sync, the 12-hour duration cap,
and the 256GB file cap. Videos over 15 minutes warn that account verification
is required. Square/vertical videos up to three minutes warn that YouTube may
classify them as Shorts.

HDR sources fail closed because this version has no explicit SDR tone-map or
10-bit HDR output path. Interlaced sources are deinterlaced before conform.
