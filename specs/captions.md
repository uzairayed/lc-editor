# SPEC-CAP: Captions

Primary goal: people can see and finish the text on a phone at arm's length. Graphics look designed. Not CapCut karaoke. Not a slideshow box.

No caption boxes, banners, blur pads, or scrims (SPEC-CRAFT-02). No word-by-word Hormozi as the default. Music is independent of caption style (SPEC-SND-11).

Hold formula (authoritative):

```
hold_s = max(floor, len(visible_chars) / 18.0 + 0.4)
floor = 1.80 if lines >= 2 else 1.50
hold_s = min(hold_s, 5.0)
```

`chars` counts every character including spaces and punctuation after stripping trailing whitespace. `hold_s` is rounded to two decimal places (2.844... -> 2.84). Cap a card at **5.0s**. Split the idea instead of holding longer.

The same wrap + metrics path feeds `caption_lint` and render. Render writes the **wrapped** textfile (newlines, UTF-8, no trailing newline, `expansion=none`) and sets drawtext `boxw` to the usable cross-post width (789). Never emit `box=1`.

## SPEC-CAP-01: roles

- `title` — hook / series / closer. Clash Display Semibold or packaged Anton. Titles stay shorter.
- `body` — facts and 2 to 3 line explainers. Satoshi Bold or packaged Space Grotesk Bold.
- One role per card. **Max 3 lines**, one idea. Still not a paragraph.

## SPEC-CAP-02: attention / hold

Hold uses the formula above. Comfortable reading stays at **18 CPS + 0.4s land**. Do not chase TikTok 28 CPS. The **1.80s floor** applies to any card with 2 or 3 lines.

If the clip is shorter than `hold_s`, extend the clip (`clip_fit`) or reject the caption. Never speed-ramp. Never drop below the floor. Hold is checked for 3-line cards too.

`caption_lint` / `caption_add` fail when:

- hold is longer than the clip
- more than 3 lines
- more than 16 words
- a wrapped line is longer than 28 characters
- a line is empty

Worked examples:

- `"100 km down the N-5"` (19 chars, 1 line): 19/18+0.4=1.46, floor 1.50 → **1.50**
- `"2 hours, one fuel stop"` (22 chars, 1 line): **1.62**
- 44-character two-line card: 44/18+0.4=2.84 → **2.84**
- `"Cafe Imran, Gharo"` forced onto two lines (17 chars): floor **1.80**
- `"600-year-old city of tombs, 2 hours from Karachi"` (48 chars) wraps to 3 lines → legal, floor **1.80**
- `"600-year-old city of tombs"` (26 chars) is one line
- 17 words → reject

## SPEC-CAP-03: placement

On 1080×1920 a card is legal only if the **glyph bbox** (after wrap, stroke, shadow) sits inside **all** of:

| Bound | Rect |
| --- | --- |
| Frame | x 0–1080, y 0–1920 (hard clip = fail) |
| 22–50% band | y 422–960 — the **whole block**, not just `y_pct` |
| Cross-post safe | x 64–853, y 270–1248 (`x < 64` or `x2 > 853` is a fail) |

- Text **center x**.
- `y_pct` is the **center** of the block (`h*y_pct - text_h/2`). Default **36%** (691). Anchor-in-band ≠ bbox-in-band: after raising line count, recompute `y` / `caption_move` so the first line stays ≥22% and the last line ≤50%.
- Hard fail if the glyph box overlaps a `protect` refocus point within 80px.

Suggested fix for overflow: `caption_move` / wrap / smaller size / split the idea. **Never suggest a box.**

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

Clash Display / Satoshi **60–72px** (title up to 84 if ≤12) is the preferred look. Lint and render **drop size** down to **52** when needed so the glyph block fits x 64–853, or wrap earlier. ALL CAPS / Hormozi shouting is `ok: false` unless a future `caption_style="punch"` is set (out of scope). Never emit `box=1`.

## SPEC-CAP-05: motion

On caption in, optional **2–4 frame** scale 100→102% (or opacity 0→1). Must finish inside the 0.4s land. No bounce, no per-word karaoke, no emoji rain.

`caption_add(..., enter="none"|"fade"|"punch")`. Default `punch` for titles, `fade` for body.

