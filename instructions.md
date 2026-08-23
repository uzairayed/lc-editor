# LC Reel Craft

Engine craft (no caption box, hold formula, 15-28s target, 60s cap, music only when the owner opts in) lives in `specs/craft.md` and applies to every project.

This file is the **Sites to visit in Karachi** series preset: optional branding, not the editor default. Apply it with `project_create(..., preset="karachi")`. A Murree cut, or any other reel, does not need this structure.

## Structure (every episode)

1. **Hook (0 to 2s):** the single most striking shot of the destination, not the ride. Caption states the payoff up front ("600-year-old city of tombs, 2 hours from Karachi"). Never open with a logo, a black frame, or the highway.
2. **Series card (2 to 3.5s):** "Sites to visit in Karachi, Ep N" over a moving shot, not a still.
3. **The journey (3.5 to ~12s):** ride clips in geographic order. One caption for distance/time/route, one for the food stop. Cut on motion: lean into a corner, an overtake, a landmark passing.
4. **The site (~12s to end):** longest section. Wide establishing shot first, then details (tilework, carvings, texture). Slow the cutting down here; let shots breathe 2 to 3s.
5. **Closer:** one line that invites the next episode or a save ("Full route in Ep 2"). End on a 0.3s hold of the last frame.

## Timing (readability first)

- Target **18 characters per second** on screen, then add **0.4s** for the text to land.
- Floor: **1.8s** for any two-line card. Never hold a readable caption under **1.5s**.
- Max **2 lines**, **~10 words**, wrap at ~26 characters.
- Stretch the clip to the caption hold, or drop the text. Never speed-ramp a clip just to fit a caption.
- Not every shot needs a caption. If the shot says it, stay silent.

## Captions

### Look

- **Clash Display Semibold** for titles, **Satoshi Bold** for body. Both are free for commercial use from [Fontshare](https://www.fontshare.com). Fallback if Fontshare is unavailable: **Anton** for titles, **Space Grotesk Bold** for body (both on Google Fonts, OFL).
- Size **60 to 72px** on 1080x1920. Titles may go up to **84px** if under 12 characters.
- Warm sand `#F6EBD4` fill.
- **No background of any kind. Ever.** No box, no banner, no semi-transparent bar, no blur pad, no gradient scrim behind text. This is a hard rule.
- Legibility comes from the text itself: **3 to 4px dark stroke** (`bordercolor=0x1A1410`, `borderw=3`) plus a soft drop shadow (`shadowcolor=black@0.5`, `shadowx=2`, `shadowy=2`).
- If text is still hard to read on a shot, move the caption to a calmer part of the frame or pick a different frame. Do not add a background.
- Centered in the **22 to 50%** vertical safe zone (clear of the Instagram/TikTok UI top and bottom).

### Voice

- Short, concrete, first-person-adjacent. "100 km down the N-5" not "We traveled approximately 100 kilometers."
- Numbers over adjectives: "2 hours, one fuel stop" beats "a long scenic ride."
- One idea per caption. If it needs a comma splice, it is two captions.

### Technical

- Captions via `drawtext=textfile=...:expansion=none`. Never inline apostrophes; always go through a textfile.
- One textfile per caption, UTF-8, no trailing newline.

## Transitions

- Default is a **hard cut on motion**. Transitions are punctuation for section changes, not decoration; a 20s reel earns **2 to 3** at most.
- **Whip pan:** into the site reveal. Fake it in ffmpeg with a fast directional blur out of the last ride frame into the first site frame (or shoot a real pan and cut mid-blur).
- **Zoom punch:** a quick 100 to 108% scale-in over 3 to 4 frames when a key caption lands or on a detail shot. Subtle; if the viewer notices the zoom itself, it is too much.
- **Match cut:** the strongest tool you have. Cut wheel-spin to dome curve, visor reflection to tile pattern. Costs nothing in ffmpeg, reads as high-end.
- Never use: star wipes, spins, cross-dissolves between unrelated shots, or any preset that looks like a slideshow app. A plain 4-frame luma fade is fine for the closing frame only.

## Sound

- User is Muslim: **no music**. This is non-negotiable, including "ambient" or "cinematic" beds.
- The soundtrack is the ride: keep **engine and wind** from ride clips. Duck wind rumble below 100 Hz with a high-pass if it muddies.
- At the site, keep natural ambience (birds, footsteps, breeze). Mute clips where bystanders are talking.
- Short **SFX** only: a whoosh on hard cuts, a tick/pop when a caption lands. Keep SFX at least 6 dB under the engine so they read as texture, not effects.

## Grade (motovlog)

- Teal / cool shadows, warm orange midtones and highlights.
- Punchy S-curve, modest saturation lift, shadows stay black (not milky).
- Light film grain + soft vignette on every shot so ride and tombs match.
- Protect turquoise tile and sandstone: do not crush the teal floor to grey or turn stone neon. If the split-tone fights the tilework, pull the teal out of the shadows for those shots only.
- One look across the reel, not a different LUT per clip. Grade the hero shot first, then match everything to it.

## Series rules

- Brand: **Sites to visit in Karachi**.
- Episode 1: Makli / Thatta. Beats: series title, 100 km / ~2 hours on the N-5, **Cafe Imran, Gharo**, then the site.
- No face selfies. Helmet visor-down is OK.
- Keep episode structure consistent so the series is recognizable: same font, same caption position, same card timing every episode.

## Export

- 9:16, 1080x1920, 30fps, H.264 yuv420p, AAC, faststart.
- Length **15 to 28s**. If the cut runs long, trim journey and site in balance, but keep the site as the longest single section.
- Check the final render on a phone at arm's length before posting. If any caption is not readable at a glance, fix the timing or placement, not the styling.
