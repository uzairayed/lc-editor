# SPEC-MUS: Music tracks and beat sync

Source: Production Reel Foundation v2. Complements `specs/sound.md`.

## SPEC-MUS-01: no stock catalog

The editor never ships music files. The owner imports a local file. Licensing is the owner's responsibility. Export records `source_name` and `license_note` in `reel.json`.

## SPEC-MUS-02: opt-in

`allow_music` starts false. `project_set(allow_music=true)` is legal. `music_add` without that flag is `ok: false`. A preset cannot set the flag. Turning the flag off while tracks exist is `ok: false`.

## SPEC-MUS-03: beat grid

`beat_analyze` caches `{ bpm, offset_s, beats[], downbeats[], sections[], confidence, source }`. `beat_edit` marks `source=manual`. Beats are seconds from the start of the music file (not the timeline).

## SPEC-MUS-04: snap rules

A proposed snap is rejected for that item when:

- the clip is in `protected_ids` or has `protect=true`
- the new duration would drop a caption below its hold
- the new duration is outside `min_shot_s` / `max_shot_s`
- strength is 0 (preview still returns the unsnapped times)

Subdivision `1` snaps to beats, `1/2` to half-beats, `1/4` to quarter-beats derived from BPM.

## SPEC-MUS-05: dry run

`beat_sync_preview` returns `{ ok, proposal, warnings }` and does not bump timeline version. `beat_sync_apply` commits the same proposal under `op_id`.

## SPEC-MUS-06: layout in-point

A layout is one clip (`SPEC-LAYO-02`). Snap the layout **in** (and its shared duration) as one item. Panes do not snap separately.

Caption hold still wins: a snap that drops a caption below SPEC-CAP-02 is rejected (SPEC-MUS-04). On a **caption-must** collage, stay at `max(detail, caption hold)` rather than a 1/4-beat trim.

`allow_music` stays owner opt-in. Cards that mention a bed or a track: `context/scenes/collage.md`, `ride-pair.md`.
