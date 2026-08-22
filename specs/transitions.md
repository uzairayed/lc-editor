# SPEC-TRN: Transitions

A reel at or under 28s earns at most **3** decorated transitions. Hard cut is the default. Video wipes stay banned (SPEC-RND-03).

## Allowed

| id | Video | Audio |
| --- | --- | --- |
| hard | concat, no xfade | 8–12 ms acrossfade (default 10 ms, 0 allowed) |
| whip | directional blur + translate, 6–10 frames, blur peaks mid, ease in/out | whoosh optional |
| punch | 4-frame 108% on incoming | |
| close_fade | 4-frame luma on last clip only | |
| j_cut | hard picture | next audio leads 8–12 frames |
| l_cut | hard picture | outgoing audio hangs 8–12 frames |
| flash | 1–2 frame sand flash, opacity ≤ 0.35 | |
| match | hard cut + 2-frame zoom settle | |

Decorated: whip, punch, close_fade, j_cut, l_cut, flash, match. Review **fails** if decorated count > 3.

## Banned

`xfade` wipe/slide/circleopen/dissolve between unrelated shots, star wipes, spins, packs, beat-sync, anything that needs music. Whip is not `wiperight`.

## Tools

`transition_set(clip_id, kind)` accepts the ids above. `from_id` is an alias for `clip_id`.
`transition_audio_xfade(ms)` default 10.
