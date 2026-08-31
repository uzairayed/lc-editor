# lc-editor

A local video editor for a computer use agent, made for grokbot. You drive it from an MCP client; there is no timeline UI to click. You send tool calls; ffmpeg renders the file.

Built for short 9:16 reels (1080x1920, 30fps). Captions are stroke-and-shadow text, never a box. Sound, duration, and caption density are the owner's call: ask before you cut. This version composites multiple layers, applies a small effect pack, expands templates into ordinary timeline items, and can mix owner-imported music with beat sync. Engine rules live in `specs/craft.md`. Series branding (for example Karachi) is an optional preset, not the default.

## Needs

- Python 3.11 or newer
- ffmpeg and ffprobe on your PATH

## Install

From a clone of this repo:

```
pipx install .
```

`pip install .` works too. pipx keeps the app in its own env and puts `lc-editor` on your PATH.

From GitHub:

```
pipx install git+https://github.com/uzairayed/lc-editor.git
```

## Run

```
lc-editor serve --project ./my-reel
```

`--web` starts a page on 127.0.0.1:8765 that can show stills. It only reads.

## Cursor

Add this to your MCP config. Use an absolute project path.

```json
{
  "mcpServers": {
    "lc-editor": {
      "command": "lc-editor",
      "args": ["serve", "--project", "/absolute/path/to/project"]
    }
  }
}
```

On Windows the path looks like `C:/Users/you/my-reel`.

## Tools

Every edit returns `{ ok, timeline_summary, warnings }`. Illegal requests fail out loud. Same `op_id` twice does not duplicate. `review_report` must pass before `export`. Preview stills and the contact sheet are JPEG files on disk, not base64.

The primary track is still the gapless `clips` list (`clip_add`, trim, split, reorder, motion, transitions). `motion_zoom_in` / `motion_zoom_out` are a 12-frame scale hit (not Ken Burns). Two or more sources can share one slot (`layout_add`). Overlays, look, and music sit beside it:

- Layers: `layer_add` / `layer_update` / `layer_remove` / `layer_reorder` / `layer_transform` / `layer_keyframe` for timed video, image, or text. `text_style` sets fade, pop, slide, or type-on. `effect_add` / `effect_update` / `effect_remove` attach `blur`, `sharpen`, `glow`, `grain`, `vignette`, `lut`, or `color`. Raw ffmpeg filter strings are rejected.
- Templates: `template_list`, `template_apply("editorial"|"karachi", bindings=...)`, `template_save`. Apply writes ordinary layers and look; the project stays editable.
- Music: default is off. `project_set(allow_music=true)` is the owner opt-in. Then `import_file` a local `.mp3`/`.wav`/`.m4a` and `music_add`. `beat_analyze`, `beat_edit`, dry-run `beat_sync_preview`, then `beat_sync_apply`. There is no stock catalog; licensing stays with the owner.
- Layouts: `layout_add("stack_v"|"stack_h"|"stack_v3"|"grid_2x2", panes=[...])` composites two to four sources into one clip. `layout_pane` refocuses a cell. `layout_clear` flattens back to pane 0. A vista or reveal stays full-frame.
- Captions: `caption_add` still works and syncs to a bound text layer. No box, banner, or scrim.

Optional: `project_create(..., preset="karachi")` loads series branding. Other reels do not need it.

## Capability matrix

| Area | In this version |
| --- | --- |
| Canvas | 1080x1920, 30fps, MCP only |
| Primary track | Gapless clips, trim/split/reorder, kenburns/punch/zoom_in/zoom_out |
| Layouts | `stack_v`, `stack_h`, `stack_v3`, `grid_2x2`. One timeline slot |
| Layers | Timed video, image, and text overlays with z-order, transform, keyframes |
| Effects | Registry: blur, sharpen, glow, grain, vignette, lut, color |
| Text | Stroke-and-shadow only. Motion: fade, pop, slide, type-on |
| Templates | `editorial`, `karachi`; apply expands to ordinary layers |
| Sound | Natural audio, beds, SFX (`tick`, `whoosh`, `swipe`, `button`, `keyboard`, and the rest of the bundled pack). Music is opt-in via `project_set(allow_music=true)` then `music_add` |
| Beat sync | `beat_analyze`, `beat_edit`, dry-run `beat_sync_preview`, then `beat_sync_apply` |
| Look | One adjustment layer (LUT, grain, vignette) after the cut |

## Giving this to grokbot

Once the MCP server is in grokbot's config, hand it a prompt like this:

```
You have an MCP server called lc-editor. It is a video editor you control
entirely through tool calls; ffmpeg does the rendering.

My raw clips are in <folder>. Cut a 9:16 reel.

Follow specs/craft.md: stroke-and-shadow captions with no background box,
hard cuts on motion.

Before you import or cut, ask me:
1. What is this reel about?
2. How long should it be? (default 15 to 28s, cap 60s)
3. Music, or natural audio only?
4. Sparse captions, or a line on every clip?

Store the answers with project_set (subject, target_duration_s,
caption_mode). If I want music, project_set(allow_music=true), import
my track, music_add it, beat_analyze, show beat_sync_preview, then
beat_sync_apply only after I confirm.

Do not assume a travel series, a motorcycle cut, or a grade. Work in
passes: analyze the footage, pick the strongest shots, match what you
see in the keyframes to context/INDEX.md and read only those scene
cards (context/HOW.md). If nothing matches, use ack. Build the
timeline. An occasional two-up is context/scenes/pair.md. A reel that
is mostly stacks is collage.md. Add layers or a template if needed,
then run review_report and fix every warning before you export. Show
me preview stills at each pass.
```

Swap the folder into the prompt as needed. Add `preset="karachi"` only for that series.

Scene holds live in `context/`. The agent looks up subjects in `context/INDEX.md` and reads only the matching cards. Ride cards stay on the shelf unless those subjects are in the footage. Engine floors in `specs/craft.md` still win when they conflict.

## Not in this version

Multicam, speech-to-captions, a stock music catalog, Drive import, or a browser you edit in.
