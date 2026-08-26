# SPEC-CRAFT: Engine invariants

These rules belong to the editor. They apply to every project, including Murree. Series branding is not here.

## SPEC-CRAFT-01: sound policy belongs to the owner

Music is an owner preference, not an engine opinion. An agent driving this editor must ask the project owner what they want for sound instead of assuming.

`allow_music` defaults to **false**. The owner may set it true with `project_set(allow_music=true)`. Music is a first-class imported track (`music_add`), never an SFX kind and never a cinematic/ambient bed. Bundled SFX and `audio_bed` stay non-musical. A preset cannot turn music on. Placing music while `allow_music` is false is `ok: false`. Review warns if music is present without source attribution.

## SPEC-CRAFT-02: no caption box

Any background, box, banner, bar, blur pad, or scrim behind text is `ok: false`.

## SPEC-CRAFT-03: caption hold and safe zone

Hold is `max(floor, chars/18 + 0.4)` with floor 1.80s (2 or 3 lines) or 1.50s (one line), capped at 5.0s. The **glyph block** (not only the `y_pct` anchor) must stay inside the 22% to 50% band and inside the 1080x1920 frame. A hold that is shorter than required, or a bbox that clips the frame or the band, is a review failure. See `specs/captions.md`.

## SPEC-CRAFT-04: length

Target 15.00s to 28.00s (warning). Hard cap 60.00s (reject mutation and fail review).

## SPEC-CRAFT-05: locked still

A still with `motion=none` and duration greater than **1.40s** fails `review_report`. Ken Burns or punch makes the still a clip, not a slideshow.

## SPEC-CRAFT-06: SFX under the bed

SFX must sit at least 6 dB under the bed (bed treated as 0 dB when none is set). Hot SFX fails review.

## SPEC-CRAFT-08: outdoor audio is denoised

Ride wind is not a highpass-only problem. Outdoor audio uses SPEC-SND-10. SPEC-CRAFT-01 still applies.

## SPEC-CRAFT-07: series is a preset

A new project has `preset: null`. Karachi branding, episode cards, and no-selfie preference live in `lc_editor/presets/karachi.json` and apply only when `project_create` / `project_set` is given `preset="karachi"`. A Murree cut must pass craft rules without that preset.
