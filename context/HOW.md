# Scene library

Editorial judgment for what a shot *is*, and how long to keep it. Engine floors in `specs/edit.md` and `specs/craft.md` still bind. A card can only raise a hold, never drop it below **ack**.

## Holds

Use these words in cards and in your own notes. They mean the same range every time.

| Word | Picture on timeline | When |
| --- | --- | --- |
| **ack** | 2.4s video, 2.2s still | Engine floor. Default when no card matches. |
| **breath** | 2.4 to 3.2s | Passing, journey punctuation, a readable object that is not the destination. |
| **detail** | 2.4 to 3.0s | Close texture, carving, tile, hands. Punch is legal. |
| **vista** | 3.5 to 5.5s | Wide place. The viewer needs to stand there. |
| **reveal** | 5.0 to 8.0s, up to 10.0s | Threshold into the subject (door, gate, walking in). One per reel. |

A **reveal** at 10.0s is legal only when the source is one continuous take *and* the cut is already in the upper half of the 15 to 28s target. Otherwise stay at 5.0 to 8.0s.

Analysis splits shots at 8.0s (`SHOT_MAX_S`). A long door or walk-in may arrive as two rows. If the keyframes are the same action, `clip_add` as **one** clip that spans both.

## Steps

1. After `media_analyze`, look at keyframes (and `shots_rank` sheets if you made them). Name every subject you can see in a kept shot: object, action, place.
2. Open `context/INDEX.md`. Collect every card whose trigger matches a named subject. Read those files. Skip the rest.
3. Resolve overlaps on one clip: action beats object, reveal beats passing, the longer hold wins. Then re-budget the reel so the sum still lands in 15 to 28s. A 15 to 28s cut gets **one** reveal or **one** vista as its long hold, not both at the top of their ranges.
4. If two or more kept shots are the same kind of readable object (two signs, two named walls, two plates) and they should be seen together, `layout_add` them as **one** clip. Hold is the longer card, not the sum. Kinds and pane counts are in `specs/layouts.md`. A vista or a reveal keeps the whole frame.
5. Set `in_s` / `out_s` from the card's cut rule, duration from the hold word, role from the card, caption and motion from the card. Stretch the clip to caption hold if a caption is on it (`clip_fit`).
6. Done: every kept shot has either a card decision written next to it, or an explicit "no card, **ack**". A layout counts as one decision. The timeline duration is inside 15 to 28s, or you have already told the owner why it must sit in the 28 to 60s warning band.

## Adding a card

Copy `context/scenes/_template.md`. Add one INDEX line whose leading word is the subject the agent will see. One file per decision. If two subjects share the same hold, role, and cut, they belong on the same card as extra triggers, not as a second file.
