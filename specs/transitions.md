# SPEC-TRN: Transitions

A reel at or under **60s** earns at most **3** decorated transitions (soft target still 15–28s). Hard cut is the default. Video wipes stay banned (SPEC-RND-03).

## Allowed

| id | Video | Audio |
| --- | --- | --- |
| cut / hard | concat, no xfade | 8–12 ms acrossfade (default 10 ms, 0 allowed) |
| fade | luma crossfade, 4–12 frames typical (default 8) | whoosh optional |
| whip | directional blur + translate, 6–10 frames, blur peaks mid, ease in/out | whoosh optional |
| punch | 4-frame 108% on incoming | |
| close_fade | 4-frame luma on last clip only | |
| j_cut | hard picture | next audio leads 8–12 frames |
| l_cut | hard picture | outgoing audio hangs 8–12 frames |
| flash | 1–2 frame sand flash, opacity ≤ 0.35 | |
| match | hard cut + 2-frame zoom settle (optional; skip when unsure) | |

Decorated: fade, whip, punch, close_fade, j_cut, l_cut, flash, match. Mutation **warns** and `review_report` **fails** if decorated count > 3.

## Banned

`xfade` wipe/slide/circleopen/dissolve between unrelated shots, star wipes, spins, packs, beat-sync, anything that needs music. Whip is not `wiperight`. Pack `fade` is a short intentional luma crossfade, not a slideshow dissolve.

## Tools

`transition_set(from_clip_id|clip_id|from_id|at_s, kind, duration_s?)`

- `cut` clears to hard. `hard` remains an alias of `cut`.
- `from_clip_id` / `clip_id` / `from_id` name the outgoing clip (transition into the next).
- `at_s` picks the outgoing clip whose end boundary is nearest that time.
- `duration_s` optional; fade clamps to 4–12 frames at 30fps, whip to 6–10.

Agent rule: use decorated transitions only at section boundaries (for process cards: before→process and process→after). Never every cut. Default stays hard cut.
`transition_audio_xfade(ms)` default 10.
