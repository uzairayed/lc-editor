# Ammo NYC / Larry Kosilla

Triggers: Ammo NYC, Larry Kosilla, barn-find first wash, filthy detailing, process transformation, satisfying dirty→clean, before/after detailing, "First Wash in N years."

## When to use

Owner asks for a barn-find or transformation compile. Footage shows a filthy car being detailed to clean. Owner names Larry Kosilla or Ammo NYC as a reference. Project is 9:16 Short/reel (15–28s) or 16:9 YouTube long-form (12–35 min).

## Intent

Show satisfying dirty→clean transformation. The viewer watches neglected metal and paint become presentable again. Key signature: 50/50 tape-line (or equivalent dirty|clean on one panel) as the mid-video hero.

## Compile

Ordered beats for long-form (12–35 min). Compress for Shorts.

1. **Hook** — garage-door reveal, dirty interior close-ups, dusty exterior, applause/reaction. Alternates ~10–20s context / people / dirt inserts. Music on intro montage.
2. **Owner/guest chat** — two-person live-to-camera with burned-in subtitles. Establishes the car's story.
3. **Wheels off, undercarriage** — wheels removed, wells and undercarriage cleaned.
4. **Engine bay** — nest and grime cleaned.
5. **Foam wash** — power wash dust, soap foam, blue towel.
6. **50/50 hero** — tape line mid-polish. Dirty|clean on one panel. This is the long hold reveal.
7. **Interior strip** — seats out, carpets power-washed, drill-brushed, steam-vac, enzyme until rinse runs clear.
8. **Interior finish** — leather and plastics steamed then conditioned.
9. **Mechanical refresh** — fuel system, first start (second climax).
10. **Drive/reveal** — road, burnouts, clean hero wide.

For 9:16 Shorts (15–28s): hook dirt → one process satisfaction → clean reveal. Not a slideshow of every step.

## Hold

| Beat | Hold | Notes |
| --- | --- | --- |
| Hook dirt inserts | **ack** to **breath** | Quick cuts, alternating |
| Owner/guest chat | **breath** to **detail** | Let dialogue land |
| Foam wash | **ack** | Enter dirty, leave on first clean pass |
| 50/50 tape-line | **reveal** (5–8s, up to 10s) | One per video. The transformation hero. |
| Interior strip | **detail** | Close texture of cleaning |
| First start | **vista** (3.5–5.5s) | Engine alive, people around car |
| Clean hero wide | **reveal** or **vista** | Depends on whether first start already took reveal |

A **reveal** at 10s is legal only when the source is one continuous take and the cut is already in the upper half of the target duration.

## Role

| Beat | Role |
| --- | --- |
| Hook dirt | `hook`, `before` |
| Owner/guest | `hook` (establishes story) |
| Wheels off | `wash`, `wheel` |
| Engine bay | `engine` |
| Foam wash | `wash` |
| 50/50 tape-line | `hero`, `detail` |
| Interior strip | `interior`, `detail` |
| Interior finish | `interior`, `after` |
| Mechanical refresh | `machine`, `engine` |
| First start | `journey` (second climax) |
| Drive/reveal | `closer`, `after`, `hero` |

`skip_face` for bystanders. Owner/guest talking-head stays unless asked to blur. Privacy blur plates/faces after story lock.

## Shot keep/skip

**Keep:**
- Garage-door reveal
- Dusty/dirty close-ups (emblem, interior, engine bay with nest)
- Foam application and rinse
- 50/50 tape-line (or any dirty|clean split on one panel)
- Seats out, carpet power-wash, drill-brush, steam
- Leather/plastics steam
- Engine bay open with people
- First start moment
- Drive, burnouts
- Clean hero wide

**Skip:**
- Bystanders without context (`skip_face`)
- Redundant repetitions of the same action
- Product lower-thirds (none observed in sampled hook)

## Cut

Enter on the recognizable frame: hand hitting garage door, first foam contact, tape line visible, engine turning over. Exit after the action registers or on motion toward the next beat. Hard cut is default.

**Transitions:**
- Default cut throughout.
- `match` on dirty→clean same-panel (e.g., before/after the 50/50).
- Cap 3 decorated transitions per ≤60s (SPEC-CRAFT-09).

## Caption

Burned-in dialogue subtitles for live talk (Ammo's habit). LC: stroke-and-shadow, no box. `style="card"` for step or product lines if needed. Skip caption if the wipe says it (e.g., "WHEELS OFF" when wheels are visibly off).

## Motion

- Hook: no freeze, speed-ramp, or slow-mo observed in sampled opening.
- Process cuts: no split-screen observed.
- `punch` or `zoom_pair` on 50/50 hero for emphasis.
- Macro emblem: `kenburns` or `punch` legal.
- Video clips: `none` unless punch on a detail texture.

## LC mapping

**Long-form YouTube (12–35 min):**

```
project_create(preset="youtube")
project_set(duration_cap_s=2100)  # 35 min
media_understand()
highlights_suggest(style="process")
```

Build timeline following Compile beats. One `layout_add stack_h` for explicit before/after at section change, not every clip.

```
clip_add(role="hook", hold="breath", ...)
clip_add(role="before", hold="ack", ...)
clip_add(role="wash", hold="ack", ...)
layout_add("stack_h", panes=[before_clip, after_clip])  # section change only
clip_add(role="hero", hold="reveal", ...)  # 50/50 tape-line
transition_set(type="match", ...)  # dirty→clean same-panel
caption_add(style="card", text="...")  # step/product lines
motion_punch(clip_id, ...)  # on 50/50 hero
review_report()
export(preset="youtube")
```

**Short/reel (15–28s):**

```
project_create(preset="process")
media_understand()
highlights_suggest(style="process")
```

Compress: hook dirt → one process satisfaction (50/50 or foam rinse) → clean reveal. Target 15–28s.

```
clip_add(role="hook", hold="ack", ...)
clip_add(role="hero", hold="reveal", ...)  # one satisfaction moment
clip_add(role="closer", hold="breath", ...)
review_report()
export()
```

## Done

A stranger understands: this car was neglected, someone cleaned it methodically, and now it looks new. The 50/50 tape-line (or equivalent panel split) is the moment they remember.

## Unverified

Do not build a timeline on these until visually confirmed:

- NLE/editor name Larry uses.
- Larry's video camera body (machineswithsouls stills kit is photographer Mike's, not Larry's video gear).
- Exact wash-section cut rhythm (seconds-per-shot was not measured).
- Shorts pacing and caption style (browser died before inspection).
- Speed ramps in body of video (none in sampled hook, rest unverified).

## Sources

- AMMO NYC YouTube channel: https://www.youtube.com/@AMMO-NYC
- Larry Kosilla bio: https://ammonyc.com/blogs/news/larry-kosillos-full-bio
- Behind the scenes at AMMO NYC: https://machineswithsouls.com/behind-the-scenes-at-ammo-nyc/
- ZR1 episode "First Wash in 30 Years! Disgusting Corvette ZR1 Barn Find Insane Detail Restoration": https://www.youtube.com/watch?v=PrPWHw4xWDI
- Motor1 RAC #72 (May 2022) on channel evolution.
