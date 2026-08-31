# SPEC-SND: Sound

Source: `instructions.md` Sound; product spec Sound tools; v2 music and beat-sync.

`allow_music` defaults to `false`. There is no music asset in the shipped pack and no stock catalog. The owner opts in with `project_set(allow_music=true)`, then imports a local audio file and places it with `music_add`.

## SPEC-SND-01: music is not SFX or a bed

Placing a music/melody/drum-loop asset as SFX, or adding a cinematic/ambient musical bed via `audio_bed`, is `ok: false`. Music is only legal through `music_add` after `allow_music` is true. `project_create` still starts with `allow_music: false`.

## SPEC-SND-02: shipped SFX only

Ride / cinematic kinds: `tick`, `pop`, `whoosh`, `impact`, `riser` (300ms noise riser), `wind`, `room`, `steps_snow`, `steps_gravel`, `engine`.

Reel / UI kinds (original wavs, not a vendor pack):

| kind | job |
| --- | --- |
| `sparkle` | bright idea / twinkle hit (~200–400 ms) |
| `swipe` | short air swipe, lighter than `whoosh` |
| `bubble` | soft bubble / pop-up |
| `button` | soft UI tap (`button` ≠ `tick`) |
| `paper` | paper rustle / page |
| `cash` | coin / register clink |
| `click` | mouse click |
| `correct` | quiz right-answer ding |
| `success` | longer success chime than `correct` |

`swipe` ≠ `whoosh`. `button` ≠ `tick`. `bubble` ≠ `pop`. `correct` and `success` are distinct wavs.

Each bundled item has `duration_s`, `file`, `kind`, and a one-line `license` (`original` or `CC0`). No vendor id field. Review warns if a placed SFX has an empty license (same spirit as music `source_name`).

`sfx_list` returns bundled items plus any files in the project user-sfx folder. No melody, no drum loop in the bundled manifest.

`sfx_zoom_auto` places a `swipe` at the start of each `zoom_in` / `zoom_out` clip. It is opt-in (speech reels stay quiet unless the agent calls it). Same call twice does not duplicate.

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

Profiles: `off | outdoor | indoor | auto`. Auto is outdoor only when `bed_kind==wind`; otherwise indoor (HP 80, nr=6, no agate, so speech is not gated). Outdoor keeps HP 120, nr=12, and agate. Muted clips skip the chain.

Tools: `audio_denoise(clip_id|"all", profile)`, `audio_gate(clip_id|"all", enabled)`.

`mix_preview` reports pre vs post peak and a wind-band estimate (80–400 Hz and 2–8 kHz). Review fails if post peak > −1.0 dBTP. Review warns if an outdoor/wind clip has denoise off.

The denoise graph never contains a music bed. Music is mixed after clip denoise (SPEC-SND-11).

## SPEC-SND-11: imported music

`import_file` accepts audio (`.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg`). The file is copied into project media with `kind=audio`. `music_add(media_id, start_s=0, in_s=0, duration_s?, gain_db=-8, fade_in_s=0.4, fade_out_s=0.8, loop=false, duck_natural=true, source_name?, license_note?)` places one music track.

- Rejects if `allow_music` is false.
- Rejects if media is not audio.
- Trim, loop, fade, and gain are stored on the track.
- When `duck_natural` is true, clip/bed audio is sidechain-ducked under the music (about 8 dB).
- Export mixes music with clip audio, bed, and SFX, then `alimiter` and optional hero `loudnorm`.

`music_update` / `music_remove` mutate the same object. `music_list` returns tracks plus beat-grid summary.

## SPEC-SND-12: picture and sound share a duration

Every hero intermediate, including stills and muted clips, emits audio of exactly `clip.duration_s` (live: `apad` + `atrim`; still/mute: `anullsrc`). `assemble` pads the mix and caps with `-t` equal to the timeline duration.

`export` probes the hero. `|audio_dur - video_dur| > 50ms` or a full-scale peak lasting more than 10 ms is `ok: false` (`SPEC-SND-12`). The sidecar records `verify`. Preview proxies stay video-only (`-an`).

## SPEC-SND-13: beat analysis

`beat_analyze(media_id)` writes a cached beat sidecar keyed by source content: BPM, offset, beat timestamps, downbeats, sections, and confidence. Automatic detection may be wrong on intros, tempo changes, and low-percussion tracks, so `beat_edit(bpm?, offset_s?, beats?)` is the correction path. Confidence below 0.45 is a review warning.

## SPEC-SND-14: beat sync

`beat_sync_preview` / `beat_sync_apply` take `strength` (0-1), `subdivision` (`1` | `1/2` | `1/4`), `min_shot_s`, `max_shot_s`, and a list of protected clip ids.

- Preview returns a dry-run proposal and does not mutate.
- Apply commits the proposal: clip out-points, transitions, caption entrances, effect starts, and SFX snap toward the nearest legal beat without shortening a caption below SPEC-CAP hold and without moving `protect` clips.
- Silent auto-sync is illegal. The agent must preview, then apply.

## SPEC-SND-15: mix with music

`mix_preview` includes music gain in the peak estimate. Music hotter than −3 dB is a warning. Post true peak still must be ≤ −1.0 dBTP. Review warns if music is present and `source_name` is empty (owner remains responsible for licensing).
