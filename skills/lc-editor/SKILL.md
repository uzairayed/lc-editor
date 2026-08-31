# lc-editor

Use this skill when asked to cut 9:16 vertical reels from raw video clips. The `lc-editor` MCP server gives you tool calls to build a timeline; ffmpeg does the rendering.

## When to use

- User asks you to edit video clips into a short reel
- User asks for 9:16 vertical video editing
- User mentions cutting, trimming, or assembling footage

## Quick start

The MCP server is `lc-editor`. Call its tools to build and export your reel.

## Workflow

1. **Analyze footage first.** Use `import_folder` or `import_file` to bring in media, then `media_analyze` and `shots_list` / `shots_rank` to find the strongest shots. Look at keyframes with `thumbnail` or `contact_sheet` before deciding what to cut.

2. **Ask about sound before touching the timeline.** Sound is the owner's call, not yours. Ask: "Do you want music or natural audio only?" Do not assume either way.
   - If music: call `project_set(allow_music=true)`, import the track, `music_add`, `beat_analyze`, show `beat_sync_preview`, then `beat_sync_apply` only after the user confirms.
   - If natural audio: proceed without music tools.

3. **Match subjects to scene cards.** When you look at keyframes or set clip durations/roles, consult `context/INDEX.md` and read only the matching scene cards. The process is in `context/HOW.md`.

4. **Build the timeline.** Use `clip_add`, trim, split, reorder, motion, and transitions. An occasional two-up is `context/scenes/pair.md`. A reel that is mostly stacks is `context/scenes/collage.md`. Two ride POVs is `context/scenes/ride-pair.md`. Add layers or apply a template if needed.

5. **Run `review_report` before export.** Fix every warning it returns.

6. **Show preview stills at each pass.** Use `preview_stills` so the user can see progress.

## Key constraints

- Canvas: 1080×1920, 30fps
- Captions: stroke-and-shadow text only, never a box
- Templates: `editorial` and `karachi` (apply expands to ordinary layers)
- Music is opt-in only via `project_set(allow_music=true)`
- Engine rules in `specs/craft.md` are floors; scene-card judgment can raise them but never lower them

## Tools overview

Every edit returns `{ ok, timeline_summary, warnings }`. Illegal requests fail out loud. Same `op_id` twice does not duplicate.

**Timeline:** `clip_add`, `clip_remove`, `clip_reorder`, `clip_trim`, `clip_split`, `clip_set_duration`, `clip_fit`, `clip_refocus`

**Motion:** `motion_kenburns`, `motion_punch`, `motion_zoom_in`, `motion_zoom_out`, `motion_none`, `motion_hold`

**Layouts:** `layout_add("stack_v"|"stack_h"|"stack_v3"|"grid_2x2", panes=[...])`, `layout_pane`, `layout_clear`

**Layers:** `layer_add`, `layer_update`, `layer_remove`, `layer_reorder`, `layer_transform`, `layer_keyframe`

**Effects:** `effect_add`, `effect_update`, `effect_remove` (blur, sharpen, glow, grain, vignette, lut, color)

**Text:** `caption_add`, `caption_edit`, `caption_move`, `caption_remove`, `text_style` (fade, pop, slide, type-on)

**Music:** `music_add`, `beat_analyze`, `beat_edit`, `beat_sync_preview`, `beat_sync_apply`

**Templates:** `template_list`, `template_apply`, `template_save`

**Review & Export:** `review_report`, `export`
