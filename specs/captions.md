# SPEC-CAP: Captions

Primary goal: people can see and finish the text on a phone at arm's length. Graphics look designed. Not CapCut karaoke. Not a slideshow box.

No caption boxes, banners, blur pads, or scrims (SPEC-CRAFT-02). No music. No word-by-word Hormozi as the default.

Hold formula (authoritative):

```
hold_s = max(floor, len(visible_chars) / 18.0 + 0.4)
floor = 1.80 if lines == 2 else 1.50
hold_s = min(hold_s, 5.0)
```

`chars` counts every character including spaces and punctuation after stripping trailing whitespace. `hold_s` is rounded to two decimal places (2.844... -> 2.84). Cap a card at **5.0s**. Split the idea instead of holding longer.

The same wrap + metrics path feeds `caption_lint` and render.

## SPEC-CAP-01: roles

- `title` — hook / series / closer. Clash Display Semibold or packaged Anton.
- `body` — facts. Satoshi Bold or packaged Space Grotesk Bold.
- One role per card. Two lines max, one idea.

## SPEC-CAP-02: attention / hold

Hold uses the formula above. Comfortable reading stays at **18 CPS + 0.4s land**. Do not chase TikTok 28 CPS.

If the clip is shorter than `hold_s`, extend the clip (`clip_fit`) or reject the caption. Never speed-ramp. Never drop below the floor.

`caption_lint` / `caption_add` fail when:

- hold is longer than the clip
- more than 2 lines
- more than 10 words
- a wrapped line is longer than 28 characters
- a line is empty

Worked examples (unchanged):

- `"100 km down the N-5"` (19 chars, 1 line): 19/18+0.4=1.46, floor 1.50 → **1.50**
- `"2 hours, one fuel stop"` (22 chars, 1 line): **1.62**
- 44-character two-line card: 44/18+0.4=2.84 → **2.84**
- `"Cafe Imran, Gharo"` forced onto two lines (17 chars): floor **1.80**
- `"600-year-old city of tombs, 2 hours from Karachi"` (48 chars) wraps past 2 lines → reject
- `"600-year-old city of tombs"` (26 chars) is one line
- 11 words → reject

## SPEC-CAP-03: placement

On 1080×1920:

- Text **center x**.
- Anchor y in **22–50%** (422–960). Default **36%** (691).
- Stay inside the cross-post safe rect: x 64–853, y 270–1248.
- Hard fail if the glyph box hits y < 270, y > 1248, or the block sits in the right action column (x > 853 as placement), or overlaps a `protect` refocus point within 80px.

`overlay_preview("ig"|"tt"|"shorts")` draws the 22–50% band, the right column, and chrome.

## SPEC-CAP-04: graphic look

| | Title | Body |
| --- | --- | --- |
| Size | 70 (84 if ≤12 chars) | 64 |
| Fill | `#F6EBD4` | `#F6EBD4` |
| Stroke | 3–4px `#1A1410` | 3px `#1A1410` |
| Shadow | 2,2 black@0.5 | same |
| Box | never | never |
| Case | sentence case | sentence case |

ALL CAPS / Hormozi shouting is `ok: false` unless a future `caption_style="punch"` is set (out of scope). Never emit `box=1`.

## SPEC-CAP-05: motion

On caption in, optional **2–4 frame** scale 100→102% (or opacity 0→1). Must finish inside the 0.4s land. No bounce, no per-word karaoke, no emoji rain.

`caption_add(..., enter="none"|"fade"|"punch")`. Default `punch` for titles, `fade` for body.

## SPEC-CAP-06: contrast lint

After placing a card, sample the underlay in the text bbox on the midpoint still.

Fail review / lint if mean underlay luminance is too close to `#F6EBD4` (both in 0.70–1.0). Suggested fix: `caption_move` to a darker band, or pick another frame. **Never suggest a box.**

White / sand plates fail. Dark plates pass.

## SPEC-CAP-07: density

Not every clip gets a card. Review **warns** if `caption_count / clip_count > 0.7` on a timeline with 8 or more clips. Warns if the first 1.5s has no title hook and the project preset is `karachi`. Other projects do not require a first-frame hook. If a title exists it must meet SPEC-CAP-02.

## SPEC-CAP-08: phone proof

`preview_stills` / `caption_lint` write a **phone proof** JPEG: the frame scaled to 270×480 (25% of 1080×1920). If stroke vanishes or text clips, lint fails. This is the arm's-length test.

## Tools

- `caption_add(clip_id, text, role, enter?)`
- `caption_edit` / `caption_move`
- `caption_lint` → `{ ok, errors[], warnings[], hold_s, lines, bbox, contrast }`
- `overlay_preview` shows IG/TT/Shorts chrome, the 22–50% band, and the right column

`caption_lint` does not mutate the timeline.
