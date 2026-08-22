# SPEC-CRAFT: Engine invariants

These rules belong to the editor. They apply to every project, including Murree. Series branding is not here.

## SPEC-CRAFT-01: no music

`allow_music` is always false. Music, melody, drum loop, score, and cinematic beds are `ok: false`.

## SPEC-CRAFT-02: no caption box

Any background, box, banner, bar, blur pad, or scrim behind text is `ok: false`.

## SPEC-CRAFT-03: caption hold and safe zone

Hold is `max(floor, chars/18 + 0.4)` with floor 1.80s (two lines) or 1.50s (one line). Caption center Y is 22% to 50%. A hold that is shorter than required is a review failure.

## SPEC-CRAFT-04: length

Target 15.00s to 28.00s (warning). Hard cap 45.00s (reject mutation and fail review).

## SPEC-CRAFT-05: locked still

A still with `motion=none` and duration greater than **1.40s** fails `review_report`. Ken Burns or punch makes the still a clip, not a slideshow.

## SPEC-CRAFT-06: SFX under the bed

SFX must sit at least 6 dB under the bed (bed treated as 0 dB when none is set). Hot SFX fails review.

## SPEC-CRAFT-07: series is a preset

A new project has `preset: null`. Karachi branding, episode cards, and no-selfie preference live in `lc_editor/presets/karachi.json` and apply only when `project_create` / `project_set` is given `preset="karachi"`. A Murree cut must pass craft rules without that preset.
