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

Preview / export proxy is 540x960, `-preset veryfast`, `-crf 30`. Size target **8 to 14 MB** for a reel up to 45s. Builder must use these encode args (integration asserts args and, when ffmpeg is present, file existence).

## SPEC-EXPORT-03: export is gated

`export` is `ok: false` unless `review_report` has been called on the **current** timeline version. After any mutation, the gate re-closes.

## SPEC-EXPORT-04: review_report

`review_report` returns duration, clip count, caption lint summary, mix lint summary, transition count, grade name, and whether length is in 15-28s. Calling it records `reviewed_version = timeline.version`.

## SPEC-EXPORT-05: export writes two files

A successful `export` writes the hero reel and a proxy alongside it.

## SPEC-EXPORT-06: same call twice

`export` with the same `op_id` does not spawn a second hero file (returns the original paths).
