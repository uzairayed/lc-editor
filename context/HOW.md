# Scene library

Editorial judgment for what a shot *is*, and how long to keep it. Engine floors in `specs/edit.md` and `specs/craft.md` still bind. A card can only raise a hold, never drop it below **ack**.

This library is not a motorcycle series. Ride cards exist for when a helmet or highway is actually in the frame. Everything else uses the generic holds below.

## Intake

If the owner has not already answered, ask before you set durations (SPEC-SES-15):

1. What is the reel about?
2. How long? Default is the 15 to 28s target. They may pick a number inside the 60s cap.
3. Sound: music, or natural audio only.
4. Captions: sparse, or a line on every clip (`caption_must`).

Store the answers with `project_set`. Then analyze footage.

## Holds

Use these words in cards and in your own notes. They mean the same range every time.

| Word | Picture on timeline | When |
| --- | --- | --- |
| **ack** | 2.4s video, 2.2s still | Engine floor. Default when no card matches. |
| **breath** | 2.4 to 3.2s | Passing beat, punctuation, a readable object that is not the point. |
| **detail** | 2.4 to 3.0s | Close texture, object, UI, hands. Punch is legal. |
| **vista** | 3.5 to 5.5s | Wide place. The viewer needs to stand there. |
| **reveal** | 5.0 to 8.0s, up to 10.0s | Threshold into the subject (door, walk-in, first wide). One per reel. |

A **reveal** at 10.0s is legal only when the source is one continuous take *and* the cut is already in the upper half of the target length. Otherwise stay at 5.0 to 8.0s.

`stack_v3` and `grid_2x2` of details use **detail** (stay until every pane is readable). They never inherit **vista** or **reveal**. **caption-must** (owner asked for a line on every clip): hold is `max(detail, caption hold)` via `clip_fit`. The pair skip ("plates name themselves") is `pair.md` only.

Analysis splits shots at 8.0s (`SHOT_MAX_S`). A long walk-in may arrive as two rows. If the keyframes are the same action, `clip_add` as **one** clip that spans both.

## Steps

1. After `media_analyze`, look at keyframes (and `shots_rank` sheets if you made them). Name every subject you can see in a kept shot: object, action, place.
2. Open `context/INDEX.md`. Collect every card whose trigger matches a named subject. Read those files. Skip the rest. Skip the Ride section unless a helmet, wheel, or highway is actually in the frame.
3. Resolve overlaps on one clip: action beats object, reveal beats passing, the longer hold wins. Then re-budget so the sum lands on the owner's target, or 15 to 28s if they did not pick one. A short cut gets **one** reveal or **one** vista as its long hold, not both at the top of their ranges. A longer owner experiment may sit in the 28 to 60s warning band.
4. Choose a layout card, not a generic stack:
   - Two named things, one hold, then a different beat → `pair.md`
   - Mostly stacks, new set each time, or **caption-must** → `collage.md`
   Several `layout_add` clips in a row are legal on a **collage**. Each stack is one clip (`SPEC-LAYO-02`). A vista or a reveal keeps the whole frame. Caption y on a stack is SPEC-CAP-09.
5. Set `in_s` / `out_s` from the card's cut rule, duration from the hold word, role from the card, caption and motion from the card. Stretch the clip to caption hold if a caption is on it (`clip_fit`).
6. Done: every kept shot has either a card decision written next to it, or an explicit "no card, **ack**". A layout counts as one decision. The timeline duration matches the owner's target, or you have already told them why it must sit elsewhere.

## Adding a card

Copy `context/scenes/_template.md`. Add one INDEX line whose leading word is the subject the agent will see. One file per decision. If two subjects share the same hold, role, and cut, they belong on the same card as extra triggers, not as a second file.
