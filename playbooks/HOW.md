# Style playbooks

Editorial judgment for *how* to compile a video in a named creator's style. Scene cards in `context/scenes/` still answer what a shot *is*. Engine floors in `specs/craft.md` and `specs/edit.md` still bind. A playbook can only raise a hold, never drop below **ack**.

## When to open this library

Open `playbooks/INDEX.md` when the owner:

- Names a creator ("do this like Ammo NYC").
- Names a compile style ("barn-find first-wash", "transformation reel", "process before/after").
- Names a job type where a known playbook exists ("detailing video", "talking-head", "shorts").

If none match, skip this library. The scene library (`context/HOW.md`) still applies.

## Steps

1. Read `playbooks/INDEX.md`. Collect every style whose trigger matches what the owner asked for. Read those files. Skip the rest.
2. Still read `context/INDEX.md` for shot subjects. A playbook chooses structure and pacing; scene cards still tell you what is in each frame.
3. Let the playbook set compile order (beats), role assignments, hold upgrades, and when to punch or hold long.
4. A playbook may raise a **hold** if the owner requests the creator's style. It may never drop below **ack** (`context/HOW.md` hold table).
5. Resolve conflicts: specs > playbook > scene card. If a playbook says "hold 12s on a hero" and `specs/craft.md` caps at 10s, the cap wins.

## What a playbook cannot do

- Add a caption box (SPEC-CRAFT-02).
- Turn on music without owner opt-in (SPEC-CRAFT-01).
- Use decorated transitions on every cut (SPEC-CRAFT-09: cap 3 per ≤60s).
- Invent timestamps, gear, or software the research does not confirm.

## Adding a style

1. Copy `playbooks/styles/_template.md`.
2. Fill every section. Use hold words from `context/HOW.md` and roles from the template.
3. Add one INDEX line whose trigger is the creator name, the style name, or both.
4. One file per creator or style. If two styles share all beats, hold, and roles, they belong on the same card as extra triggers.