Independent text layers also accept `motion="none"|"fade"|"pop"|"slide"|"type_on"`. Pop is a 2–4 frame scale (same as punch). Slide is a short vertical ease-in. Type-on reveals characters inside the 0.4s land window via `enable`/`text` drawtext, still using a textfile (never inline apostrophes). All four stay box-free.

## SPEC-CAP-10: opt-in karaoke

`caption_style="karaoke"` is opt-in. Default phrase cards stay. Karaoke is not the house style.

- Spoken word fill `#FFE14A`, rest sand `#F6EBD4`
- No box, Clash Display, y 22–50%
- Word timings: `words: [{text, start_s, end_s}]`
- Textfiles / ASS, never apostrophes inline
- SPEC-CAP-04 / no-box / no-ALL-CAPS still apply
- `caption_add(..., style="karaoke", words=...)` is `ok: false` without timings

## SPEC-CAP-11: opt-in word-pop

`caption_style="pop"` is opt-in. Default phrase cards and karaoke tracing stay.

- One word on screen at a time, replaced from whisper timings `words: [{text, start_s, end_s}]`
- Clash Display Semibold, fill `#FFE14A`, 3px `#1A1410` stroke, no box, Alignment 8 / y 22–50% (MarginV ~620 on 1080×1920)
- Default pop: scale-in 128→100 over ~90ms
- Expand contractions at caption time (`I'm` → `I` / `am`). No apostrophes in ASS
- Render as **one ASS overlay** at assemble, not chained `drawtext`. Recut is `caption_edit`, not a clip re-encode
- SPEC-CAP-02 hold floors (1.5s / 1.8s), 16-word cap, and 3-line wrap do **not** apply. A 0.2s word is correct if it matches speech
- `caption_add(..., style="pop")` is `ok: false` without timings

## SPEC-CAP-06: contrast lint

After placing a card, sample the underlay in the text bbox on the midpoint still.

Fail review / lint if mean underlay luminance is too close to `#F6EBD4` (both in 0.70–1.0). Suggested fix: `caption_move` to a darker band, or pick another frame. **Never suggest a box.**

White / sand plates fail. Dark plates pass.

## SPEC-CAP-07: density

Not every clip gets a card. Review **warns** if `caption_count / clip_count > 0.7` on a timeline with 8 or more clips. Warns if the first 1.5s has no title hook and the project preset is `karachi`. Other projects do not require a first-frame hook. If a title exists it must meet SPEC-CAP-02. A **caption-must** collage (`context/scenes/collage.md`) will trip the density warn. Keep the lines; do not drop text to silence it.

## SPEC-CAP-08: phone proof

`preview_stills` / `caption_lint` write a **phone proof** JPEG: the frame scaled to 270×480 (25% of 1080×1920). If stroke vanishes or text clips, lint fails. This is the arm's-length test.

## SPEC-CAP-09: layout seams

On a layout clip, the caption still has no box (SPEC-CRAFT-02). Park it so the glyph bbox misses every **seam** (a join ±40px, same energy as the 80px `protect` rule). A hit is a lint / review fail. Suggested fix: `caption_move`.

Seams on 1080x1920, and the y to use:

| Kind | Seams | Caption |
| --- | --- | --- |
| `stack_v` | y = 960 (0.50) | `y_pct` **0.28**, center x |
| `stack_h` | x = 540 (0.50) | `y_pct` **0.36**. Center x when both panes are even; otherwise bias into the darker pane |
| `stack_v3` | y = 640 (0.33) and y = 1280 (0.67) | `y_pct` **0.22** (top row). 0.67 is already outside the 22 to 50% band. 0.33 is the live seam. A mid-row pocket at **0.50** is the center of pane 1, not a join |
| `grid_2x2` | cross at (540, 960) | `y_pct` **0.28** (upper half). Center-cross is a fail. A long line that sits on the vertical gutter (x = 540 ±40px) is a fail |

Editorial cards: `context/scenes/pair.md`, `collage.md`, `ride-pair.md`.

## Tools

- `caption_add(clip_id, text, role, enter?, style?, words?)` — phrase cards, opt-in karaoke, or word-pop
- `caption_edit` / `caption_move(y_pct)` — still center-x
- `caption_lint` → `{ ok, errors[], warnings[], hold_s, lines, bbox, contrast }` with bbox tested against frame + 22–50% + cross-post
- `clip_fit` still wins over a short clip
- `overlay_preview` shows IG/TT/Shorts chrome, the 22–50% band, and the right column

`caption_lint` does not mutate the timeline.
