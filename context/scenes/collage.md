# Collage

Triggers: collage, layout-heavy reel, mostly stacks, stacked details, 2x2 of carvings or tiles, caption-must experiment.

## Intent

A 15 to 30s place cut can be **mostly layouts** when the point is a set, not a walk-through. **Pair** is one two-up, then a different beat (`pair.md`). **Collage** is the spine: several stacks in a row, each a new set.

## Hold

Each `layout_add` is **one** clip. Hold is that clip, not the sum of panes (`SPEC-LAYO-02`).

- `stack_v` / `stack_v3` / `grid_2x2` of details (carvings, tiles, plates, names): **detail**. Stay until every pane’s name or object is readable.
- **caption-must** (a line on every clip): hold is `max(detail, caption hold)` via `clip_fit`. Readable panes plus SPEC-CAP-02, not a snappier collage.
- A wide tomb, door, or court stays full frame. **vista** and **reveal** never sit inside a layout.

A 30s collage sits in the 28 to 60s warning band. Use that length only when the owner asked for a 30s experiment. Default target stays 15 to 28s.

## Role

`site_detail` for stacked carvings, tiles, or objects. `site_wide` only when the stacks *are* the destination list (named walls, named tombs). `journey` belongs on `ride-pair.md`, not here.

## Cut

Several `layout_add` clips in a row are legal when each stack is a **new set** (new names, new objects). The same two boards again is a pair you already used; drop it.

`stack_v` for two, `stack_v3` for three, `grid_2x2` for four. Crop each pane onto the object. Exit when every pane has been read once. Hard cut to the next set, or to a full-frame **vista** / **reveal**.

## Caption

**caption-must:** write the fact the frames do not (count, dynasty, distance). The pair skip ("plates name themselves") is pair-only.

Place the card on SPEC-CAP-09 so the glyph box misses every **seam**. Suggested fix for a hit is `caption_move`, not a plate.

## Motion

Video or mixed: `none`. All-still stack: `kenburns` on the layout clip. No punch on a stack.

## Music

Owner opt-in only (`allow_music`). Default is engine, wind, or site ambience. A melody is `music_add` after the owner says yes, never `audio_bed`.

When a track is on: keep pane-0 natural audio (`SPEC-LAYO-02`). `duck_natural` ducks that bed under the track (about 8 dB). The two-up or stack stays a picture with engine or air under it.

Snap the **in** of the layout clip to a downbeat. The whole stack is one beat. Strength 0 is preview only. On a **caption-must** collage, the caption floor wins: do not shorten `stack_v3` or `grid_2x2` below readable plus SPEC-CAP-02 to hit a 1/4 beat (`SPEC-MUS-04`, `SPEC-MUS-06`).

## Done

A stranger can name each set from its hold, every caption clears its **seam**, and a wide or a door still owns the full frame when it appears.
