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

`audio_highpass(hz)` ducks rumble. Outdoor default **120** Hz, indoor **80** Hz. `hz <= 0` is `ok: false`.

## SPEC-SND-07: beds

`audio_bed(kind)` accepts `wind`, `room`, or `none`. Musical kinds are `ok: false` (SPEC-SND-01).

## SPEC-SND-08: duck

`audio_duck(enabled)` records a duck flag. Render ducks the bed under SFX when enabled.

## SPEC-SND-09: mix lint true peak

`mix_preview` reports pre and post true peak. Post must be **≤ −1.0 dBTP**. The mix ends with `alimiter`. Optional `loudnorm` I=−16, TP=−1.5, LRA=8 on the hero only.

## SPEC-SND-10: denoise chain

Every unmuted clip (and the bed) runs a denoise chain unless `audio_denoise(..., "off")`.

Order: highpass, spectral `afftdn` (nr=12 outdoor / nr=6 indoor), `agate` attack 10 ms release 200 ms, then mix `alimiter` to −1.0 dBTP.

Profiles: `off | outdoor | indoor | auto`. Auto is outdoor unless `bed_kind==room`. Muted clips skip the chain.

Tools: `audio_denoise(clip_id|"all", profile)`, `audio_gate(clip_id|"all", enabled)`.

`mix_preview` reports pre vs post peak and a wind-band estimate (80–400 Hz and 2–8 kHz). Review fails if post peak > −1.0 dBTP. Review warns if an outdoor/wind clip has denoise off.

The denoise graph never contains a music bed.
