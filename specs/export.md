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

`review_report` returns duration, clip count, caption lint summary, mix lint summary, transition count, grade name, whether length is in 15-28s, plus structured `errors` and `warnings`.

`ok` is false and `reviewed_version` is **not** set when any of these hold:

- a still has `motion=none` and duration greater than 1.40s
- a caption center is outside 22-50%
- a caption hold is shorter than required
- music is on the timeline while `allow_music` is false
- any SFX is less than 6 dB under the bed
- duration exceeds 60.00s
- a layer is missing its media or text, or sits fully off-canvas
- an effect name is not in the registry
- a caption box or banned transition is present

A duration between 28s and 60s is a warning, not a failure.

## SPEC-EXPORT-05: export writes two files

A successful `export` writes the hero reel and a proxy alongside it. Both apply the adjustment layer after concat (SPEC-ADJ). Hero canvas stays 1080x1920.

## SPEC-EXPORT-06: same call twice

`export` with the same `op_id` does not spawn a second hero file (returns the original paths).

## SPEC-EXPORT-07: sidecar

A successful `export` writes `reel.json` next to the hero. The sidecar lists shots (source, in, out, duration, motion, crop), captions, layers, SFX (kind, at, gain), music (source name, gain, in/out), beat-grid BPM if present, total duration, grade, preset, template id, timeline version, and the hero/proxy paths. Replay of the same `op_id` returns the same sidecar path.
