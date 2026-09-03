# SPEC-EXPORT: Review, proxy, export

Source: `instructions.md` Export; product spec Out tools.

## SPEC-EXPORT-01: export geometry and codec

Hero export is:

- 1080x1920
- 30fps
- H.264
- yuv420p
- AAC audio
- `+faststart`

## SPEC-EXPORT-02: proxy budget

The timeline preview encode is 540x960, `-preset veryfast`, `-crf 30`. Edit/lint reads a cached **360x640** source proxy (no LUT, no denoise). Hero export stays 1080x1920.

## SPEC-EXPORT-03: export is gated

`export` is `ok: false` unless `review_report` has been called on the **current** timeline version. After any mutation, the gate re-closes.

## SPEC-EXPORT-04: review_report

`review_report` returns duration, clip count, caption lint summary, mix lint summary, transition count, grade name, whether length is in 15-28s, zoom `{pairs, punches, skipped}`, plus structured `errors` and `warnings`.

`ok` is false and `reviewed_version` is **not** set when any of these hold:

- a still has `motion=none` and duration greater than 1.40s
- a caption center is outside 22-50%
- a caption hold is shorter than required
- music is on the timeline while `allow_music` is false
- any SFX is less than 6 dB under the bed
- duration exceeds 60.00s
- a layer is missing its media or text, or sits fully off-canvas
- a layout has the wrong pane count or missing pane media
- an effect name is not in the registry
- a caption box or banned transition is present

A duration between 28s and 60s is a warning, not a failure.

## SPEC-EXPORT-05: export writes two files

A successful `export` writes the hero reel and a proxy alongside it. Both apply the adjustment layer after concat (SPEC-ADJ). Hero canvas stays 1080x1920.

## SPEC-EXPORT-06: same call twice

`export` with the same `op_id` does not spawn a second hero file (returns the original paths).

## SPEC-EXPORT-07: sidecar

A successful `export` writes `reel.json` next to the hero. The sidecar lists shots (source, in, out, duration, motion, crop, layout, panes), captions, layers, SFX (kind, at, gain), music (source name, gain, in/out), beat-grid BPM if present, total duration, grade, preset, template id, timeline version, and the hero/proxy paths. Replay of the same `op_id` returns the same sidecar path.

## SPEC-EXPORT-08: hero encode is fixed

Hero `export` is only valid if the ffmpeg graph contains:

- `-c:v libx264`
- `-preset medium` (or slower: `slow` / `veryslow`)
- `-crf` ≤ 18
- `-s 1080x1920` (or scale to 1080x1920)
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
