# Ride pair

Triggers: two-up ride, two helmet POVs, two N-5 wides, two overtake lanes seen at once, two highway or cockpit frames in one slot.

## Intent

Two landscape ride POVs side by side are a **two-up**, not a portrait split and not a pair of signs. The road is still punctuation. The stack is one journey beat.

## Hold

**breath**. **detail** only when a pane’s point is a plate or a name (then you are on `pair.md`, not here).

## Role

`journey`. The site still owns more time than the two-up.

## Cut

`layout_add("stack_h", panes=[...])`. Crop each pane onto the vanishing point or the rider, not the sky. Video: `none`.

Enter already at speed. Exit mid-motion into the next journey clip or the site. Hard cut.

This is one timeline slot, not multicam. Pane 0 is the audible road (`SPEC-LAYO-02`).

## Caption

One line for the **journey block** (distance, time, route), same voice as `highway.md`. Numbers. Place it with SPEC-CAP-09 for `stack_h`: `y_pct` **0.36**, center x when both panes are even, otherwise bias into the darker pane.

## Motion

Video: `none`. An all-still two-up is rare on a ride; if it happens, `kenburns` along the road.

## Music

Owner opt-in only. A ride two-up keeps engine as the picture’s sound (pane 0). `duck_natural` ducks that engine under the imported track. Leave the engine in the mix.

Snap the layout **in** as one clip. Caption floor wins over a 1/4-beat snap (`SPEC-MUS-06`).

## Done

The viewer feels two roads at once for one **breath**, the journey line has landed, and the next clip is a new place or a full-frame site.
