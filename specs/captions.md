# SPEC-CAP: Captions

Source: `instructions.md` Timing, Captions; product spec Type tools.

Hold formula (authoritative):

```
hold_s = max(floor_s, chars / 18 + 0.4)
floor_s = 1.8 if line_count == 2 else 1.5
```

`chars` is the caption text length after stripping trailing whitespace, counting every character including spaces and punctuation. `hold_s` is rounded to two decimal places with standard half-up rounding (2.844... -> 2.84).

The same wrap + metrics path feeds `caption_lint` and render. They must never disagree.

## SPEC-CAP-01: one-line floor

A readable one-line caption is never held under 1.50s.

Worked example: text `"100 km down the N-5"` is 19 characters, 1 line.

- `19 / 18 + 0.4 = 1.46` (1.055... + 0.4)
- floor 1.50
- expected hold: **1.50**

## SPEC-CAP-02: one-line readability target

When `chars / 18 + 0.4` exceeds the 1.50 floor, that value wins.

Worked example: text `"2 hours, one fuel stop"` is 22 characters, 1 line.

- `22 / 18 + 0.4 = 1.62` (1.222... + 0.4)
- floor 1.50
- expected hold: **1.62**

## SPEC-CAP-03: two-line readability beats the 1.80 floor

Worked example: a 44-character two-line caption.

- `44 / 18 + 0.4 = 2.84` (2.444... + 0.4, rounded to two decimals)
- floor 1.80
- expected hold: **2.84**

## SPEC-CAP-04: two-line floor

Worked example: text `"Cafe Imran, Gharo"` forced onto two lines (or wrapped to two), 17 characters.

- `17 / 18 + 0.4 = 1.34`
- floor 1.80
- expected hold: **1.80**

## SPEC-CAP-05: wrap at ~26 characters, max 2 lines

Greedy word wrap at 26 characters per line. A caption that wraps to 3 or more lines is `ok: false`.

Worked example: `"600-year-old city of tombs, 2 hours from Karachi"` (48 characters) wraps to more than 2 lines and is rejected.

Worked example that passes: `"600-year-old city of tombs"` (26 characters) is one line.

## SPEC-CAP-06: ~10 words

A caption with 11 or more words is `ok: false`.

Worked example: `"one two three four five six seven eight nine ten eleven"` is rejected.

Worked example: `"2 hours, one fuel stop"` (5 words) is accepted.

## SPEC-CAP-07: no background of any kind

Any request that would add a box, banner, bar, blur pad, or scrim behind text is `ok: false`. The editor never emits `box=1` or a background filter for captions.

## SPEC-CAP-08: look tokens

Render params (locked):

- fill: `#F6EBD4` (`fontcolor=0xF6EBD4`)
- stroke: `bordercolor=0x1A1410`, `borderw=3`
- shadow: `shadowcolor=black@0.5`, `shadowx=2`, `shadowy=2`
- titles: Clash Display Semibold, else Anton
- body: Satoshi Bold, else Space Grotesk Bold
- size: 60 to 72px on 1080x1920; titles under 12 characters may use 84px

## SPEC-CAP-09: vertical safe zone

Caption center Y is inside 22% to 50% of frame height. Default is 36%. Values outside that range are `ok: false`.

On 1080x1920: Y in `[422, 960]` pixels (0.22 * 1920 = 422.4, 0.50 * 1920 = 960).

## SPEC-CAP-10: textfile, never inline apostrophes

Each caption writes one UTF-8 textfile with no trailing newline. `drawtext` uses `textfile=...:expansion=none`. Apostrophes in the text are allowed in the file; they are never interpolated into the filter string.

## SPEC-CAP-11: hold vs clip duration

If clip duration is shorter than required hold, `caption_add` / `caption_edit` is `ok: false` with a warning that the clip must be extended or the text dropped. The editor never speed-ramps to fit text.

## SPEC-CAP-12: lint is a tool

`caption_lint` returns `{ ok, timeline_summary, warnings[] }` and does not mutate. `ok` is true only when every caption on the timeline satisfies SPEC-CAP-01 through SPEC-CAP-11.
