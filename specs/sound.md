# SPEC-SND: Sound

Source: `instructions.md` Sound; product spec Sound tools.

`allow_music` is always `false`. There is no music asset in the shipped pack and no API to enable music.

## SPEC-SND-01: music is rejected

Any attempt to set `allow_music: true`, place a music/melody/drum-loop asset, or add a cinematic/ambient musical bed is `ok: false`.

## SPEC-SND-02: shipped SFX only

Bundled kinds: `tick`, `pop`, `whoosh`, `impact`, `riser` (300ms noise riser), `wind`, `room`, `steps_snow`, `steps_gravel`, `engine`.

`sfx_list` returns bundled items plus any files in the project user-sfx folder. No melody, no drum loop in the bundled manifest.

`steps_snow` and `steps_gravel` are different waveforms (different SHA-256). Snow is a soft crunch. Gravel is a sharper multi-grain impact.

## SPEC-SND-03: auto tick on caption in

`sfx_caption_auto` places a `tick` (or `pop`) at each caption start that does not already have an auto tick. Same call twice does not duplicate (idempotent, or no-op when already placed).

## SPEC-SND-04: auto whoosh on decorated section cuts

`sfx_transition_auto` places a `whoosh` on `whip` and `punch` transitions (section cuts). Hard cuts do not get a whoosh unless the caller `sfx_place`s one. Same call twice does not duplicate.

## SPEC-SND-05: SFX at least 6 dB under the bed

If a placed SFX `gain_db` is greater than `bed_gain_db - 6`, `mix` lint / the place call is `ok: false`.

Worked example: bed at `-6.0` dB, SFX at `-8.0` dB is rejected (`-8 > -12`). SFX at `-12.0` dB is accepted.

When no bed is set, treat bed as `0.0` dB (clip/engine bed), so SFX must be `<= -6.0` dB.

## SPEC-SND-06: highpass

`audio_highpass(hz)` ducks rumble. Default useful value is **100** Hz. `hz <= 0` is `ok: false`.

## SPEC-SND-07: beds

`audio_bed(kind)` accepts `wind`, `room`, or `none`. Musical kinds are `ok: false` (SPEC-SND-01).

## SPEC-SND-08: duck

`audio_duck(enabled)` records a duck flag. Render ducks the bed under SFX when enabled.

## SPEC-SND-09: mix lint true peak

`mix_preview` reports estimated true peak. If true peak would exceed **0.0 dBTP**, `ok: false` with a warning. Unit tests use a deterministic estimator from gains (bed + sfx linear sum); integration tests may use ebur128 when ffmpeg is present.
